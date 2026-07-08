"""Skill 自进化编排层 — 推荐-反馈闭环的 M6 侧。

职责（M6 只编排不实现业务逻辑）：
- 收集输入（反馈、profile、live 标签、候补池）→ 调 M2 tag_evolver 纯函数 → 落盘产物；
- 自动触发（反馈积累达阈值起 daemon 线程）与教师手动触发；
- skill 版本修订的教师确认制流程（pending → confirm 落 skills/v{n+1}/，H12 旧版本不动）。

数据落点：
  data/teachers/{tid}/style_tags_live.json            众评标签（M3/前端消费）
  data/teachers/{tid}/evolution/state.json            处理游标 + 修订建议积累
  data/teachers/{tid}/evolution/calibration.json      auto 标签 confidence 校准累积
  data/teachers/{tid}/evolution/pending_tags.json     support=1 候补标签池
  data/teachers/{tid}/evolution/pending_revision.json 待教师确认的版本修订
  data/teachers/{tid}/evolution/runs/{run_id}.json    每次梯度运行审计日志

锁纪律（同 chat.py）：持锁只做文件读写快照，LLM 调用 10-30s 绝不持锁。
"""
import hashlib
import json
import os
import secrets
import sys
import threading
from datetime import datetime, timezone
from flask import request

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from auth import require_auth, require_role, ok, err
from teachers import (get_teacher_dir, load_teacher_card, load_skill_profile,
                      load_skill_md, load_live_tags)

REFRESH_THRESHOLD = int(os.environ.get("EVOLUTION_REFRESH_THRESHOLD", "5"))
# 修订就绪条件：校准信号总人次 ≥ 10 或 晋升众评标签 ≥ 3
REVISION_SIGNAL_MIN = 10
REVISION_CROWD_MIN = 3
REVISION_HINTS_CAP = 20

_SCHEMA_PATH = os.path.join(_project_root, "modules", "M2_distill", "schemas",
                            "style_tags_live.schema.json")

# per-teacher 锁 + 进行中集合（防同一教师并发进化）
_locks_guard = threading.Lock()
_evolution_locks: dict = {}
_in_progress: set = set()


def _teacher_lock(teacher_id):
    with _locks_guard:
        if teacher_id not in _evolution_locks:
            _evolution_locks[teacher_id] = threading.Lock()
        return _evolution_locks[teacher_id]


def _atomic_write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _evo_dir(teacher_id):
    return os.path.join(get_teacher_dir(teacher_id), "evolution")


def _state_path(tid):    return os.path.join(_evo_dir(tid), "state.json")
def _calib_path(tid):    return os.path.join(_evo_dir(tid), "calibration.json")
def _pending_path(tid):  return os.path.join(_evo_dir(tid), "pending_tags.json")
def _revision_path(tid): return os.path.join(_evo_dir(tid), "pending_revision.json")
def _live_path(tid):     return os.path.join(get_teacher_dir(tid), "style_tags_live.json")


def load_state(tid):
    return _load_json(_state_path(tid), {
        "processed_feedback_ids": [], "revision_hints": [],
        "last_run_at": None, "last_run_id": None, "last_error": None, "runs_total": 0,
    })


def _student_hash(user_id):
    return hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:12]


def _validate_live_doc(live_doc):
    """写盘前 schema 校验；jsonschema 不可用时退化为关键结构检查。"""
    try:
        import jsonschema
        schema = _load_json(_SCHEMA_PATH, None)
        if schema:
            jsonschema.validate(live_doc, schema)
            return
    except ImportError:
        pass
    # 退化检查
    assert isinstance(live_doc.get("teacher_id"), str)
    assert isinstance(live_doc.get("tags"), list)
    for t in live_doc["tags"]:
        assert t.get("source") == "crowd" and t.get("text")
        assert isinstance(t.get("support"), int) and t["support"] >= 1


def _build_feedback_batch(feedback_list, processed_ids):
    """未处理反馈 → evolver 输入格式。"""
    batch = []
    for fb in feedback_list:
        if fb["id"] in processed_ids:
            continue
        mc = fb.get("match_context") or {}
        batch.append({
            "feedback_id": fb["id"],
            "student_hash": _student_hash(fb.get("user_id", "")),
            "rating": fb.get("rating"),
            "comment": fb.get("comment", ""),
            "created_at": fb.get("created_at", ""),
            "context": fb.get("context", "profile"),
            "query": mc.get("query", ""),
            "reason": mc.get("reason", ""),
            "matched_tags": mc.get("matched_tags", []),
        })
    return batch


