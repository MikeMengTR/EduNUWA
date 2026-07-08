"""课堂预录制：按大纲/讲课记录为每一讲编排 teaching events，持久化为可逐讲播放的课程。

数据落地：data/teachers/{teacher_id}/courses/{course_id}/
  - course.json                       课程元数据 + 章节列表 + 每讲状态
  - {chapter_id}/events.json          每讲教学事件（与 M5 demo 同格式，stream 模式逐句 TTS）

编排只生成 events（一次 LLM 调用/讲），不预合成音频；学生端 iframe 用老师音色实时合成。
"""
import json
import os
import sys
import secrets
import threading
from datetime import datetime, timezone
from flask import request

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from auth import require_auth, ok, err
from teachers import load_teacher_card, get_teacher_dir
from chat import _build_system_prompt, get_client, DEEPSEEK_API_KEY
from pipeline import _parse_demo_response

MAX_CHAPTERS = 16

# 板书 / 公式 / 输出格式规则（抽取自 pipeline.teaching_demo，保证与 M5 渲染契约一致）
_FORMAT_RULES = """请以教学演示模式完成本讲的讲解。你的输出必须包含两类内容：
1. **[speak]** 口头讲解文本（口语化，按照你的 Speech Policy 风格）
2. **[board]** 板书内容（标题、定义、公式、要点）

【公式规则·重要】
- 数学公式只能出现在 [board] 或 [formula] 行；统一用 $...$（行内）或 $$...$$（块级）包裹，禁止使用 \\( \\)、\\[ \\] 等其它定界符。分式、根号、上下标等复杂公式也一律用 $$...$$ 包裹。
- [board] 行（write_bullets/write_steps/write_summary）里写公式：简单符号直接用 Unicode（如 x²、x₀、Δx、μ、σ²、≤、→），复杂式才用 $...$ 包裹。**绝不要在板书行里写裸的 LaTeX 上下标 `_{...}`/`^{...}`（会原样显示成 _{x=x_0} 这样的乱码），也绝不要用求值竖线 `|`**——`|` 是 write_bullets/write_summary 多条要点的分隔符，写进公式会把内容拦腰切断。需要表达「在某点取值」时用文字，例如写「导数 dy/dx 在 x₀ 处的值」而不是 dy/dx|_{x=x_0}。
- [speak] 口播文本必须是纯口语，绝对不能包含 LaTeX 或公式符号（语音合成念不出来）。需要提到公式时改用自然语言，例如说“X 服从均值 μ、方差 σ 平方的正态分布”，而不是写出 X ~ N(μ, σ²)。

【板书规则·重要】
- [board:xxx] 的板书类型只能用这 5 种：write_title（标题）、write_subtitle（小标题）、write_bullets（要点，多条用 | 分隔）、write_steps（步骤）、write_summary（小结）。禁止使用 write_definition、write_highlight 等其它类型。
- 需要做对比/表格时，单独用一行 [table]，格式为：[table] 表标题 | 列名1,列名2,列名3 | 第一行格1,第一行格2,第一行格3 | 第二行... （竖线 | 分隔每一行，英文逗号分隔单元格）。
- 不要使用 markdown 语法（如 **加粗**、# 号），直接写纯文字。

【讲解顺序·重要】
- 要讲解公式、表格、图片或关键板书时，必须**先输出对应的 [formula]/[table]/[image]/[board] 行**（让它先出现在黑板上），**紧接着再用 [speak] 讲解它**。
- 绝对不要先用 [speak] 把内容讲完、最后才补上 [formula]/[image]/[board]——那样学生在听讲解时黑板还是空的。正确顺序永远是「先上黑板，再开口讲」。

请按以下格式输出，每个事件一行（注意：公式/板书都在讲解它的 [speak] 之前）：
[speak] 同学们好，这一讲我们来学习正态分布。
[board:write_title] 正态分布
[formula] $$f(x)=\\frac{1}{\\sqrt{2\\pi}\\sigma}e^{-\\frac{(x-\\mu)^2}{2\\sigma^2}}$$
[speak] 大家看黑板上这个概率密度函数，μ 是它的均值、σ 是标准差，这两个参数决定了曲线的形状。
[board:write_bullets] 均值 μ 决定分布中心 | 标准差 σ 决定离散程度
[speak] 也就是说，μ 决定中心位置，σ 决定胖瘦程度，这就是本讲的核心。
"""


def _courses_dir(teacher_id):
    return os.path.join(get_teacher_dir(teacher_id), "courses")


def _course_dir(teacher_id, course_id):
    return os.path.join(_courses_dir(teacher_id), course_id)


