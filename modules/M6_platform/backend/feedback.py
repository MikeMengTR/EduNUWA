"""学生评价系统 — 评分 + 评论。

进化闭环升级：
- 反馈可关联推荐事件（match_id，服务端校验+快照 enrich）或讲课会话（session_id）；
- 所有 load-modify-save 由模块级锁保护（该文件被提交/删除/进化读取并发访问）；
- 提交成功后触发进化检查（evolution.maybe_trigger_refresh，失败绝不影响评价本身）。
"""
import json, os, secrets, threading
from datetime import datetime, timezone
from flask import request
from auth import require_auth, ok, err
from teachers import get_teacher_dir

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "data")
FEEDBACK_DIR = os.path.join(DATA_DIR, "feedback")

# 评价文件并发读写锁。注意：持锁期间只做文件读写，不要做网络/LLM 调用。
_feedback_lock = threading.Lock()

VALID_CONTEXTS = ("match", "classroom", "profile")

def _get_teacher_feedback_path(teacher_id):
    return os.path.join(FEEDBACK_DIR, f"{teacher_id}.json")

def load_feedback(teacher_id):
    path = _get_teacher_feedback_path(teacher_id)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_feedback(teacher_id, data):
    os.makedirs(FEEDBACK_DIR, exist_ok=True)
    path = _get_teacher_feedback_path(teacher_id)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def _update_card_stats(teacher_id, feedback_list):
    """同步 teacher_card 的评分统计（提交与删除共用）。"""
    from teachers import load_teacher_card, save_teacher_card
    card = load_teacher_card(teacher_id)
    if not card:
        return
    all_ratings = [f["rating"] for f in feedback_list]
    card["stats"] = {
        "total_feedback": len(feedback_list),
        "avg_rating": round(sum(all_ratings) / len(all_ratings), 1) if all_ratings else 0,
    }
    save_teacher_card(teacher_id, card)

def _resolve_match_context(teacher_id, user_id, match_id):
    """校验 match_id 并提取快照。校验失败返回 (None, None)——静默降级为普通评价，防伪造。

    校验：记录存在、归属当前用户、该教师在本次推荐结果中。
    """
    from match_log import load_match_record
    record = load_match_record(match_id)
    if not record or record.get("user_id") != user_id:
        return None, None
    ranking = next((r for r in record.get("rankings", []) if r.get("teacher_id") == teacher_id), None)
    if not ranking:
        return None, None
    match_context = {
        "query": record.get("query", ""),
        "reason": ranking.get("reason", ""),
        "matched_tags": ranking.get("matched_tags", []),
        "semantic_fit": ranking.get("semantic_fit"),
    }
    candidate = next((c for c in record.get("candidates", []) if c.get("teacher_id") == teacher_id), None)
    skill_version = candidate.get("skill_version") if candidate else None
    return match_context, skill_version

def register_routes(app):
    @app.route("/api/v1/teachers/<teacher_id>/feedback", methods=["POST"])
    @require_auth
    def submit_feedback(teacher_id):
        """提交评价：评分(1-5) + 文字评论，可选关联 match_id / session_id / context"""
        data = request.json
        rating = data.get("rating")
        comment = data.get("comment", "").strip()

        try:
            rating = int(rating)
            if rating < 1 or rating > 5:
                return err("评分必须在1-5之间")
        except (TypeError, ValueError):
            return err("请提供有效的评分(1-5)")

        if not comment:
            return err("请输入评价内容")

        entry = {
            "id": secrets.token_hex(6),
            "user_id": request.user_id,
            "rating": rating,
            "comment": comment,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        context = data.get("context", "")
        if context in VALID_CONTEXTS:
            entry["context"] = context
        session_id = (data.get("session_id") or "").strip()
        if session_id:
            entry["session_id"] = session_id

        # match_id 服务端校验 + 推荐快照嵌入（denormalize，进化器无需回查）
        match_id = (data.get("match_id") or "").strip()
        skill_version = None
        if match_id:
            match_context, skill_version = _resolve_match_context(teacher_id, request.user_id, match_id)
            if match_context is not None:
                entry["match_id"] = match_id
                entry["match_context"] = match_context
                entry.setdefault("context", "match")

        # skill_version：优先取推荐时的快照，否则取当前最新版本
        if skill_version is None:
            from teachers import load_skill_profile
            profile = load_skill_profile(teacher_id)
            if profile:
                skill_version = profile.get("version")
        if skill_version is not None:
            entry["skill_version"] = skill_version

        with _feedback_lock:
            feedback_list = load_feedback(teacher_id)
            feedback_list.append(entry)
            save_feedback(teacher_id, feedback_list)
            _update_card_stats(teacher_id, feedback_list)

        # 进化闭环触发检查（后台线程，失败绝不影响评价提交）
        try:
            from evolution import maybe_trigger_refresh
            maybe_trigger_refresh(teacher_id)
        except Exception:
            pass

        return ok({"id": entry["id"]}, "评价提交成功")

    @app.route("/api/v1/teachers/<teacher_id>/feedback", methods=["GET"])
    @require_auth
    def get_feedback(teacher_id):
        """获取某教师的所有评价"""
        with _feedback_lock:
            feedback_list = load_feedback(teacher_id)
        # 按时间倒序，最新在前
        feedback_list.sort(key=lambda f: f.get("created_at", ""), reverse=True)
        # 计算统计
        ratings = [f["rating"] for f in feedback_list]
        stats = {
            "total": len(feedback_list),
            "avg_rating": round(sum(ratings) / len(ratings), 1) if ratings else 0,
            "distribution": {str(i): ratings.count(i) for i in range(1, 6)},
        }
        return ok({"feedback": feedback_list[:50], "stats": stats})

    @app.route("/api/v1/teachers/<teacher_id>/feedback/<feedback_id>", methods=["DELETE"])
    @require_auth
    def delete_feedback(teacher_id, feedback_id):
        """删除自己的评价"""
        with _feedback_lock:
            feedback_list = load_feedback(teacher_id)
            target = next((f for f in feedback_list if f["id"] == feedback_id), None)
            if not target:
                return err("评价不存在", 4040, 404)
            if target["user_id"] != request.user_id:
                return err("只能删除自己的评价", 4030, 403)

            feedback_list = [f for f in feedback_list if f["id"] != feedback_id]
            save_feedback(teacher_id, feedback_list)
            _update_card_stats(teacher_id, feedback_list)
        return ok(None, "评价已删除")
