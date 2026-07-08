"""
Session 状态管理 — 维护多轮对话上下文。

符合 M4 §3.3 session_manager 规范。
"""
from __future__ import annotations
import os
import json
import time
from pathlib import Path


def load_or_create_session(session_id: str, base_dir: str = "data/sessions") -> dict:
    """加载或创建 session 状态。"""
    path = os.path.join(base_dir, session_id, "session_state.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "session_id": session_id,
        "mode": "ondemand",
        "turn": 0,
        "qa_history": [],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
    }


def update_session(session_id: str, plan: dict, events_path: str, base_dir: str = "data/sessions") -> dict:
    """更新 session 状态（原子写入）。"""
    state = load_or_create_session(session_id, base_dir)
    state["turn"] = state.get("turn", 0) + 1
    state["last_events"] = events_path
    state["last_topic"] = plan.get("topic", "")
    state["last_depth"] = plan.get("depth", "intro")
    state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())

    # 压缩历史（超过 10 轮时）
    qa = state.get("qa_history", [])
    qa.append({
        "turn": state["turn"],
        "topic": plan.get("topic", ""),
        "question": plan.get("user_question", ""),
        "events": events_path,
    })
    if len(qa) > 10:
        qa = qa[-10:]
    state["qa_history"] = qa

    # 原子写入
    path = os.path.join(base_dir, session_id, "session_state.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp." + str(os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return state