def _course_json_path(teacher_id, course_id):
    return os.path.join(_course_dir(teacher_id, course_id), "course.json")


def load_course(teacher_id, course_id):
    p = _course_json_path(teacher_id, course_id)
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_course(teacher_id, course):
    d = _course_dir(teacher_id, course["course_id"])
    os.makedirs(d, exist_ok=True)
    with open(_course_json_path(teacher_id, course["course_id"]), "w", encoding="utf-8") as f:
        json.dump(course, f, ensure_ascii=False, indent=2)


def list_courses(teacher_id):
    root = _courses_dir(teacher_id)
    out = []
    if not os.path.exists(root):
        return out
    for cid in os.listdir(root):
        c = load_course(teacher_id, cid)
        if c:
            out.append(c)
    out.sort(key=lambda c: c.get("created_at", ""), reverse=True)
    return out


def _estimate_duration(events):
    """按 M5 _simple_playback 的节奏估算单讲时长（秒）"""
    t = 0.0
    for e in events:
        et = e.get("type")
        if et == "speak":
            t += max(len(e.get("text", "")) / 4.0, 1.5) + 0.3
        elif et == "board":
            t += 2.0
        elif et == "formula":
            t += 3.0
        elif et == "image":
            t += 3.0
        elif et == "pause":
            t += e.get("duration_sec", 1.5)
    return round(t)


def _orchestrate_chapter(client, system_prompt, course_title, chapter, index, total, source):
    """为单讲生成 teaching events（一次 LLM 调用）"""
    if source == "transcript":
        task = (f"这是课程《{course_title}》第 {index} 讲「{chapter['title']}」的讲课记录。"
                f"请你按自己的教学风格，把它重新组织成结构化的板书 + 口播讲解，"
                f"保留原意但更有条理：\n\n{chapter.get('brief', '')}")
    else:
        task = (f"请系统讲解本讲主题：「{chapter['title']}」。"
                f"这是课程《{course_title}》的第 {index} 讲（共 {total} 讲）。"
                f"请完整、有条理地把这一讲讲透，包含必要的定义、公式、例子和小结。")

    # 教学插图：按章节标题+大纲检索候选注入 prompt（规则块与 demo 链路共用
    # media_library.build_image_prompt_block，两处保持一致）
    from media_library import retrieve_candidates, build_catalog, build_image_prompt_block
    image_candidates = retrieve_candidates(f"{chapter['title']} {str(chapter.get('brief', ''))[:300]}")
    image_block = build_image_prompt_block(image_candidates)

    prompt = f"{system_prompt}\n\n{_FORMAT_RULES}{image_block}\n\n讲解任务：{task}"
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=2500,
    )
    return _parse_demo_response(response.choices[0].message.content,
                                image_catalog=build_catalog(image_candidates))


def _generate_course(teacher_id, course_id):
    """后台线程：逐讲编排并落盘，实时更新 course.json 状态。"""
    card = load_teacher_card(teacher_id)
    course = load_course(teacher_id, course_id)
    if not card or not course:
        return
    system_prompt = _build_system_prompt(teacher_id, card)
    voice_id = card.get("voice_id", "")
    try:
        client = get_client()
    except Exception as e:
        for ch in course["chapters"]:
            ch["status"] = "error"
            ch["error"] = f"LLM 客户端初始化失败: {e}"
        course["status"] = "error"
        save_course(teacher_id, course)
        return

    total = len(course["chapters"])
    for ch in course["chapters"]:
        if ch.get("status") == "ready":
            continue
        ch["status"] = "generating"
        save_course(teacher_id, course)
        try:
            events = _orchestrate_chapter(client, system_prompt, course["title"],
                                          ch, ch["index"], total, course.get("source", "outline"))
            if not events:
                raise RuntimeError("未解析出有效教学事件")
            chdir = os.path.join(_course_dir(teacher_id, course_id), ch["chapter_id"])
            os.makedirs(chdir, exist_ok=True)
            with open(os.path.join(chdir, "events.json"), "w", encoding="utf-8") as f:
                json.dump({
                    "course_id": course_id,
                    "teacher_id": teacher_id,
                    "chapter_id": ch["chapter_id"],
                    "voice_id": voice_id,
                    "title": ch["title"],
                    "events": events,
                }, f, ensure_ascii=False, indent=2)
            ch["status"] = "ready"
            ch["events_count"] = len(events)
            ch["duration_sec"] = _estimate_duration(events)
            ch["error"] = None
        except Exception as e:
            ch["status"] = "error"
            ch["error"] = str(e)[:200]
        # 每讲完成即落盘，前端轮询可见增量进度
        latest = load_course(teacher_id, course_id) or course
        latest["chapters"] = course["chapters"]  # 以内存章节为准，保留 published 等外部改动
        course = latest
        save_course(teacher_id, course)

    statuses = [c["status"] for c in course["chapters"]]
    if all(s == "ready" for s in statuses):
        course["status"] = "ready"
    elif any(s == "ready" for s in statuses):
        course["status"] = "partial"
    else:
        course["status"] = "error"
    save_course(teacher_id, course)