def pending_feedback_count(teacher_id):
    from feedback import load_feedback, _feedback_lock
    with _feedback_lock:
        feedback_list = load_feedback(teacher_id)
    processed = set(load_state(teacher_id).get("processed_feedback_ids", []))
    return len([f for f in feedback_list if f["id"] not in processed])


def maybe_trigger_refresh(teacher_id):
    """反馈提交后调用：未处理反馈达阈值且该教师不在进化中 → 后台线程跑一轮。"""
    if pending_feedback_count(teacher_id) < REFRESH_THRESHOLD:
        return False
    with _locks_guard:
        if teacher_id in _in_progress:
            return False
        _in_progress.add(teacher_id)
    threading.Thread(target=_run_refresh_guarded, args=(teacher_id,), daemon=True).start()
    return True


def _run_refresh_guarded(teacher_id):
    try:
        run_refresh(teacher_id)
    except Exception:
        pass
    finally:
        with _locks_guard:
            _in_progress.discard(teacher_id)


def run_refresh(teacher_id):
    """跑一轮标签梯度更新。手动 API 同步调用本函数；自动触发在 daemon 线程里调。"""
    from feedback import load_feedback, _feedback_lock
    from modules.M2_distill.tag_evolver import refresh_crowd_tags, extract_md_sections

    lock = _teacher_lock(teacher_id)
    run_id = f"R_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(3)}"

    # --- 1) 持锁取快照 ---
    with lock:
        state = load_state(teacher_id)
        with _feedback_lock:
            feedback_list = load_feedback(teacher_id)
        batch = _build_feedback_batch(feedback_list, set(state["processed_feedback_ids"]))
        if not batch:
            return {"status": "success", "message": "no new feedback", "processed": 0}
        profile = load_skill_profile(teacher_id) or {}
        skill_md = load_skill_md(teacher_id) or ""
        live_doc = load_live_tags(teacher_id)
        pending_pool = _load_json(_pending_path(teacher_id), [])

    auto_tags = [t for t in profile.get("style_tags", []) if isinstance(t, dict) and t.get("text")]
    excerpt_secs = extract_md_sections(skill_md, ["Teaching Philosophy", "Speech Policy"])
    excerpt = "\n\n".join(excerpt_secs.values())[:1500]
    embeddings_model = profile.get("style_embeddings_model", "bge-base-zh-v1.5")

    # --- 2) 释放锁调 LLM（10-30s） ---
    result = refresh_crowd_tags(
        teacher_id=teacher_id, auto_tags=auto_tags, live_doc=live_doc,
        pending_pool=pending_pool, feedback_batch=batch,
        skill_md_excerpt=excerpt, embeddings_model=embeddings_model,
    )

    # --- 3) 重新持锁落盘 ---
    with lock:
        state = load_state(teacher_id)
        now = datetime.now(timezone.utc).isoformat()
        if result.get("status") != "success":
            state.update({"last_error": result.get("message", "unknown"),
                          "last_run_at": now, "last_run_id": run_id})
            _atomic_write_json(_state_path(teacher_id), state)
            return result

        try:
            _validate_live_doc(result["live_doc"])
        except Exception as e:
            state.update({"last_error": f"live_doc schema invalid: {e}",
                          "last_run_at": now, "last_run_id": run_id})
            _atomic_write_json(_state_path(teacher_id), state)
            return {"status": "error", "message": f"live_doc schema invalid: {e}"}

        # calibration 增量累积 + 校准值重算
        from modules.M2_distill.tag_evolver import _calibrate
        calib = _load_json(_calib_path(teacher_id), {"tags": {}})
        auto_by_text = {t["text"]: t for t in auto_tags}
        for text, delta in result["calibration_delta"].items():
            c = calib["tags"].setdefault(text, {
                "confirms": 0, "contradicts": 0,
                "original_confidence": auto_by_text.get(text, {}).get("confidence", 0.6),
            })
            c["confirms"] += delta.get("confirms", 0)
            c["contradicts"] += delta.get("contradicts", 0)
            c["adjusted_confidence"] = _calibrate(
                c["original_confidence"], c["confirms"], c["contradicts"])
        calib["updated_at"] = now

        # 修订建议积累（供 propose_skill_revision 用）
        hints = (state.get("revision_hints", []) + result.get("skill_md_suggestions", []))
        state["revision_hints"] = hints[-REVISION_HINTS_CAP:]
        state["processed_feedback_ids"] = sorted(
            set(state["processed_feedback_ids"]) | {fb["feedback_id"] for fb in batch})
        state.update({"last_run_at": now, "last_run_id": run_id,
                      "last_error": None, "runs_total": state.get("runs_total", 0) + 1})

        _atomic_write_json(_live_path(teacher_id), result["live_doc"])
        _atomic_write_json(_pending_path(teacher_id), result["pending_pool"])
        _atomic_write_json(_calib_path(teacher_id), calib)
        _atomic_write_json(_state_path(teacher_id), state)
        _atomic_write_json(os.path.join(_evo_dir(teacher_id), "runs", f"{run_id}.json"), {
            "run_id": run_id, "at": now,
            "input_feedback_ids": [fb["feedback_id"] for fb in batch],
            "report": result["gradient_report"],
        })

    return {"status": "success", "run_id": run_id, "processed": len(batch),
            "live_tags": len(result["live_doc"]["tags"]),
            "promoted": result["gradient_report"].get("promoted", []),
            "calibrated": list(result["calibration_delta"].keys())}


