"""平台监控台（只读）后端蓝图。

定位：给运营/课题方一个俯瞰全平台数据的只读后台。鉴权与现有「师/生」账号体系
完全隔离——靠 .env 里的 PLATFORM_KEY（请求头 X-Platform-Key）一个独立口令进入。

红线（参考 media_library.py 那条只读零依赖约定）：
- 本文件**只读**，绝不写 data/；
- **不 import** M1–M5 重模块（torch/funasr 等），只 import 轻量的 auth（取 ok/err/
  load_users/DATA_DIR）+ 标准库，自己扫 data/ 聚合，避免循环依赖与启动变慢。

所有遍历容错：单个坏 JSON / 缺字段跳过，不让一条脏数据搞崩整个看板。
"""
import os
import re
import json
import hmac
from collections import Counter, defaultdict
from functools import wraps

from flask import request

import auth
from auth import ok, err

DATA_DIR = auth.DATA_DIR
TEACHERS_DIR = os.path.join(DATA_DIR, "teachers")
SESSIONS_DIR = os.path.join(DATA_DIR, "sessions")
FEEDBACK_DIR = os.path.join(DATA_DIR, "feedback")
MATCH_LOG_DIR = os.path.join(DATA_DIR, "match_log")
CONVERSATIONS_FILE = os.path.join(DATA_DIR, "conversations.json")
MEDIA_INDEX = os.path.join(DATA_DIR, "media_library", "index.json")

# 无配置时给一个默认口令，仅为本地 demo 兜底；生产请在 .env 配 PLATFORM_KEY。
DEFAULT_KEY = "edunuwa-admin"

_VER_RE = re.compile(r"^v(\d+)$")
_SES_DATE_RE = re.compile(r"^SES_(\d{8})")


# ────────────────────────────── 鉴权 ──────────────────────────────
def _platform_key():
    return os.environ.get("PLATFORM_KEY") or DEFAULT_KEY


def require_platform_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        provided = request.headers.get("X-Platform-Key", "")
        # 常量时间比较，避免口令长度/前缀被旁路探测
        if not provided or not hmac.compare_digest(str(provided), str(_platform_key())):
            return err("平台口令无效", 4030, 403)
        return f(*args, **kwargs)
    return decorated


# ────────────────────────────── 通用读取 ──────────────────────────────
def _load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except Exception:
        return default


def _listdir(path):
    try:
        return os.listdir(path)
    except Exception:
        return []


def _teacher_ids():
    return sorted(d for d in _listdir(TEACHERS_DIR)
                  if os.path.isdir(os.path.join(TEACHERS_DIR, d)))


def _card(tid):
    return _load_json(os.path.join(TEACHERS_DIR, tid, "teacher_card.json")) or {}


def _teacher_name(tid, card=None):
    if not tid:
        return None
    card = card if card is not None else _card(tid)
    return card.get("display_name") or card.get("real_name") or tid


def _subject_list(card):
    """subject 字段历史上既可能是字符串也可能是列表，统一成字符串列表。"""
    s = card.get("subject")
    if isinstance(s, list):
        return [str(x) for x in s if x]
    return [str(s)] if s else []


def _subject_str(card):
    return " / ".join(_subject_list(card)) or None


def _latest_skill_dir(tid):
    """优先取最高的 v{n} 版本（带 skill_profile.json）；退回任意含 profile 的目录。"""
    sdir = os.path.join(TEACHERS_DIR, tid, "skills")
    if not os.path.isdir(sdir):
        return None
    best, best_n = None, -1
    for name in _listdir(sdir):
        m = _VER_RE.match(name)
        if m and int(m.group(1)) > best_n and \
                os.path.exists(os.path.join(sdir, name, "skill_profile.json")):
            best_n, best = int(m.group(1)), name
    if best:
        return os.path.join(sdir, best)
    for name in sorted(_listdir(sdir)):
        if os.path.exists(os.path.join(sdir, name, "skill_profile.json")):
            return os.path.join(sdir, name)
    return None


def _latest_profile(tid):
    d = _latest_skill_dir(tid)
    return _load_json(os.path.join(d, "skill_profile.json")) if d else None


