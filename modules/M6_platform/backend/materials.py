"""素材管理：教师原始件（视频/音频/课件）统一入库 + 勾选批量处理。

设计要点：
- 上传 = 只入库（status=unprocessed），不自动跑 M1，与处理解耦。
- 处理 = 勾选若干素材 → 后台逐个调 M1 ingest → 产出转写（文字库）。
- 重处理覆盖：每个素材产出的转写统一重命名为稳定名 TR_{material_id}，
  因此重处理同一素材会覆盖它自己那份文字，不同素材永不串号
  （M1 的 transcript_id 是每次调用 seq 从 1 起，不能直接当稳定键）。
- 课件（PDF/PPT）只存档，不参与处理（processable=False）。
- 旧 videos_manifest 的视频惰性并入素材清单（origin=video），数据不丢。
"""
import os
import sys
import json
import secrets
import threading
import shutil
from datetime import datetime, timezone

from flask import request

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from auth import require_auth, require_role, ok, err
from teachers import get_teacher_dir, list_all_teachers

VIDEO_EXT = {"mp4", "webm", "mkv", "mov", "avi"}
AUDIO_EXT = {"wav", "mp3", "m4a", "flac", "aac", "ogg"}
DOC_EXT = {"pdf", "pptx", "ppt"}
ALLOWED_EXT = VIDEO_EXT | AUDIO_EXT | DOC_EXT

_proc_lock = threading.Lock()       # 全局：同时只跑一个处理作业，避免 M1 临时产物串名
_manifest_lock = threading.Lock()   # 清单原子读改写


def _materials_dir(tid):
    d = os.path.join(get_teacher_dir(tid), "materials")
    os.makedirs(d, exist_ok=True)
    return d


def _manifest_path(tid):
    return os.path.join(_materials_dir(tid), "materials_manifest.json")


def _load_manifest(tid):
    p = _manifest_path(tid)
    if not os.path.exists(p):
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_manifest(tid, items):
    p = _manifest_path(tid)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def _patch_material(tid, material_id, **patch):
    """原子地改某条素材并落盘。"""
    with _manifest_lock:
        items = _load_manifest(tid)
        for it in items:
            if it.get("material_id") == material_id:
                it.update(patch)
                break
        _save_manifest(tid, items)
        return items


def _kind(ext):
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    return "courseware"


def _processable(kind):
    return kind in ("video", "audio")


def _videos_manifest(tid):
    p = os.path.join(get_teacher_dir(tid), "videos", "videos_manifest.json")
    if not os.path.exists(p):
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _migrate_legacy_videos(tid):
    """把旧「视频管理」里的视频惰性并入素材清单（幂等，按 legacy_video_id 去重）。"""
    with _manifest_lock:
        items = _load_manifest(tid)
        known = {it.get("legacy_video_id") for it in items if it.get("legacy_video_id")}
        changed = False
        for v in _videos_manifest(tid):
            vid = v.get("video_id")
            if not vid or vid in known:
                continue
            fn = v.get("filename", "")
            ext = fn.rsplit(".", 1)[-1].lower() if "." in fn else "mp4"
            items.append({
                "material_id": f"MAT_vid_{vid}",
                "title": v.get("title", fn),
                "filename": fn,
                "kind": "video",
                "ext": ext,
                "file_size": v.get("file_size", 0),
                "status": "unprocessed",
                "transcript_id": None,
                "processed_at": None,
                "created_at": v.get("created_at"),
                "error": None,
                "origin": "video",
                "legacy_video_id": vid,
            })
            changed = True
        if changed:
            _save_manifest(tid, items)
        return items


def _raw_path(tid, m):
    if m.get("origin") == "video":
        return os.path.join(get_teacher_dir(tid), "videos", m["filename"])
    return os.path.join(_materials_dir(tid), m["filename"])


def _my_teacher_id():
    card = next((t for t in list_all_teachers() if t.get("user_id") == request.user_id), None)
    return card["teacher_id"] if card else None


def _owner_guard(teacher_id):
    from teachers import load_teacher_card
    card = load_teacher_card(teacher_id)
    if not card:
        return err("教师不存在", 4040, 404)
    if card.get("user_id") != request.user_id:
        return err("无权操作此教师", 4030, 403)
    return None


def _view(m, tid):
    """对外视图（隐藏内部字段，补 processable）。"""
    return {
        "material_id": m.get("material_id"),
        "title": m.get("title"),
        "kind": m.get("kind"),
        "ext": m.get("ext"),
        "file_size": m.get("file_size"),
        "status": m.get("status", "unprocessed"),
        "transcript_id": m.get("transcript_id"),
        "processed_at": m.get("processed_at"),
        "created_at": m.get("created_at"),
        "error": m.get("error"),
        "origin": m.get("origin", "upload"),
        "processable": _processable(m.get("kind")),
    }