def _revision_ready(teacher_id):
    calib = _load_json(_calib_path(teacher_id), {"tags": {}})
    total_signals = sum(c.get("confirms", 0) + c.get("contradicts", 0)
                        for c in calib["tags"].values())
    live = load_live_tags(teacher_id) or {}
    return total_signals >= REVISION_SIGNAL_MIN or len(live.get("tags", [])) >= REVISION_CROWD_MIN


def run_revision(teacher_id):
    """生成 skill 修订提案 → pending_revision.json（待教师确认）。"""
    from feedback import load_feedback, _feedback_lock
    from modules.M2_distill.tag_evolver import propose_skill_revision

    lock = _teacher_lock(teacher_id)
    with lock:
        skill_md = load_skill_md(teacher_id)
        profile = load_skill_profile(teacher_id)
        if not skill_md or not profile:
            return {"status": "error", "message": "该教师还没有蒸馏的 Skill，无法修订"}
        live_doc = load_live_tags(teacher_id)
        calib = _load_json(_calib_path(teacher_id), {"tags": {}})
        state = load_state(teacher_id)
        with _feedback_lock:
            feedback_list = load_feedback(teacher_id)

    # 代表性反馈摘录：有评论的最新 10 条，优先带推荐上下文的
    digest_src = sorted(feedback_list,
                        key=lambda f: (bool(f.get("match_context")), f.get("created_at", "")),
                        reverse=True)[:10]
    digest = [{"rating": f.get("rating"), "comment": f.get("comment", ""),
               "query": (f.get("match_context") or {}).get("query", "")} for f in digest_src]

    result = propose_skill_revision(
        teacher_id=teacher_id, skill_md=skill_md, profile=profile,
        live_doc=live_doc, calibration=calib["tags"],
        feedback_digest=digest, revision_hints=state.get("revision_hints", []),
    )
    if result.get("status") != "success":
        return result

    with lock:
        _atomic_write_json(_revision_path(teacher_id), {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "base_version": profile.get("version"),
            "revised_md": result["revised_md"],
            "revised_style_tags": result["revised_style_tags"],
            "change_summary": result["change_summary"],
            "applied_sections": result["applied_sections"],
            "unchanged_rationale": result["unchanged_rationale"],
        })
    return {"status": "success", "change_summary": result["change_summary"],
            "applied_sections": result["applied_sections"]}


def confirm_revision(teacher_id):
    """教师确认修订 → 落地为 skills/v{n+1}/（H12：旧版本目录不动）。"""
    lock = _teacher_lock(teacher_id)
    with lock:
        pending = _load_json(_revision_path(teacher_id), None)
        if not pending:
            return {"status": "error", "message": "没有待确认的修订"}
        profile = load_skill_profile(teacher_id)
        if not profile:
            return {"status": "error", "message": "skill_profile 不存在"}

        # 版本号：扫描 skills/ 下最大 v{n}（与 distill.py 同逻辑）
        skills_dir = os.path.join(get_teacher_dir(teacher_id), "skills")
        version = 1
        if os.path.exists(skills_dir):
            nums = [int(d[1:].split("_")[0]) for d in os.listdir(skills_dir)
                    if d.startswith("v") and d[1:].split("_")[0].isdigit()]
            if nums:
                version = max(nums) + 1

        new_profile = dict(profile)
        new_profile.update({
            "skill_id": f"S_{teacher_id.replace('_', '')}_v{version}",
            "version": version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "style_tags": pending["revised_style_tags"],
            "derived_from": f"v{pending.get('base_version')}+feedback",
        })

        out_dir = os.path.join(skills_dir, f"v{version}")
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "TeacherSkill.md"), "w", encoding="utf-8") as f:
            f.write(pending["revised_md"])
        _atomic_write_json(os.path.join(out_dir, "skill_profile.json"), new_profile)

        # 已落地的校准信号清零（避免旧信号重复作用于新版本），修订建议清空
        _atomic_write_json(_calib_path(teacher_id), {
            "tags": {}, "updated_at": datetime.now(timezone.utc).isoformat()})
        state = load_state(teacher_id)
        state["revision_hints"] = []
        _atomic_write_json(_state_path(teacher_id), state)
        os.remove(_revision_path(teacher_id))

    return {"status": "success", "version": version,
            "change_summary": pending["change_summary"]}