def _skill_versions(tid):
    sdir = os.path.join(TEACHERS_DIR, tid, "skills")
    out = []
    for name in sorted(_listdir(sdir)):
        prof = _load_json(os.path.join(sdir, name, "skill_profile.json"))
        if prof is None:
            continue
        out.append({
            "dir": name,
            "version": prof.get("version"),
            "generated_at": prof.get("generated_at"),
            "grade": (prof.get("quality") or {}).get("overall_grade"),
            "n_tags": len(prof.get("tags") or []),
        })
    return out


def _all_profiles(tid):
    sdir = os.path.join(TEACHERS_DIR, tid, "skills")
    out = []
    for name in sorted(_listdir(sdir)):
        prof = _load_json(os.path.join(sdir, name, "skill_profile.json"))
        if prof:
            out.append(prof)
    return out


def _best_style_tags(tid, latest_prof=None):
    """取最稳健的 style_tags：优先最新版本；为空则回退到任一非空版本
    （示范教师01最新 v2 的 tags=[] 但 v1 有，靠这个回退取到）。"""
    tags = (latest_prof or {}).get("style_tags") or []
    if tags:
        return tags
    for prof in _all_profiles(tid):
        if prof.get("style_tags"):
            return prof["style_tags"]
    return []


def _style_line(style_tags, top=3):
    """一句话风格：取 confidence 最高的前几个标签拼接。"""
    ts = [t for t in (style_tags or []) if isinstance(t, dict) and t.get("text")]
    ts.sort(key=lambda t: t.get("confidence") or 0, reverse=True)
    return " · ".join(t["text"] for t in ts[:top])


def _teacher_courses(tid):
    cdir = os.path.join(TEACHERS_DIR, tid, "courses")
    out = []
    for cid in sorted(_listdir(cdir)):
        cj = _load_json(os.path.join(cdir, cid, "course.json"))
        if cj:
            out.append(cj)
    return out


def _transcripts(tid):
    tdir = os.path.join(TEACHERS_DIR, tid, "transcripts")
    out = []
    for f in sorted(_listdir(tdir)):
        if not f.endswith(".json"):
            continue
        data = _load_json(os.path.join(tdir, f)) or {}
        # 转写文件是 {TR_xxx: {course, school, transcript, ...}} 的单键包裹
        for key, val in (data.items() if isinstance(data, dict) else []):
            if not isinstance(val, dict):
                continue
            text = val.get("transcript") or ""
            out.append({
                "id": key,
                "file": f,
                "course": val.get("course"),
                "school": val.get("school"),
                "chars": len(text),
                "segments": len(val.get("segments") or []),
            })
    return out


def _teacher_feedback(tid):
    return _load_json(os.path.join(FEEDBACK_DIR, tid + ".json"), []) or []


def _all_feedback():
    out = []
    for f in _listdir(FEEDBACK_DIR):
        if not f.endswith(".json"):
            continue
        tid = f[:-5]
        for item in (_load_json(os.path.join(FEEDBACK_DIR, f), []) or []):
            if isinstance(item, dict):
                row = dict(item)
                row["teacher_id"] = tid
                out.append(row)
    return out


def _all_matches():
    out = []
    for month in _listdir(MATCH_LOG_DIR):
        mdir = os.path.join(MATCH_LOG_DIR, month)
        if not os.path.isdir(mdir):
            continue
        for f in _listdir(mdir):
            if f.endswith(".json"):
                rec = _load_json(os.path.join(mdir, f))
                if rec:
                    out.append(rec)
    return out


def _conversations():
    return _load_json(CONVERSATIONS_FILE, {}) or {}