# ---------- 处理（后台 worker）----------

def _refine_config(enable_refine):
    """构造 M1 精修配置。开启精修时指向 DeepSeek（项目已有 key），不依赖本地 localhost:8000；
    无 key 时自动退回不精修（规避死端点）。返回 (config, refine_on)。"""
    cfg = {"enable_refine": False, "save_audio_samples": True}
    if not enable_refine:
        return cfg, False
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        return cfg, False  # 无 DeepSeek key：不精修，避免打 localhost:8000
    cfg.update({
        "enable_refine": True,
        "refine_api_url": "https://api.deepseek.com/v1/chat/completions",
        "refine_model": "deepseek-chat",
        "refine_api_key": key,
    })
    return cfg, True


def _process_one(tid, teacher_dir, m, enable_refine):
    """处理单个素材：调 M1 → 把产出转写重命名为稳定名 TR_{material_id}（覆盖式）。
    精修开启且成功时，用精修后的段落作为文字库内容。返回 stable transcript_id 或抛异常。"""
    from modules.M1_ingest import ingest_teacher_material

    raw = _raw_path(tid, m)
    if not os.path.exists(raw):
        raise RuntimeError("原始文件已丢失")

    cfg, refine_on = _refine_config(enable_refine)
    res = ingest_teacher_material(
        teacher_id=tid, source_paths=[raw], output_dir=teacher_dir, config=cfg,
    )
    if res.get("status") not in ("success", "partial") or not res.get("transcripts"):
        fail = (res.get("failed") or [{}])[0]
        raise RuntimeError(fail.get("error") or res.get("message") or "处理失败")

    item = res["transcripts"][0]
    raw_tp = item.get("transcript_path")     # 原始 ASR 稿（含 asr_quality 等元数据）
    ref_tp = item.get("refined_path")        # 精修 sidecar（可能为空/不存在）
    if not raw_tp or not os.path.exists(raw_tp):
        raise RuntimeError("未生成转写文件")

    with open(raw_tp, "r", encoding="utf-8") as f:
        tj = json.load(f)
    # 精修成功（有段落）→ 用精修后的段落，保留原始元数据
    if refine_on and ref_tp and os.path.exists(ref_tp):
        try:
            with open(ref_tp, "r", encoding="utf-8") as f:
                rj = json.load(f)
            if rj.get("segments"):
                tj["segments"] = rj["segments"]
                tj.setdefault("asr_quality", {})["refined"] = True
        except (OSError, json.JSONDecodeError):
            pass

    stable = f"TR_{m['material_id']}"
    tdir = os.path.join(teacher_dir, "transcripts")
    os.makedirs(tdir, exist_ok=True)
    new_tp = os.path.join(tdir, stable + ".json")
    tj["transcript_id"] = stable
    tj["material_id"] = m["material_id"]
    tj["source_file"] = m.get("title") or tj.get("source_file", "")
    tmp = new_tp + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, new_tp)

    # 清理 M1 临时产物（原始稿 + 精修 sidecar），避免 distill 把它们当成额外转写重复计入
    for p in (raw_tp, ref_tp):
        if p and os.path.exists(p) and os.path.abspath(p) != os.path.abspath(new_tp):
            try:
                os.remove(p)
            except OSError:
                pass

    # 音色切片同步重命名为稳定名（voice 训练按 *.wav 通配，命名不影响，仅为整洁/可覆盖）
    asp = item.get("audio_sample_path")
    if asp and os.path.exists(asp):
        new_asp = os.path.join(teacher_dir, "audio_samples", stable + ".wav")
        try:
            os.replace(asp, new_asp)
        except OSError:
            pass
    return stable


def _process_worker(tid, ids, enable_refine, lock_held):
    teacher_dir = get_teacher_dir(tid)
    try:
        items = _load_manifest(tid)
        by_id = {it["material_id"]: it for it in items}
        for mid in ids:
            m = by_id.get(mid)
            if not m or not _processable(m.get("kind")):
                continue
            _patch_material(tid, mid, status="processing", error=None)
            try:
                stable = _process_one(tid, teacher_dir, m, enable_refine)
                _patch_material(tid, mid, status="processed", transcript_id=stable,
                                processed_at=datetime.now(timezone.utc).isoformat(), error=None)
            except Exception as e:
                _patch_material(tid, mid, status="error", error=str(e)[:200])
    finally:
        if lock_held:
            _proc_lock.release()


