"""教师专属音色训练编排（前端一键发起）。

链路：ASR 切片转写 → GPT 微调（子进程，GPU）→ 产物落地 → 生成多参数试听样本，
教师试听后选定最自然的一款，写回 voice_profile.json 的 temperature/top_p，讲课即用。

- 训练是长任务（约 10~20 分钟，GPU），用 daemon 线程跑、进度落 train_status.json，前端轮询。
- 全局单任务锁 `_train_lock`：同一时刻只允许一个训练/试听作业，避免 GPU 显存争用。
- 试听样本走公开音频路由 /api/v1/audio/{tid}/voice/previews/{id}.wav（serve_audio 从 data/teachers 提供）。
- 合成参数只有 temperature/top_p 对 synthesize 生效，故「6 种参数」即 6 组 (temperature, top_p)。
"""
import os
import sys
import re
import json
import secrets
import threading
import subprocess
from datetime import datetime, timezone

from flask import request

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from auth import require_auth, require_role, ok, err
from teachers import get_teacher_dir, load_teacher_card

_VOICE_TRAINING_DIR = os.path.join(_project_root, "scripts", "voice_training")
_PYTHON = sys.executable  # Flask 跑在 edu 环境，子进程沿用同一解释器

# 全局单任务锁：训练/试听互斥，防 GPU 争用
_train_lock = threading.Lock()

# 6 种参数档：temperature 越高语气越活泼、表现力越强，但稳定性略降
PREVIEW_VARIANTS = [
    {"id": "v1", "label": "沉稳", "desc": "吐字清晰、节奏平稳，最稳定", "temperature": 0.25, "top_p": 0.40},
    {"id": "v2", "label": "稳重", "desc": "略带起伏、偏书面讲解", "temperature": 0.35, "top_p": 0.50},
    {"id": "v3", "label": "自然", "desc": "默认推荐、最贴近原声", "temperature": 0.45, "top_p": 0.60},
    {"id": "v4", "label": "生动", "desc": "语气更活、讲解代入感强", "temperature": 0.60, "top_p": 0.70},
    {"id": "v5", "label": "活泼", "desc": "抑扬明显、有感染力", "temperature": 0.75, "top_p": 0.80},
    {"id": "v6", "label": "饱满", "desc": "情绪最足、表现力最强", "temperature": 0.90, "top_p": 0.90},
]
_VARIANT_BY_ID = {v["id"]: v for v in PREVIEW_VARIANTS}

DEFAULT_TEST_TEXT = "同学们好，我们今天来讲一个新的知识点。只要掌握了它，后面的题目就会变得很简单。"

# 训练中/进行中的状态（前端据此继续轮询）
ACTIVE_STATES = {"queued", "asr", "finetune", "finalize", "previews"}


def _voice_dir(tid):
    return os.path.join(get_teacher_dir(tid), "voice")


def _status_path(tid):
    return os.path.join(_voice_dir(tid), "train_status.json")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _read_status(tid):
    p = _status_path(tid)
    if not os.path.exists(p):
        return {"state": "idle"}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"state": "idle"}


def _write_status(tid, **patch):
    os.makedirs(_voice_dir(tid), exist_ok=True)
    st = _read_status(tid)
    if st.get("state") == "idle":
        st = {}
    st.update(patch)
    st["updated_at"] = _now()
    tmp = _status_path(tid) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _status_path(tid))
    return st