def register_routes(app):
    @app.route("/api/v1/teachers/<teacher_id>/courses", methods=["POST"])
    @require_auth
    def create_course(teacher_id):
        card = load_teacher_card(teacher_id)
        if not card:
            return err("教师不存在", 4040, 404)
        if card.get("user_id") != request.user_id:
            return err("无权为该教师创建课程", 4030, 403)
        if not DEEPSEEK_API_KEY:
            return err("请配置 DEEPSEEK_API_KEY 后再编排课程", 5030, 503)

        data = request.json or {}
        title = (data.get("title") or "").strip()
        if not title:
            return err("请填写课程标题")
        source = data.get("source", "outline")
        if source not in ("outline", "transcript"):
            source = "outline"

        raw_chapters = data.get("chapters") or []
        chapters = []
        for rc in raw_chapters[:MAX_CHAPTERS]:
            t = (rc.get("title") or "").strip()
            if not t:
                continue
            n = len(chapters) + 1
            chapters.append({
                "chapter_id": f"ch{n}",
                "index": n,
                "title": t[:60],
                "brief": (rc.get("brief") or t)[:4000],
                "status": "pending",
                "events_count": 0,
                "duration_sec": 0,
                "events_url": "",
                "error": None,
            })
        if not chapters:
            return err("请至少提供一个章节")

        course_id = f"C_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(3)}"
        for ch in chapters:
            ch["events_url"] = f"{teacher_id}/courses/{course_id}/{ch['chapter_id']}/events.json"

        subj = card.get("subject", "")
        if isinstance(subj, list):
            subj = subj[0] if subj else ""

        course = {
            "course_id": course_id,
            "teacher_id": teacher_id,
            "user_id": request.user_id,
            "title": title,
            "subject": (data.get("subject") or subj or "").strip() if isinstance(data.get("subject") or subj, str) else subj,
            "summary": (data.get("summary") or "").strip() or (
                "由课程大纲自动编排生成。" if source == "outline" else "由讲课记录自动编排生成。"),
            "source": source,
            "status": "generating",
            "published": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "chapters": chapters,
        }
        save_course(teacher_id, course)
        threading.Thread(target=_generate_course, args=(teacher_id, course_id), daemon=True).start()
        return ok(course, "课程已创建，正在后台编排")

    @app.route("/api/v1/teachers/<teacher_id>/courses", methods=["GET"])
    @require_auth
    def get_courses(teacher_id):
        card = load_teacher_card(teacher_id)
        if not card:
            return err("教师不存在", 4040, 404)
        courses = list_courses(teacher_id)
        is_owner = card.get("user_id") == request.user_id
        if not is_owner:
            courses = [c for c in courses if c.get("published")]
        return ok(courses)

    @app.route("/api/v1/teachers/<teacher_id>/courses/<course_id>", methods=["GET"])
    @require_auth
    def get_course_detail(teacher_id, course_id):
        course = load_course(teacher_id, course_id)
        if not course:
            return err("课程不存在", 4040, 404)
        card = load_teacher_card(teacher_id)
        is_owner = card and card.get("user_id") == request.user_id
        if not course.get("published") and not is_owner:
            return err("课程未发布", 4030, 403)
        return ok(course)

    @app.route("/api/v1/teachers/<teacher_id>/courses/<course_id>/publish", methods=["POST"])
    @require_auth
    def publish_course(teacher_id, course_id):
        card = load_teacher_card(teacher_id)
        if not card or card.get("user_id") != request.user_id:
            return err("无权操作此课程", 4030, 403)
        course = load_course(teacher_id, course_id)
        if not course:
            return err("课程不存在", 4040, 404)
        course["published"] = True
        save_course(teacher_id, course)
        return ok(course, "课程已发布")

    @app.route("/api/v1/teachers/<teacher_id>/courses/<course_id>", methods=["DELETE"])
    @require_auth
    def delete_course(teacher_id, course_id):
        card = load_teacher_card(teacher_id)
        if not card or card.get("user_id") != request.user_id:
            return err("无权操作此课程", 4030, 403)
        import shutil
        d = _course_dir(teacher_id, course_id)
        if os.path.exists(d):
            shutil.rmtree(d, ignore_errors=True)
        return ok(None, "课程已删除")
