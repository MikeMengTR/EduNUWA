import json
import os
import sys
from datetime import datetime, timezone
from flask import request

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from auth import require_auth, require_role, ok, err, load_users

DATA_DIR = os.path.join(_project_root, "data")
TEACHERS_ROOT = os.path.join(DATA_DIR, "teachers")

def generate_teacher_id():
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%d")
    existing = []
    if os.path.exists(TEACHERS_ROOT):
        existing = [d for d in os.listdir(TEACHERS_ROOT) if d.startswith(f"T_{ts}_")]
    seq = len(existing) + 1
    return f"T_{ts}_{seq:03d}"

def get_teacher_dir(teacher_id):
    return os.path.join(TEACHERS_ROOT, teacher_id)

def get_card_path(teacher_id):
    return os.path.join(get_teacher_dir(teacher_id), "teacher_card.json")

def load_teacher_card(teacher_id):
    path = get_card_path(teacher_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_teacher_card(teacher_id, card):
    d = get_teacher_dir(teacher_id)
    os.makedirs(d, exist_ok=True)
    with open(get_card_path(teacher_id), "w", encoding="utf-8") as f:
        json.dump(card, f, ensure_ascii=False, indent=2)

def load_live_tags(teacher_id):
    """加载众评标签 style_tags_live.json（由进化闭环产出，与 skill 版本并行积累）。"""
    path = os.path.join(get_teacher_dir(teacher_id), "style_tags_live.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def load_skill_profile(teacher_id):
    """加载教师最新版本的 skill_profile"""
    skills_dir = os.path.join(get_teacher_dir(teacher_id), "skills")
    if not os.path.exists(skills_dir):
        return None
    # 找最大版本号，优先 full 版本
    versions = [d for d in os.listdir(skills_dir) if d.startswith("v")]
    if not versions:
        return None
    def _version_sort_key(v):
        # v2_full > v2 > v1; 名字里带 full 的优先
        num = int(v.split("_")[0][1:]) if v[1:].split("_")[0].isdigit() else 0
        is_full = 1 if "full" in v else 0
        return (num, is_full)
    versions.sort(key=_version_sort_key, reverse=True)
    for ver in versions:
        profile_path = os.path.join(skills_dir, ver, "skill_profile.json")
        if os.path.exists(profile_path):
            with open(profile_path, "r", encoding="utf-8") as f:
                return json.load(f)
    return None

def load_skill_md(teacher_id):
    """加载教师最新版本的 TeacherSkill.md"""
    skills_dir = os.path.join(get_teacher_dir(teacher_id), "skills")
    if not os.path.exists(skills_dir):
        return None
    versions = [d for d in os.listdir(skills_dir) if d.startswith("v")]
    versions.sort(key=lambda v: int(v[1:]) if v[1:].isdigit() else 0, reverse=True)
    for ver in versions:
        md_path = os.path.join(skills_dir, ver, "TeacherSkill.md")
        if os.path.exists(md_path):
            with open(md_path, "r", encoding="utf-8") as f:
                return f.read()
    return None

def _load_segment_map(teacher_id):
    """构建 {seg_id: {transcript_id,start,end,text}}，seg_id 前缀规则与 distill._gather_transcripts 一致
    （单文件无前缀，多文件 f{idx}_），供风格标签 evidence 回链到真实转写句子。"""
    transcripts_dir = os.path.join(get_teacher_dir(teacher_id), "transcripts")
    segmap = {}
    if not os.path.exists(transcripts_dir):
        return segmap
    files = sorted([f for f in os.listdir(transcripts_dir)
                    if f.endswith(".json") and not f.startswith("_")])
    for idx, f in enumerate(files):
        try:
            with open(os.path.join(transcripts_dir, f), "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except (json.JSONDecodeError, OSError):
            continue
        trid = data.get("transcript_id", f[:-5])
        prefix = "" if len(files) == 1 else f"f{idx}_"
        for i, seg in enumerate(data.get("segments", [])):
            sid = prefix + seg.get("segment_id", f"seg_{i+1:04d}")
            segmap[sid] = {"seg_id": sid, "transcript_id": trid,
                           "start": seg.get("start"), "end": seg.get("end"),
                           "text": seg.get("text", "")}
    return segmap


def _enrich_style_tags(style_tags, segmap):
    """给每个风格标签附 evidence_text：把 evidence 里的 seg_id 解析成真实句子。"""
    out = []
    for t in style_tags or []:
        if isinstance(t, dict):
            t = dict(t)
            t["evidence_text"] = [segmap[e] for e in (t.get("evidence") or []) if e in segmap]
            out.append(t)
        else:
            out.append(t)
    return out


def _normalize_subject(card):
    """subject 可能是字符串或数组，统一转为字符串"""
    s = card.get("subject", "")
    if isinstance(s, list):
        return s[0] if s else ""
    return s

def list_all_teachers():
    if not os.path.exists(TEACHERS_ROOT):
        return []
    teachers = []
    for tid in os.listdir(TEACHERS_ROOT):
        card = load_teacher_card(tid)
        if card:
            card["subject"] = _normalize_subject(card)  # 统一为字符串
            profile = load_skill_profile(tid)
            if profile:
                # v2: style_tags（开放标签）替代 v1 的 fingerprint + tags
                style_tags = profile.get("style_tags", [])
                card["tags"] = [t.get("text", t) if isinstance(t, dict) else str(t) for t in style_tags]
                card["style_tags"] = style_tags  # 原始数据给 M3 匹配用
                card["base_metrics"] = profile.get("base_metrics", {})
                card["pedagogy"] = profile.get("pedagogy")
                card["quality"] = profile.get("quality")
                card["skill_version"] = profile.get("version")
                card["grade"] = profile.get("quality", {}).get("overall_grade", "NA")
                # 从 base_metrics 构建 fingerprint 显示
                bm = profile.get("base_metrics", {})
                if bm:
                    card["fingerprint"] = {
                        k: {"value": v.get("value", 0) / 300.0 if k == "speech_rate" else min(v.get("value", 0) / 10.0, 1.0),
                            "confidence": 0.8}
                        for k, v in bm.items()
                    }
            live = load_live_tags(tid)
            if live and live.get("tags"):
                card["live_tags"] = live["tags"]
            teachers.append(card)
    return teachers

def register_routes(app):
    @app.route("/api/v1/teachers", methods=["GET"])
    @require_auth
    def list_teachers():
        role = request.args.get("role", "")
        subject = request.args.get("subject", "").lower()
        search = request.args.get("search", "").lower()

        all_t = list_all_teachers()
        if role == "teacher":
            all_t = [t for t in all_t if t.get("user_id") == request.user_id]
        else:
            # 学生发现页：隐藏被平台监控台「下架」的教师（hidden=True）
            all_t = [t for t in all_t if not t.get("hidden")]
        if subject:
            all_t = [t for t in all_t if subject in t.get("subject", "").lower()]
        if search:
            all_t = [t for t in all_t
                     if search in t.get("display_name", "").lower()
                     or search in t.get("real_name", "").lower()
                     or search in t.get("bio", "").lower()]

        all_t.sort(key=lambda t: t.get("created_at", ""), reverse=True)
        return ok(all_t)

    @app.route("/api/v1/teachers/<teacher_id>", methods=["GET"])
    @require_auth
    def get_teacher(teacher_id):
        card = load_teacher_card(teacher_id)
        if not card:
            return err("教师不存在", 4040, 404)
        card["subject"] = _normalize_subject(card)
        profile = load_skill_profile(teacher_id)
        if profile:
            style_tags = profile.get("style_tags", [])
            card["tags"] = [t.get("text", t) if isinstance(t, dict) else str(t) for t in style_tags]
            card["style_tags"] = style_tags
            card["base_metrics"] = profile.get("base_metrics", {})
            card["pedagogy"] = profile.get("pedagogy")
            card["quality"] = profile.get("quality")
            bm = profile.get("base_metrics", {})
            if bm:
                card["fingerprint"] = {
                    k: {"value": v.get("value", 0) / 300.0 if k == "speech_rate" else min(v.get("value", 0) / 10.0, 1.0),
                        "confidence": 0.8}
                    for k, v in bm.items()
                }
        live = load_live_tags(teacher_id)
        if live and live.get("tags"):
            card["live_tags"] = live["tags"]
        # 附加上视频列表
        vmanifest_path = os.path.join(get_teacher_dir(teacher_id), "videos", "videos_manifest.json")
        if os.path.exists(vmanifest_path):
            with open(vmanifest_path, "r", encoding="utf-8") as f:
                card["videos"] = json.load(f)
        return ok(card)

    @app.route("/api/v1/teachers/<teacher_id>/skill", methods=["GET"])
    @require_auth
    def get_teacher_skill(teacher_id):
        card = load_teacher_card(teacher_id)
        if not card:
            return err("教师不存在", 4040, 404)
        profile = load_skill_profile(teacher_id)
        skill_md = load_skill_md(teacher_id)
        if profile and profile.get("style_tags"):
            profile = dict(profile)
            profile["style_tags"] = _enrich_style_tags(profile["style_tags"], _load_segment_map(teacher_id))
        return ok({
            "teacher_id": teacher_id,
            "display_name": card.get("display_name"),
            "profile": profile,
            "skill_md": skill_md,
        })

    @app.route("/api/v1/teachers/<teacher_id>/transcripts", methods=["GET"])
    @require_auth
    def get_teacher_transcripts(teacher_id):
        transcripts_dir = os.path.join(get_teacher_dir(teacher_id), "transcripts")
        if not os.path.exists(transcripts_dir):
            return ok([])
        files = [f for f in os.listdir(transcripts_dir) if f.endswith(".json") and not f.startswith("_")]
        transcripts = []
        for f in sorted(files):
            with open(os.path.join(transcripts_dir, f), "r", encoding="utf-8") as fp:
                data = json.load(fp)
            segs = data.get("segments", [])
            q = data.get("asr_quality", {}) or {}
            transcripts.append({
                "transcript_id": data.get("transcript_id", f[:-5]),
                "segments_count": len(segs),
                "source_audio": data.get("source_audio", ""),
                "source_file": data.get("source_file", ""),
                "asr_backend": data.get("asr_backend", ""),
                "duration": segs[-1].get("end") if segs else 0,
                "estimated_cer": q.get("estimated_cer"),
                "low_confidence_segments": q.get("low_confidence_segments"),
                "refined": q.get("refined"),
            })
        return ok(transcripts)

    @app.route("/api/v1/teachers/<teacher_id>/transcripts/<transcript_id>", methods=["GET"])
    @require_auth
    def get_transcript_detail(teacher_id, transcript_id):
        """单份转写全文（segments + asr_quality），供教师审阅/核对。只读。"""
        safe = os.path.basename(transcript_id)
        tdir = os.path.join(get_teacher_dir(teacher_id), "transcripts")
        target = None
        if os.path.isdir(tdir):
            for f in os.listdir(tdir):
                if f.endswith(".json") and not f.startswith("_") and f[:-5] == safe:
                    target = os.path.join(tdir, f)
                    break
        if not target:
            return err("转写不存在", 4040, 404)
        with open(target, "r", encoding="utf-8") as fp:
            return ok(json.load(fp))

    @app.route("/api/v1/teachers/<teacher_id>/skills", methods=["GET"])
    @require_auth
    def list_skill_versions(teacher_id):
        """列出该教师的所有 Skill 版本（含生成时间、标签数），供版本历史查看。只读。"""
        skills_dir = os.path.join(get_teacher_dir(teacher_id), "skills")
        versions = []
        if os.path.isdir(skills_dir):
            for d in os.listdir(skills_dir):
                pp = os.path.join(skills_dir, d, "skill_profile.json")
                if not os.path.exists(pp):
                    continue
                try:
                    with open(pp, "r", encoding="utf-8") as fp:
                        prof = json.load(fp)
                except (json.JSONDecodeError, OSError):
                    continue
                versions.append({
                    "version": prof.get("version", 0),
                    "dir": d,
                    "generated_at": prof.get("generated_at"),
                    "style_tags_count": len(prof.get("style_tags", [])),
                    "has_md": os.path.exists(os.path.join(skills_dir, d, "TeacherSkill.md")),
                })
        versions.sort(key=lambda v: (v.get("version") or 0, v.get("dir", "")), reverse=True)
        return ok(versions)

    @app.route("/api/v1/teachers/<teacher_id>/skills/<version_dir>", methods=["GET"])
    @require_auth
    def get_skill_version(teacher_id, version_dir):
        """取某个 Skill 版本的 TeacherSkill.md 全文 + profile（风格标签已附 evidence 句子）。只读。"""
        safe = os.path.basename(version_dir)
        vdir = os.path.join(get_teacher_dir(teacher_id), "skills", safe)
        pp = os.path.join(vdir, "skill_profile.json")
        if not os.path.exists(pp):
            return err("版本不存在", 4040, 404)
        with open(pp, "r", encoding="utf-8") as fp:
            prof = json.load(fp)
        mp = os.path.join(vdir, "TeacherSkill.md")
        skill_md = None
        if os.path.exists(mp):
            with open(mp, "r", encoding="utf-8") as fp:
                skill_md = fp.read()
        if prof.get("style_tags"):
            prof["style_tags"] = _enrich_style_tags(prof["style_tags"], _load_segment_map(teacher_id))
        return ok({"version": prof.get("version"), "dir": safe, "skill_md": skill_md, "profile": prof})

    @app.route("/api/v1/teachers", methods=["POST"])
    @require_role("teacher")
    def create_teacher_card():
        data = request.json
        real_name = data.get("real_name", "").strip()
        display_name = data.get("display_name", "").strip()
        subject = data.get("subject", "").strip()
        bio = data.get("bio", "").strip()
        system_prompt = data.get("system_prompt", "").strip()

        if not real_name:
            return err("教师姓名不能为空")
        if not display_name:
            display_name = real_name + "老师"

        all_t = list_all_teachers()
        existing = next((t for t in all_t if t.get("user_id") == request.user_id), None)
        if existing:
            return err("已有教师卡片，请使用编辑功能", 4090, 409)

        teacher_id = generate_teacher_id()
        voice_id = data.get("voice_id", "") or "songhao"

        card = {
            "teacher_id": teacher_id,
            "user_id": request.user_id,
            "real_name": real_name,
            "display_name": display_name,
            "subject": subject,
            "bio": bio,
            "system_prompt": system_prompt,
            "avatar_url": data.get("avatar_url"),
            "voice_id": voice_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        save_teacher_card(teacher_id, card)
        return ok(card, "教师卡片创建成功")

    @app.route("/api/v1/teachers/<teacher_id>", methods=["PUT"])
    @require_role("teacher")
    def update_teacher_card(teacher_id):
        card = load_teacher_card(teacher_id)
        if not card:
            return err("教师不存在", 4040, 404)
        if card.get("user_id") != request.user_id:
            return err("无权修改此教师", 4030, 403)

        data = request.json
        for field in ["real_name", "display_name", "subject", "bio", "system_prompt", "avatar_url", "voice_id"]:
            if field in data:
                card[field] = data[field].strip() if isinstance(data[field], str) else data[field]

        save_teacher_card(teacher_id, card)
        return ok(card, "更新成功")

    @app.route("/api/v1/teachers/<teacher_id>/avatar", methods=["POST"])
    @require_role("teacher")
    def upload_teacher_avatar(teacher_id):
        """教师上传/更换头像图片。存到 data/teachers/{tid}/avatar/ 并写回 card.avatar。
        单帧上传：pixel_url 用于显示、images 仅一帧（讲课无口型张口帧，仅静态头像）。"""
        card = load_teacher_card(teacher_id)
        if not card:
            return err("教师不存在", 4040, 404)
        if card.get("user_id") != request.user_id:
            return err("无权修改此教师", 4030, 403)

        f = request.files.get("file")
        if not f or not f.filename:
            return err("未收到头像文件")
        ext = os.path.splitext(f.filename)[1].lower().lstrip(".")
        if ext not in {"png", "jpg", "jpeg", "webp", "gif"}:
            return err("仅支持 png / jpg / webp / gif 图片")
        blob = f.read()
        if len(blob) > 5 * 1024 * 1024:
            return err("图片不能超过 5MB")

        avatar_dir = os.path.join(get_teacher_dir(teacher_id), "avatar")
        os.makedirs(avatar_dir, exist_ok=True)
        # 唯一文件名避免浏览器缓存旧图
        fname = f"avatar_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.{ext}"
        with open(os.path.join(avatar_dir, fname), "wb") as out:
            out.write(blob)

        url = f"/api/v1/avatar/{teacher_id}/{fname}"
        card["avatar"] = {"pixel_url": url, "images": [fname]}
        card["avatar_url"] = url
        save_teacher_card(teacher_id, card)
        return ok({"avatar_url": url, "avatar": card["avatar"]}, "头像已更新")

    @app.route("/api/v1/my/teacher", methods=["GET"])
    @require_role("teacher")
    def my_teacher():
        all_t = list_all_teachers()
        card = next((t for t in all_t if t.get("user_id") == request.user_id), None)
        if not card:
            return err("还未创建教师卡片", 4040, 404)
        return ok(card)

    # ---- M3 匹配引擎 ----
    @app.route("/api/v1/match", methods=["POST"])
    @require_auth
    def match_teachers():
        """M3 风格匹配：学生用自然语言描述需求，LLM 返回排序结果"""
        data = request.json
        query = data.get("query", "").strip()
        if not query:
            return err("请描述你想要的教师风格")

        try:
            from modules.M3_catalog.matching_engine import match_teachers as m3_match
            # 下架教师不参与推荐匹配
            all_teachers = [t for t in list_all_teachers() if not t.get("hidden")]
            if not all_teachers:
                return err("暂无可用教师", 4040, 404)

            # 转换为 M3 matcher 需要的字段格式
            m3_teachers = []
            for t in all_teachers:
                style_tags_raw = t.get("style_tags", [])
                bm_raw = t.get("base_metrics", {})
                m3_teachers.append({
                    "teacher_id": t["teacher_id"],
                    "teacher_name": t.get("display_name", t.get("real_name", "")),
                    "subject": t.get("subject", ""),
                    "grade": t.get("grade", "NA"),
                    "style_tags": [s.get("text", str(s)) if isinstance(s, dict) else str(s) for s in style_tags_raw],
                    "crowd_tags": [{"text": ct.get("text", ""), "support": ct.get("support", 1)}
                                   for ct in t.get("live_tags", []) if isinstance(ct, dict) and ct.get("text")],
                    "base_metrics": {k: (v.get("label", str(v.get("value", ""))) if isinstance(v, dict) else str(v))
                                     for k, v in bm_raw.items()},
                })

            result = m3_match(query, m3_teachers)
            # 统一输出格式：rankings（前端用）+ display_name
            rankings = []
            for r in result.get("results", []):
                orig = next((t for t in all_teachers if t["teacher_id"] == r["teacher_id"]), None)
                rankings.append({
                    "teacher_id": r["teacher_id"],
                    "display_name": orig.get("display_name", r.get("teacher_name", "")) if orig else r.get("teacher_name", ""),
                    "subject": r.get("subject", ""),
                    "semantic_fit": r.get("semantic_fit"),
                    "reason": r.get("reason", ""),
                    "matched_tags": r.get("matched_tags", []),
                })

            # 进化闭环：落盘本次推荐事件（不可变），match_id 返回给前端随反馈回传
            match_id = None
            try:
                from match_log import create_match_record
                candidates = [{
                    "teacher_id": t["teacher_id"],
                    "skill_version": t.get("skill_version"),
                    "n_auto_tags": len(t.get("style_tags", [])),
                    "n_crowd_tags": len(t.get("live_tags", [])),
                } for t in all_teachers]
                match_id = create_match_record(request.user_id, query, candidates, rankings)
            except Exception:
                pass  # 落盘失败不影响推荐结果返回

            return ok({"query": query, "match_id": match_id, "rankings": rankings})
        except ImportError as e:
            return err(f"M3 模块未加载: {e}", 5030, 503)
        except Exception as e:
            return err(f"匹配失败: {e}", 5000, 500)