def _voice_profile(tid):
    p = os.path.join(_voice_dir(tid), "voice_profile.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _list_samples(tid):
    d = os.path.join(get_teacher_dir(tid), "audio_samples")
    if not os.path.isdir(d):
        return []
    return [f for f in os.listdir(d) if f.lower().endswith(".wav")]


def _gen_previews(tid, test_text=None):
    """逐款用不同参数合成同一句话。返回 previews 列表；全失败抛异常。"""
    import voice_service
    import soundfile as sf

    text = (test_text or DEFAULT_TEST_TEXT).strip() or DEFAULT_TEST_TEXT
    prev_dir = os.path.join(_voice_dir(tid), "previews")
    os.makedirs(prev_dir, exist_ok=True)
    nonce = secrets.token_hex(4)  # URL 加版本号破浏览器缓存（同名文件被覆盖）

    out = []
    for v in PREVIEW_VARIANTS:
        try:
            r = voice_service.synthesize(tid, text, temperature=v["temperature"], top_p=v["top_p"])
        except Exception as e:
            print(f"[voice_train] {tid} 试听 {v['id']} 合成异常: {e}")
            r = None
        if not r:
            print(f"[voice_train] {tid} 试听 {v['id']} 无结果，跳过")
            continue
        sr, audio = r
        fpath = os.path.join(prev_dir, f"{v['id']}.wav")
        sf.write(fpath, audio, sr)
        out.append({
            "id": v["id"], "label": v["label"], "desc": v["desc"],
            "temperature": v["temperature"], "top_p": v["top_p"],
            "url": f"/api/v1/audio/{tid}/voice/previews/{v['id']}.wav?v={nonce}",
            "text": text,
        })
    if not out:
        raise RuntimeError("试听样本生成失败：该老师音色当前不可用")
    return out


def _run_training(tid, epochs):
    """三步训练（沿用 scripts/voice_training 的脚本），分阶段写进度。"""
    exp = "T" + tid.split("_")[-1]
    if _VOICE_TRAINING_DIR not in sys.path:
        sys.path.insert(0, _VOICE_TRAINING_DIR)
    import asr_to_list
    import finalize_voice

    # 1/3 ASR 切片转写
    _write_status(tid, state="asr", stage_detail="正在转写音频切片…", progress=0.05)
    asr_to_list.asr_teacher(tid, exp)

    # 2/3 GPT 微调（子进程，流式解析 epoch 进度）
    _write_status(tid, state="finetune", stage_detail="GPT 微调中（约 10~20 分钟）…", progress=0.15)
    list_path = os.path.join(_voice_dir(tid), "train", f"{exp}.list")
    wav_dir = os.path.join(get_teacher_dir(tid), "audio_samples")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [_PYTHON, os.path.join(_VOICE_TRAINING_DIR, "train_gpt.py"), exp,
           "--list", list_path, "--wav-dir", wav_dir, "--epochs", str(epochs)]
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", bufsize=1)
    last_epoch = 0
    for line in proc.stdout:
        m = re.search(r"[Ee]poch\s+(\d+)", line)
        if m:
            ep = int(m.group(1))
            if ep != last_epoch:
                last_epoch = ep
                _write_status(tid, stage_detail=f"GPT 微调中… 第 {ep}/{epochs} 轮",
                              progress=min(0.15 + 0.65 * ep / max(epochs, 1), 0.80))
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"GPT 微调失败（退出码 {proc.returncode}）")

    # 3/3 产物落地
    _write_status(tid, state="finalize", stage_detail="训练完成，正在落地音色…", progress=0.85)
    finalize_voice.finalize(tid, exp)


def _train_worker(tid, epochs, lock_held):
    try:
        _run_training(tid, epochs)
        _write_status(tid, state="previews", stage_detail="正在生成试听样本…", progress=0.92)
        previews = _gen_previews(tid)
        _write_status(tid, state="awaiting_choice", stage_detail="训练完成，请试听并选择",
                      progress=1.0, previews=previews, chosen=None, message="")
    except BaseException as e:  # 捕获 asr/finalize 里的 sys.exit(SystemExit)
        _write_status(tid, state="error", message=str(e) or repr(e))
    finally:
        if lock_held:
            _train_lock.release()


def _preview_worker(tid, test_text, lock_held):
    try:
        _write_status(tid, state="previews", stage_detail="正在生成试听样本…", progress=0.5)
        previews = _gen_previews(tid, test_text)
        _write_status(tid, state="awaiting_choice", stage_detail="请试听并选择",
                      progress=1.0, previews=previews, chosen=None, message="")
    except BaseException as e:
        _write_status(tid, state="error", message=str(e) or repr(e))
    finally:
        if lock_held:
            _train_lock.release()


def _apply_choice(tid, preview_id):
    """把选定档的 temperature/top_p 写回 voice_profile.json。"""
    variant = _VARIANT_BY_ID.get(preview_id)
    prof = _voice_profile(tid)
    if not variant or not prof:
        return None
    prof["temperature"] = variant["temperature"]
    prof["top_p"] = variant["top_p"]
    pp = os.path.join(_voice_dir(tid), "voice_profile.json")
    tmp = pp + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(prof, f, ensure_ascii=False, indent=2)
    os.replace(tmp, pp)
    return variant