def register_routes(app):
    @app.route("/api/v1/teachers/<teacher_id>/materials", methods=["GET"])
    @require_auth
    def list_materials(teacher_id):
        items = _migrate_legacy_videos(teacher_id)
        items = sorted(items, key=lambda m: m.get("created_at") or "", reverse=True)
        return ok([_view(m, teacher_id) for m in items])

    @app.route("/api/v1/teachers/<teacher_id>/materials", methods=["POST"])
    @require_role("teacher")
    def upload_material_raw(teacher_id):
        e = _owner_guard(teacher_id)
        if e:
            return e
        if "file" not in request.files:
            return err("请选择文件")
        f = request.files["file"]
        if not f.filename:
            return err("请选择文件")
        ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
        if ext not in ALLOWED_EXT:
            return err(f"不支持的类型，支持：{', '.join(sorted(ALLOWED_EXT))}")

        mid = f"MAT_{secrets.token_hex(6)}"
        fname = f"{mid}.{ext}"
        f.save(os.path.join(_materials_dir(teacher_id), fname))
        entry = {
            "material_id": mid,
            "title": request.form.get("title", "").strip() or f.filename.rsplit(".", 1)[0],
            "filename": fname,
            "kind": _kind(ext),
            "ext": ext,
            "file_size": os.path.getsize(os.path.join(_materials_dir(teacher_id), fname)),
            "status": "unprocessed",
            "transcript_id": None,
            "processed_at": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "error": None,
            "origin": "upload",
        }
        with _manifest_lock:
            items = _load_manifest(teacher_id)
            items.append(entry)
            _save_manifest(teacher_id, items)
        return ok(_view(entry, teacher_id), "已入库（未处理）")

    @app.route("/api/v1/teachers/<teacher_id>/materials/process", methods=["POST"])
    @require_role("teacher")
    def process_materials(teacher_id):
        e = _owner_guard(teacher_id)
        if e:
            return e
        data = request.get_json(silent=True) or {}
        ids = data.get("material_ids") or []
        enable_refine = bool(data.get("enable_refine", True))
        if not ids:
            return err("请先勾选要处理的素材")

        items = {it["material_id"]: it for it in _load_manifest(teacher_id)}
        todo = [mid for mid in ids if items.get(mid) and _processable(items[mid].get("kind"))
                and items[mid].get("status") != "processing"]
        if not todo:
            return err("没有可处理的素材（课件不参与处理，或所选项正在处理中）")

        if not _proc_lock.acquire(blocking=False):
            return err("已有处理任务在进行，请稍候", 4290, 429)
        try:
            for mid in todo:
                _patch_material(teacher_id, mid, status="processing", error=None)
            threading.Thread(target=_process_worker,
                             args=(teacher_id, todo, enable_refine, True), daemon=True).start()
        except Exception:
            _proc_lock.release()
            raise
        return ok({"queued": len(todo)}, f"已开始处理 {len(todo)} 个素材")

    @app.route("/api/v1/teachers/<teacher_id>/materials/<material_id>", methods=["DELETE"])
    @require_role("teacher")
    def delete_material(teacher_id, material_id):
        e = _owner_guard(teacher_id)
        if e:
            return e
        with _manifest_lock:
            items = _load_manifest(teacher_id)
            m = next((it for it in items if it.get("material_id") == material_id), None)
            if not m:
                return err("素材不存在", 4040, 404)
            if m.get("status") == "processing":
                return err("正在处理中，无法删除")
            # 删原始件
            raw = _raw_path(teacher_id, m)
            if os.path.exists(raw):
                try:
                    os.remove(raw)
                except OSError:
                    pass
            # 旧视频同步从 videos_manifest 移除
            if m.get("origin") == "video" and m.get("legacy_video_id"):
                vpath = os.path.join(get_teacher_dir(teacher_id), "videos", "videos_manifest.json")
                vman = _videos_manifest(teacher_id)
                vman = [v for v in vman if v.get("video_id") != m["legacy_video_id"]]
                with open(vpath, "w", encoding="utf-8") as f:
                    json.dump(vman, f, ensure_ascii=False, indent=2)
            # 删产出的转写（文字库随之一致）
            if m.get("transcript_id"):
                for sub in (f"{m['transcript_id']}.json",):
                    tp = os.path.join(get_teacher_dir(teacher_id), "transcripts", sub)
                    if os.path.exists(tp):
                        try:
                            os.remove(tp)
                        except OSError:
                            pass
            items = [it for it in items if it.get("material_id") != material_id]
            _save_manifest(teacher_id, items)
        return ok(None, "已删除")