def _split_conv_key(key):
    """会话记忆 key 形如 `<16位学生id>_T_<日期>_<序号>`；学生 id 无下划线，
    教师 id 以 T_ 开头，故首个下划线即分界。"""
    parts = key.split("_", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return key, None


def _bump_last(entry, ts):
    if ts and (entry["last_active"] is None or ts > entry["last_active"]):
        entry["last_active"] = ts


def _student_index():
    """一次性聚合每个学生的活跃度派生指标，供 users 列表与下钻共用。"""
    idx = defaultdict(lambda: {
        "questions": 0, "conversations": 0, "teachers": set(),
        "feedback": 0, "matches": 0, "last_active": None,
    })
    for key, val in _conversations().items():
        uid, tid = _split_conv_key(key)
        e = idx[uid]
        e["conversations"] += 1
        if tid:
            e["teachers"].add(tid)
        for m in (val.get("messages") or []):
            if m.get("role") == "user":
                e["questions"] += 1
    for fb in _all_feedback():
        uid = fb.get("user_id")
        if uid:
            idx[uid]["feedback"] += 1
            _bump_last(idx[uid], fb.get("created_at"))
    for rec in _all_matches():
        uid = rec.get("user_id")
        if uid:
            idx[uid]["matches"] += 1
            _bump_last(idx[uid], rec.get("created_at"))
    return idx


def _session_date(name):
    m = _SES_DATE_RE.match(name)
    if m:
        s = m.group(1)
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return None


def _activity_series(feedback, matches, session_dirs, days=21):
    """近 N 天平台活跃（反馈 + 推荐 + 课堂会话合计），按天聚合。"""
    counter = Counter()
    for fb in feedback:
        ts = (fb.get("created_at") or "")[:10]
        if ts:
            counter[ts] += 1
    for rec in matches:
        ts = (rec.get("created_at") or "")[:10]
        if ts:
            counter[ts] += 1
    for name in session_dirs:
        d = _session_date(name)
        if d:
            counter[d] += 1
    ordered = sorted(counter.items())
    return [{"date": d, "value": v} for d, v in ordered[-days:]]


# ────────────────────────────── 路由 ──────────────────────────────
def register_routes(app):

    @app.route("/api/v1/platform/auth", methods=["POST"])
    def platform_auth():
        data = request.json or {}
        key = (data.get("key") or "").strip()
        if not key or not hmac.compare_digest(str(key), str(_platform_key())):
            return err("平台口令无效", 4030, 403)
        return ok({"ok": True}, "口令正确")

    @app.route("/api/v1/platform/overview", methods=["GET"])
    @require_platform_key
    def platform_overview():
        users = auth.load_users()
        n_students = sum(1 for u in users if u.get("role") == "student")
        n_teachers_u = sum(1 for u in users if u.get("role") == "teacher")

        tids = _teacher_ids()
        cards = [_card(t) for t in tids]

        all_fb = _all_feedback()
        ratings = [f["rating"] for f in all_fb
                   if isinstance(f.get("rating"), (int, float))]
        avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else 0

        session_dirs = [d for d in _listdir(SESSIONS_DIR)
                        if os.path.isdir(os.path.join(SESSIONS_DIR, d))]

        course_count = chapter_count = 0
        for t in tids:
            for c in _teacher_courses(t):
                course_count += 1
                chapter_count += len(c.get("chapters") or [])

        transcript_count = sum(len(_transcripts(t)) for t in tids)
        matches = _all_matches()
        media = _load_json(MEDIA_INDEX, {"images": []}) or {"images": []}
        imgs = media.get("images") or []

        subj = Counter()
        for c in cards:
            for s in _subject_list(c):
                subj[s] += 1
        rdist = Counter(int(r) for r in ratings)

        return ok({
            "totals": {
                "users": len(users),
                "students": n_students,
                "teacher_accounts": n_teachers_u,
                "teacher_profiles": len(tids),
                "sessions": len(session_dirs),
                "courses": course_count,
                "chapters": chapter_count,
                "transcripts": transcript_count,
                "feedback": len(all_fb),
                "matches": len(matches),
                "media_images": len(imgs),
            },
            "avg_rating": avg_rating,
            "role_dist": [
                {"label": "学生", "value": n_students},
                {"label": "教师", "value": n_teachers_u},
            ],
            "subject_dist": [{"label": k, "value": v}
                             for k, v in subj.most_common()],
            "rating_dist": [{"label": f"{r}★", "value": rdist.get(r, 0)}
                            for r in range(5, 0, -1)],
            "activity": _activity_series(all_fb, matches, session_dirs),
        })

    @app.route("/api/v1/platform/users", methods=["GET"])
    @require_platform_key
    def platform_users():
        role = (request.args.get("role") or "").strip()
        q = (request.args.get("q") or "").strip().lower()

        users = auth.load_users()
        idx = _student_index()
        # user_id -> teacher_id（教师账号关联到其教师卡片）
        u2t = {}
        for t in _teacher_ids():
            uid = _card(t).get("user_id")
            if uid:
                u2t[uid] = t

        rows = []
        for u in users:
            if role and u.get("role") != role:
                continue
            if q and q not in (u.get("username", "").lower()):
                continue
            row = {
                "id": u.get("id"),
                "username": u.get("username"),
                "role": u.get("role"),
                "teacher_id": u2t.get(u.get("id")),
            }
            if u.get("role") == "student":
                a = idx.get(u.get("id"))
                if a:
                    row["activity"] = {
                        "questions": a["questions"],
                        "conversations": a["conversations"],
                        "teachers_consulted": len(a["teachers"]),
                        "feedback": a["feedback"],
                        "matches": a["matches"],
                        "last_active": a["last_active"],
                    }
                else:
                    row["activity"] = {
                        "questions": 0, "conversations": 0,
                        "teachers_consulted": 0, "feedback": 0,
                        "matches": 0, "last_active": None,
                    }
            rows.append(row)

        # 学生按提问数倒序、教师按用户名，方便一眼看活跃头部
        rows.sort(key=lambda r: (
            r["role"] != "student",
            -(r.get("activity", {}).get("questions", 0) if r["role"] == "student" else 0),
            r.get("username") or "",
        ))
        return ok({"users": rows, "total": len(rows)})

    @app.route("/api/v1/platform/students/<uid>", methods=["GET"])
    @require_platform_key
    def platform_student(uid):
        users = auth.load_users()
        user = next((u for u in users if u.get("id") == uid), None)

        threads = []
        for key, val in _conversations().items():
            kuid, tid = _split_conv_key(key)
            if kuid != uid:
                continue
            msgs = val.get("messages") or []
            questions = [m.get("content") for m in msgs if m.get("role") == "user"]
            threads.append({
                "teacher_id": tid,
                "teacher_name": _teacher_name(tid),
                "message_count": len(msgs),
                "questions": questions,
            })

        feedback = []
        for fb in _all_feedback():
            if fb.get("user_id") == uid:
                row = dict(fb)
                row["teacher_name"] = _teacher_name(fb.get("teacher_id"))
                feedback.append(row)
        feedback.sort(key=lambda f: f.get("created_at") or "", reverse=True)

        matches = []
        for rec in _all_matches():
            if rec.get("user_id") != uid:
                continue
            rankings = rec.get("rankings") or []
            matches.append({
                "match_id": rec.get("match_id"),
                "query": rec.get("query"),
                "created_at": rec.get("created_at"),
                "top": rankings[0] if rankings else None,
            })
        matches.sort(key=lambda m: m.get("created_at") or "", reverse=True)

        return ok({
            "user": {"id": uid,
                     "username": (user or {}).get("username"),
                     "role": (user or {}).get("role")},
            "threads": threads,
            "feedback": feedback,
            "matches": matches,
            "summary": {
                "questions": sum(len(t["questions"]) for t in threads),
                "teachers_consulted": len({t["teacher_id"] for t in threads if t["teacher_id"]}),
                "feedback": len(feedback),
                "matches": len(matches),
            },
        })

    @app.route("/api/v1/platform/teachers", methods=["GET"])
    @require_platform_key
    def platform_teachers():
        users = auth.load_users()
        uid2name = {u.get("id"): u.get("username")
                    for u in users if u.get("role") == "teacher"}
        rows = []
        for tid in _teacher_ids():
            card = _card(tid)
            prof = _latest_profile(tid)
            style_tags = _best_style_tags(tid, prof)
            fb = _teacher_feedback(tid)
            ratings = [f["rating"] for f in fb
                       if isinstance(f.get("rating"), (int, float))]
            live = _load_json(os.path.join(TEACHERS_DIR, tid, "style_tags_live.json")) or {}
            courses = _teacher_courses(tid)
            rows.append({
                "teacher_id": tid,
                "display_name": card.get("display_name") or tid,
                "real_name": card.get("real_name"),
                "subject": _subject_str(card),
                "school": card.get("school"),
                "avatar": (card.get("avatar") or {}).get("pixel_url"),
                "avg_rating": (card.get("stats") or {}).get("avg_rating",
                               round(sum(ratings) / len(ratings), 2) if ratings else 0),
                "feedback_count": len(fb),
                "style_line": _style_line(style_tags),
                "grade": (prof.get("quality") or {}).get("overall_grade") if prof else None,
                "skill_versions": len(_skill_versions(tid)),
                "course_count": len(courses),
                "transcript_count": len(_transcripts(tid)),
                "crowd_tags": len(live.get("tags") or []),
                "has_voice": os.path.exists(
                    os.path.join(TEACHERS_DIR, tid, "voice", "voice_profile.json")),
                "hidden": bool(card.get("hidden")),
                "account_username": uid2name.get(card.get("user_id")),
            })
        rows.sort(key=lambda r: (-r["feedback_count"], r["teacher_id"]))
        return ok({"teachers": rows, "total": len(rows)})

    @app.route("/api/v1/platform/teachers/<tid>", methods=["GET"])
    @require_platform_key
    def platform_teacher(tid):
        card = _card(tid)
        if not card:
            return err("教师不存在", 4040, 404)
        card["subject"] = _subject_str(card)  # 列表/字符串统一成展示字符串
        # 风格速写 / 指纹与学生端对齐：复用 teachers.load_skill_profile（优先 _full 版本），
        # 把 base_metrics/pedagogy/style_tags/tags/live_tags 富化进 card，让前端直接喂给
        # 共享组件 StyleProfile（buildRadar/buildSketch/buildCloudWords），两端口径完全一致。
        import teachers as T
        prof = T.load_skill_profile(tid)
        style_tags = (prof or {}).get("style_tags") or _best_style_tags(tid, prof)
        live = _load_json(os.path.join(TEACHERS_DIR, tid, "style_tags_live.json")) or {}
        card["style_tags"] = style_tags
        card["tags"] = [(t.get("text", t) if isinstance(t, dict) else str(t)) for t in style_tags]
        card["base_metrics"] = (prof or {}).get("base_metrics")
        card["pedagogy"] = (prof or {}).get("pedagogy")
        card["live_tags"] = live.get("tags") or []
        fb = _teacher_feedback(tid)
        for f in fb:
            f["user_name"] = next(
                (u.get("username") for u in auth.load_users()
                 if u.get("id") == f.get("user_id")), None)
        fb.sort(key=lambda f: f.get("created_at") or "", reverse=True)
        evo = _load_json(os.path.join(TEACHERS_DIR, tid, "evolution", "state.json")) or {}
        ratings = [f["rating"] for f in fb if isinstance(f.get("rating"), (int, float))]
        rdist = Counter(int(r) for r in ratings)
        acct = next((u for u in auth.load_users()
                     if u.get("id") == card.get("user_id") and u.get("role") == "teacher"), None)
        return ok({
            "card": card,
            "account": {"username": acct["username"], "user_id": acct["id"]} if acct else None,
            "skill_versions": _skill_versions(tid),
            "courses": [{
                "course_id": c.get("course_id"),
                "title": c.get("title"),
                "subject": c.get("subject"),
                "published": c.get("published"),
                "status": c.get("status"),
                "created_at": c.get("created_at"),
                "chapters": len(c.get("chapters") or []),
                "duration_sec": sum((ch.get("duration_sec") or 0)
                                    for ch in (c.get("chapters") or [])),
            } for c in _teacher_courses(tid)],
            "transcripts": _transcripts(tid),
            "feedback": fb,
            "rating_dist": [{"label": f"{r}★", "value": rdist.get(r, 0)}
                            for r in range(5, 0, -1)],
            "evolution": {
                "runs_total": evo.get("runs_total", 0),
                "processed_feedback": len(evo.get("processed_feedback_ids") or []),
                "last_run_at": evo.get("last_run_at"),
            },
            "has_voice": os.path.exists(
                os.path.join(TEACHERS_DIR, tid, "voice", "voice_profile.json")),
        })

    @app.route("/api/v1/platform/sessions", methods=["GET"])
    @require_platform_key
    def platform_sessions():
        rows = []
        type_total = Counter()
        for name in _listdir(SESSIONS_DIR):
            sdir = os.path.join(SESSIONS_DIR, name)
            if not os.path.isdir(sdir):
                continue
            events_doc = _load_json(os.path.join(sdir, "events.json"))
            playback = _load_json(os.path.join(sdir, "playback_data.json"))
            teacher_id = voice_id = None
            type_counts = Counter()
            event_count = 0
            if events_doc:
                teacher_id = events_doc.get("teacher_id")
                voice_id = events_doc.get("voice_id")
                for e in (events_doc.get("events") or []):
                    type_counts[e.get("type") or "?"] += 1
                    event_count += 1
            elif playback:
                voice_id = playback.get("voice_id")
                for e in (playback.get("timeline") or []):
                    type_counts[e.get("type") or "?"] += 1
                    event_count += 1
            # playback 里的 teacher_id 是已知 bug（=session_id），不采信
            if teacher_id == name:
                teacher_id = None
            duration = (playback or {}).get("total_duration_sec")
            for k, v in type_counts.items():
                type_total[k] += v
            rows.append({
                "session_id": name,
                "date": _session_date(name),
                "teacher_id": teacher_id,
                "teacher_name": _teacher_name(teacher_id) if teacher_id else None,
                "voice_id": voice_id,
                "event_count": event_count,
                "type_counts": dict(type_counts),
                "duration_sec": round(duration, 1) if isinstance(duration, (int, float)) else None,
            })
        rows.sort(key=lambda r: r["session_id"], reverse=True)
        return ok({
            "sessions": rows,
            "total": len(rows),
            "type_total": [{"label": k, "value": v}
                           for k, v in type_total.most_common()],
        })

    @app.route("/api/v1/platform/feedback", methods=["GET"])
    @require_platform_key
    def platform_feedback():
        all_fb = _all_feedback()
        users = {u.get("id"): u.get("username") for u in auth.load_users()}
        items = []
        for f in all_fb:
            row = dict(f)
            row["teacher_name"] = _teacher_name(f.get("teacher_id"))
            row["user_name"] = users.get(f.get("user_id"))
            items.append(row)
        items.sort(key=lambda f: f.get("created_at") or "", reverse=True)

        ratings = [f["rating"] for f in all_fb
                   if isinstance(f.get("rating"), (int, float))]
        rdist = Counter(int(r) for r in ratings)

        by_teacher = defaultdict(list)
        for f in all_fb:
            if isinstance(f.get("rating"), (int, float)):
                by_teacher[f["teacher_id"]].append(f["rating"])
        teacher_rows = [{
            "teacher_id": tid,
            "teacher_name": _teacher_name(tid),
            "count": len(rs),
            "avg": round(sum(rs) / len(rs), 2) if rs else 0,
        } for tid, rs in by_teacher.items()]
        teacher_rows.sort(key=lambda r: -r["count"])

        trend = Counter((f.get("created_at") or "")[:10]
                        for f in all_fb if f.get("created_at"))
        return ok({
            "items": items,
            "total": len(items),
            "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else 0,
            "rating_dist": [{"label": f"{r}★", "value": rdist.get(r, 0)}
                            for r in range(5, 0, -1)],
            "by_teacher": teacher_rows,
            "trend": [{"date": d, "value": v} for d, v in sorted(trend.items())],
        })

    @app.route("/api/v1/platform/matches", methods=["GET"])
    @require_platform_key
    def platform_matches():
        matches = _all_matches()
        users = {u.get("id"): u.get("username") for u in auth.load_users()}
        items = []
        hit_top = Counter()         # 被排到第 1 的教师
        tag_freq = Counter()        # matched_tags 词频
        fit_buckets = Counter()     # semantic_fit 分桶
        for rec in matches:
            rankings = rec.get("rankings") or []
            top = rankings[0] if rankings else None
            if top:
                hit_top[top.get("display_name") or top.get("teacher_id")] += 1
                fit = top.get("semantic_fit")
                if isinstance(fit, (int, float)):
                    fit_buckets[f"{int(fit * 10) * 10}–{int(fit * 10) * 10 + 9}%"] += 1
            for r in rankings:
                for t in (r.get("matched_tags") or []):
                    tag_freq[t] += 1
            items.append({
                "match_id": rec.get("match_id"),
                "query": rec.get("query"),
                "user_name": users.get(rec.get("user_id")),
                "created_at": rec.get("created_at"),
                "candidates": len(rec.get("candidates") or []),
                "top": {
                    "teacher_name": top.get("display_name"),
                    "subject": top.get("subject"),
                    "semantic_fit": top.get("semantic_fit"),
                } if top else None,
            })
        items.sort(key=lambda m: m.get("created_at") or "", reverse=True)
        return ok({
            "items": items,
            "total": len(items),
            "top_hits": [{"label": k, "value": v} for k, v in hit_top.most_common(12)],
            "tag_freq": [{"label": k, "value": v} for k, v in tag_freq.most_common(30)],
            "fit_dist": [{"label": k, "value": v}
                         for k, v in sorted(fit_buckets.items(), reverse=True)],
        })

    @app.route("/api/v1/platform/media", methods=["GET"])
    @require_platform_key
    def platform_media():
        media = _load_json(MEDIA_INDEX, {"images": []}) or {"images": []}
        imgs = media.get("images") or []
        subj = Counter(i.get("subject") for i in imgs if i.get("subject"))
        mtype = Counter(i.get("media_type") for i in imgs if i.get("media_type"))
        active = sum(1 for i in imgs if i.get("status") == "active")
        items = [{
            "id": i.get("id"),
            "subject": i.get("subject"),
            "topic": i.get("topic"),
            "caption": i.get("caption"),
            "media_type": i.get("media_type"),
            "status": i.get("status"),
            "keywords": i.get("keywords") or [],
            "url": "/api/v1/media/" + (i.get("file") or ""),
        } for i in imgs]
        return ok({
            "items": items,
            "total": len(imgs),
            "active": active,
            "subject_dist": [{"label": k, "value": v}
                             for k, v in subj.most_common()],
            "type_dist": [{"label": k, "value": v} for k, v in mtype.most_common()],
        })

    # ═════════════════════ 管控（写操作） ═════════════════════
    # 平台端唯一的写路径；读路径仍保持只读零依赖。重模块一律在处理函数内惰性 import，
    # 复用各业务模块既有的原子写 / 锁 / 统计同步，不另起一套，避免数据不一致。

    @app.route("/api/v1/platform/users/<uid>", methods=["DELETE"])
    @require_platform_key
    def platform_delete_user(uid):
        users = auth.load_users()
        if not any(u.get("id") == uid for u in users):
            return err("用户不存在", 4040, 404)
        auth.save_users([u for u in users if u.get("id") != uid])
        # 同时失效其在线 token
        for tk, u_id in list(auth.tokens.items()):
            if u_id == uid:
                auth.tokens.pop(tk, None)
        return ok({"id": uid}, "用户已删除")

    @app.route("/api/v1/platform/users/<uid>/password", methods=["POST"])
    @require_platform_key
    def platform_reset_password(uid):
        pw = ((request.json or {}).get("password") or "").strip()
        if len(pw) < 4:
            return err("密码至少 4 位")
        users = auth.load_users()
        target = next((u for u in users if u.get("id") == uid), None)
        if not target:
            return err("用户不存在", 4040, 404)
        target["password"] = auth.hash_password(pw)
        auth.save_users(users)
        return ok({"id": uid}, "密码已重置")

    @app.route("/api/v1/platform/teachers/<tid>/visibility", methods=["POST"])
    @require_platform_key
    def platform_teacher_visibility(tid):
        import teachers as T
        hidden = bool((request.json or {}).get("hidden"))
        card = T.load_teacher_card(tid)
        if not card:
            return err("教师不存在", 4040, 404)
        card["hidden"] = hidden
        T.save_teacher_card(tid, card)
        # 下架后学生发现页 / M3 匹配均不再返回该教师
        return ok({"teacher_id": tid, "hidden": hidden}, "已下架" if hidden else "已上架")

    @app.route("/api/v1/platform/teachers/<tid>/account", methods=["POST"])
    @require_platform_key
    def platform_assign_account(tid):
        """给「无账号」教师分配一个登录账号（用户名取下一个可用 t{N}，初始密码 1234），
        并把账号 id 写回 teacher_card.user_id，使该账号能访问/管理这位教师。"""
        import re as _re
        import secrets
        import teachers as T
        card = T.load_teacher_card(tid)
        if not card:
            return err("教师不存在", 4040, 404)
        users = auth.load_users()
        existing = next((u for u in users
                         if u.get("id") == card.get("user_id") and u.get("role") == "teacher"), None)
        if existing:
            return err(f"该教师已绑定账号 {existing['username']}", 4090, 409)
        # 下一个可用 t{N}：取现有所有 t<数字> 账号的最大编号 +1（当前 t1–t7 → t8 起）
        nums = [int(m.group(1)) for u in users
                for m in [_re.match(r"^t(\d+)$", u.get("username", ""))] if m]
        username = f"t{(max(nums) + 1) if nums else 1}"
        new_user = {"id": secrets.token_hex(8), "username": username,
                    "password": auth.hash_password("1234"), "role": "teacher"}
        users.append(new_user)
        auth.save_users(users)
        card["user_id"] = new_user["id"]
        T.save_teacher_card(tid, card)
        return ok({"teacher_id": tid, "username": username, "password": "1234",
                   "user_id": new_user["id"]}, f"已分配账号 {username}（初始密码 1234）")

    @app.route("/api/v1/platform/courses/<tid>/<cid>/publish", methods=["POST"])
    @require_platform_key
    def platform_course_publish(tid, cid):
        import course as C
        published = bool((request.json or {}).get("published"))
        crs = C.load_course(tid, cid)
        if not crs:
            return err("课程不存在", 4040, 404)
        crs["published"] = published
        C.save_course(tid, crs)
        return ok({"course_id": cid, "published": published}, "已上架" if published else "已下架")

    @app.route("/api/v1/platform/courses/<tid>/<cid>", methods=["DELETE"])
    @require_platform_key
    def platform_course_delete(tid, cid):
        import course as C
        import shutil
        d = C._course_dir(tid, cid)
        if not os.path.isdir(d):
            return err("课程不存在", 4040, 404)
        shutil.rmtree(d, ignore_errors=True)
        return ok({"course_id": cid}, "课程已删除")

    @app.route("/api/v1/platform/feedback/<tid>/<fid>", methods=["DELETE"])
    @require_platform_key
    def platform_feedback_delete(tid, fid):
        import feedback as F
        with F._feedback_lock:
            lst = F.load_feedback(tid)
            if not any(f.get("id") == fid for f in lst):
                return err("评价不存在", 4040, 404)
            lst = [f for f in lst if f.get("id") != fid]
            F.save_feedback(tid, lst)
            F._update_card_stats(tid, lst)  # 同步 teacher_card 的 total/avg
        return ok({"id": fid}, "评价已删除")

    @app.route("/api/v1/platform/media/<image_id>/status", methods=["POST"])
    @require_platform_key
    def platform_media_status(image_id):
        import media_admin as M
        status = (request.json or {}).get("status")
        if status not in ("active", "disabled"):
            return err("status 不合法（active / disabled）")
        index = M._load_index()
        entry = next((e for e in index.get("images", []) if e.get("id") == image_id), None)
        if not entry:
            return err("图片不存在", 4040, 404)
        entry["status"] = status  # disabled 后检索层不再返回
        M._save_index(index)
        return ok({"id": image_id, "status": status}, "已启用" if status == "active" else "已停用")

    @app.route("/api/v1/platform/media/<image_id>", methods=["DELETE"])
    @require_platform_key
    def platform_media_delete(image_id):
        import media_admin as M
        index = M._load_index()
        entry = next((e for e in index.get("images", []) if e.get("id") == image_id), None)
        if not entry:
            return err("图片不存在", 4040, 404)
        index["images"] = [e for e in index.get("images", []) if e.get("id") != image_id]
        M._save_index(index)
        try:  # best-effort 删文件
            from media_library import IMAGES_ROOT
            fp = os.path.join(IMAGES_ROOT, (entry.get("file") or "").replace("/", os.sep))
            if os.path.isfile(fp):
                os.remove(fp)
        except Exception:
            pass
        return ok({"id": image_id}, "图片已删除")
