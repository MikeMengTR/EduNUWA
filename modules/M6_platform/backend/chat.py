import json
import os
import threading
from flask import request
from openai import OpenAI
from auth import require_auth, ok, err
from teachers import load_teacher_card, load_skill_md, get_teacher_dir

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA_DIR = os.path.join(_project_root, "data")
CONVERSATIONS_FILE = os.path.join(DATA_DIR, "conversations.json")

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# conversations.json 被 chat 与 demo（pipeline.py）两条链路并发读写，必须加锁。
# 注意：不要在持锁期间调 LLM——读时拿快照，写时重新加载再追加。
_conv_lock = threading.Lock()

def get_client():
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

def load_conversations():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(CONVERSATIONS_FILE):
        with open(CONVERSATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)
    with open(CONVERSATIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_conversations(convs):
    with open(CONVERSATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(convs, f, ensure_ascii=False, indent=2)

def get_history(user_id, teacher_id, limit=20):
    """取该学生×该老师的最近对话（含文字 chat 与 demo 讲课摘要）。"""
    with _conv_lock:
        convs = load_conversations()
    return convs.get(f"{user_id}_{teacher_id}", {}).get("messages", [])[-limit:]

def append_history(user_id, teacher_id, entries):
    """原子追加若干条消息（先重新加载再写，避免覆盖并发写入）。"""
    with _conv_lock:
        convs = load_conversations()
        key = f"{user_id}_{teacher_id}"
        if key not in convs:
            convs[key] = {"messages": []}
        convs[key]["messages"].extend(entries)
        save_conversations(convs)

def _build_system_prompt(teacher_id, card):
    """构建系统提示词：优先使用 M2 蒸馏的 TeacherSkill.md，回退到教师手写 prompt"""
    skill_md = load_skill_md(teacher_id)
    if skill_md:
        # 使用完整的蒸馏 Skill（截断到 ~6000 字留给对话空间）
        skill_trimmed = skill_md[:6000]
        return f"""你是 {card.get('display_name', '教师')}，以下是你的教学风格规范。请严格按照规范中的 Teaching Philosophy、Explanation Pattern、Speech Policy 来回答学生的问题。

{skill_trimmed}

---
请以教师身份，按照上述教学风格回应当前学生的问题。"""

    # 回退：教师手写的简单 system_prompt
    return card.get("system_prompt",
        f"你是{card.get('display_name', '教师')}，请用教学风格回答学生的问题。")

def register_routes(app):
    @app.route("/api/v1/chat/<teacher_id>", methods=["POST"])
    @require_auth
    def chat(teacher_id):
        card = load_teacher_card(teacher_id)
        if not card:
            return err("教师不存在", 4040, 404)

        data = request.json
        message = data.get("message", "").strip()
        if not message:
            return err("消息不能为空")

        user_id = request.user_id
        history = get_history(user_id, teacher_id, limit=19)

        system_prompt = _build_system_prompt(teacher_id, card)
        has_skill = load_skill_md(teacher_id) is not None
        messages = [{"role": "system", "content": system_prompt}]
        # 只取 role/content：存储里的消息可能带 kind 等附加字段，API 不接受
        messages.extend({"role": m["role"], "content": m["content"]} for m in history)
        messages.append({"role": "user", "content": message})

        if not DEEPSEEK_API_KEY:
            reply = f"[模拟回复] 我是 {card.get('display_name', 'AI教师')}。你说：「{message}」。请配置 DEEPSEEK_API_KEY 环境变量以获得真实 AI 回复。"
            append_history(user_id, teacher_id, [
                {"role": "user", "content": message},
                {"role": "assistant", "content": reply},
            ])
            return ok({"reply": reply, "skillUsed": has_skill})

        try:
            client = get_client()
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                temperature=0.7,
                max_tokens=2000,
            )
            reply = response.choices[0].message.content
        except Exception as e:
            reply = f"[错误] 调用 AI 失败: {str(e)}"

        # LLM 调用耗时数秒，期间 demo 链路可能写入了历史——append_history
        # 内部重新加载再追加，不会覆盖
        append_history(user_id, teacher_id, [
            {"role": "user", "content": message},
            {"role": "assistant", "content": reply},
        ])
        return ok({"reply": reply, "skillUsed": has_skill})

    @app.route("/api/v1/chat/<teacher_id>/history", methods=["GET"])
    @require_auth
    def chat_history(teacher_id):
        convs = load_conversations()
        key = f"{request.user_id}_{teacher_id}"
        messages = convs.get(key, {}).get("messages", [])
        return ok(messages)

    @app.route("/api/v1/chat/<teacher_id>/history", methods=["DELETE"])
    @require_auth
    def clear_history(teacher_id):
        convs = load_conversations()
        key = f"{request.user_id}_{teacher_id}"
        if key in convs:
            convs[key]["messages"] = []
            save_conversations(convs)
        return ok(None, "对话历史已清除")