def _owner_guard(tid):
    """返回 (card, None) 或 (None, error_response)。"""
    card = load_teacher_card(tid)
    if not card:
        return None, err("教师不存在", 4040, 404)
    if card.get("user_id") != request.user_id:
        return None, err("无权操作此教师", 4030, 403)
    return card, None


def register_routes(app):
    @app.route("/api/v1/teachers/<teacher_id>/voice/status", methods=["GET"])
    @require_auth
    def voice_status(teacher_id):
        prof = _voice_profile(teacher_id)
        samples = _list_samples(teacher_id)
        return ok({
            "has_voice": prof is not None and not prof.get("disabled", False),
            "has_audio_samples": len(samples) > 0,
            "n_samples": len(samples),
            "voice_id": prof.get("voice_id") if prof else None,
            "temperature": prof.get("temperature") if prof else None,
            "top_p": prof.get("top_p") if prof else None,
            "variants": PREVIEW_VARIANTS,
            "train": _read_status(teacher_id),
        })

    @app.route("/api/v1/teachers/<teacher_id>/voice/train/status", methods=["GET"])
    @require_auth
    def voice_train_status(teacher_id):
        return ok(_read_status(teacher_id))

    @app.route("/api/v1/teachers/<teacher_id>/voice/train", methods=["POST"])
    @require_role("teacher")
    def voice_train(teacher_id):
        card, e = _owner_guard(teacher_id)
        if e:
            return e
        if not _list_samples(teacher_id):
            return err("请先上传教学音频素材（需有可用的语音切片）再训练音色", 4000, 400)

        data = request.get_json(silent=True) or {}
        try:
            epochs = int(data.get("epochs", 20))
        except (TypeError, ValueError):
            epochs = 20
        epochs = max(4, min(epochs, 40))

        if not _train_lock.acquire(blocking=False):
            return err("已有音色任务正在进行，请等其完成后再试", 4290, 429)
        try:
            _write_status(teacher_id, state="queued", stage_detail="任务已排队…", progress=0.0,
                          previews=[], chosen=None, message="", started_at=_now(), epochs=epochs)
            threading.Thread(target=_train_worker, args=(teacher_id, epochs, True), daemon=True).start()
        except Exception:
            _train_lock.release()
            raise
        return ok({"state": "queued"}, "音色训练已开始，请稍候")

    @app.route("/api/v1/teachers/<teacher_id>/voice/previews", methods=["POST"])
    @require_role("teacher")
    def voice_previews(teacher_id):
        card, e = _owner_guard(teacher_id)
        if e:
            return e
        if not _voice_profile(teacher_id):
            return err("尚未训练出音色，请先训练", 4000, 400)

        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()[:120] or None

        if not _train_lock.acquire(blocking=False):
            return err("已有音色任务正在进行，请稍候", 4290, 429)
        try:
            _write_status(teacher_id, state="previews", stage_detail="正在生成试听样本…",
                          progress=0.3, previews=[], chosen=None, message="", started_at=_now())
            threading.Thread(target=_preview_worker, args=(teacher_id, text, True), daemon=True).start()
        except Exception:
            _train_lock.release()
            raise
        return ok({"state": "previews"}, "正在生成试听样本")

    @app.route("/api/v1/teachers/<teacher_id>/voice/choose", methods=["POST"])
    @require_role("teacher")
    def voice_choose(teacher_id):
        card, e = _owner_guard(teacher_id)
        if e:
            return e
        data = request.get_json(silent=True) or {}
        preview_id = data.get("preview_id", "")
        variant = _apply_choice(teacher_id, preview_id)
        if not variant:
            return err("无效的选择或音色档案缺失", 4000, 400)
        _write_status(teacher_id, state="done", chosen=preview_id,
                      stage_detail=f"已选用「{variant['label']}」音色", message="")
        return ok({
            "chosen": preview_id, "label": variant["label"],
            "temperature": variant["temperature"], "top_p": variant["top_p"],
        }, f"已选用「{variant['label']}」作为讲课音色")