def reject_revision(teacher_id):
    with _teacher_lock(teacher_id):
        path = _revision_path(teacher_id)
        if not os.path.exists(path):
            return {"status": "error", "message": "没有待确认的修订"}
        os.remove(path)
    return {"status": "success"}


def _require_owner(teacher_id):
    """教师本人校验，返回 err 响应或 None。"""
    card = load_teacher_card(teacher_id)
    if not card:
        return err("教师不存在", 4040, 404)
    if card.get("user_id") != request.user_id:
        return err("无权操作此教师", 4030, 403)
    return None


def register_routes(app):
    @app.route("/api/v1/teachers/<teacher_id>/evolution/status", methods=["GET"])
    @require_auth
    def evolution_status(teacher_id):
        state = load_state(teacher_id)
        live = load_live_tags(teacher_id) or {}
        return ok({
            "pending_count": pending_feedback_count(teacher_id),
            "threshold": REFRESH_THRESHOLD,
            "live_tags_count": len(live.get("tags", [])),
            "live_tags": live.get("tags", []),
            "last_run_at": state.get("last_run_at"),
            "last_error": state.get("last_error"),
            "runs_total": state.get("runs_total", 0),
            "revision_ready": _revision_ready(teacher_id),
            "has_pending_revision": os.path.exists(_revision_path(teacher_id)),
        })

    @app.route("/api/v1/teachers/<teacher_id>/evolution/refresh", methods=["POST"])
    @require_role("teacher")
    def evolution_refresh(teacher_id):
        e = _require_owner(teacher_id)
        if e:
            return e
        with _locks_guard:
            if teacher_id in _in_progress:
                return err("该教师的进化正在进行中", 4090, 409)
            _in_progress.add(teacher_id)
        try:
            result = run_refresh(teacher_id)
        finally:
            with _locks_guard:
                _in_progress.discard(teacher_id)
        if result.get("status") != "success":
            return err(result.get("message", "进化失败"), 5000, 500)
        return ok(result, "标签进化完成")

    @app.route("/api/v1/teachers/<teacher_id>/evolution/revise", methods=["POST"])
    @require_role("teacher")
    def evolution_revise(teacher_id):
        e = _require_owner(teacher_id)
        if e:
            return e
        result = run_revision(teacher_id)
        if result.get("status") != "success":
            return err(result.get("message", "修订生成失败"), 5000, 500)
        return ok(result, "修订提案已生成，请确认")

    @app.route("/api/v1/teachers/<teacher_id>/evolution/revision", methods=["GET"])
    @require_role("teacher")
    def evolution_get_revision(teacher_id):
        e = _require_owner(teacher_id)
        if e:
            return e
        pending = _load_json(_revision_path(teacher_id), None)
        if not pending:
            return err("没有待确认的修订", 4040, 404)
        return ok(pending)

    @app.route("/api/v1/teachers/<teacher_id>/evolution/revision/confirm", methods=["POST"])
    @require_role("teacher")
    def evolution_confirm(teacher_id):
        e = _require_owner(teacher_id)
        if e:
            return e
        result = confirm_revision(teacher_id)
        if result.get("status") != "success":
            return err(result.get("message", "确认失败"), 4040, 404)
        return ok(result, f"已生效为 v{result['version']}")

    @app.route("/api/v1/teachers/<teacher_id>/evolution/revision/reject", methods=["POST"])
    @require_role("teacher")
    def evolution_reject(teacher_id):
        e = _require_owner(teacher_id)
        if e:
            return e
        result = reject_revision(teacher_id)
        if result.get("status") != "success":
            return err(result.get("message", "操作失败"), 4040, 404)
        return ok(None, "修订已拒绝")
