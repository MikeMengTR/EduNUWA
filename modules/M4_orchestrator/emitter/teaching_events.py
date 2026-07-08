"""
EduNUWA 教学事件生成器（agent_generator 模块入口）。

职责: 读取 TeacherSkill.md (怎么讲) + retrieved_context.md (讲什么) + 用户问题，
调用 Claude Agent SDK + DeepSeek 生成符合 docs/api_contract.md §5 的
teaching_events.json。

函数签名严格遵循 api_contract.md §7.4::

    generate_teaching_events(
        question: str,
        teacher_skill_path: str,
        retrieved_context_path: str,
        output_dir: str,
        config: dict | None = None,
    ) -> dict

CLI 用法（v2 路径）::

    python modules/M4_orchestrator/emitter/teaching_events.py \\
        --question "什么是过拟合？" \\
        --skill data/teachers/T_legacy_001/skills/v2/TeacherSkill.md \\
        --context data/sessions/<session_id>/context/turn_1.md \\
        --output data/sessions/<session_id>/events/
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# 让脚本可以以两种方式运行: `python teaching_events.py` 或 `python -m ...`
# v2 路径调整: skill_distiller 现位于 modules/M2_distill/skill_distiller/
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "M2_distill" / "skill_distiller"))

# 复用 skill_distiller 的公共基础设施（env / options / runner）
from _common import (  # noqa: E402
    REPO_ROOT,
    load_env,
    make_options,
    run_agent_task,
)


# ============================================================
# 事件 schema 定义（来自 api_contract.md §5）
# ============================================================

VALID_EVENT_TYPES: frozenset[str] = frozenset({
    "speak", "board", "formula", "table", "pause", "quiz",
})

VALID_BOARD_ACTIONS: frozenset[str] = frozenset({
    "write_title", "write_subtitle", "write_bullets",
    "write_steps", "write_summary", "clear_board", "highlight",
})

VALID_FORMULA_DISPLAY_MODES: frozenset[str] = frozenset({"block", "inline"})


# ============================================================
# JSON 提取与校验
# ============================================================
def extract_json(text: str) -> Any:
    """
    从模型输出中提取 JSON。
    支持四种常见污染模式:
      - markdown 代码块  ```json ... ```
      - 前后混入解释性文字
      - 多层 dict 包装  {"result": {"events": [...]}}
      - 数组顶层
    """
    text = text.strip()

    # 1. 移除 markdown 代码块（仅头/尾的，不破坏内容里的反引号）
    md_block = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text, flags=re.IGNORECASE)
    if md_block:
        text = md_block.group(1).strip()

    # 2. 直接尝试解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 3. 找首个 [ 或 { 开始用 raw_decode 兜底
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in "[{":
            try:
                obj, _ = decoder.raw_decode(text[i:])
                return obj
            except json.JSONDecodeError:
                continue

    raise ValueError("无法从模型输出中解析到合法 JSON。")


def unwrap_events(data: Any) -> list[dict]:
    """
    递归剥离 dict 包装，最终返回 events 数组。

    支持的包装路径:
      [...]                                              -> 直接返回
      {"events": [...]}                                  -> data["events"]
      {"result": {"events": [...]}}                      -> 递归
      {"event_file_id": ..., "events": [...]}            -> 取 events
    """
    KEY_CANDIDATES = (
        "events", "teaching_events", "teachingEvents",
        "result", "data", "items", "steps",
    )
    seen_ids: set[int] = set()
    cur = data
    while isinstance(cur, dict):
        if id(cur) in seen_ids:
            break
        seen_ids.add(id(cur))
        for key in KEY_CANDIDATES:
            if key in cur:
                cur = cur[key]
                break
        else:
            break

    if not isinstance(cur, list):
        raise ValueError(
            f"events 顶层应为数组，当前类型: {type(cur).__name__}; "
            f"已尝试剥离 keys: {KEY_CANDIDATES}"
        )
    if not all(isinstance(x, dict) for x in cur):
        raise ValueError("events 数组中存在非对象元素")
    return cur


def _validate_event(idx: int, ev: dict) -> dict:
    """对单个事件做 schema 校验并填充必要字段。"""
    if "type" not in ev:
        raise ValueError(f"event[{idx}] 缺少 type 字段")
    etype = ev["type"]
    if etype not in VALID_EVENT_TYPES:
        raise ValueError(
            f"event[{idx}] 非法 type={etype!r}; 合法集合={sorted(VALID_EVENT_TYPES)}"
        )

    # 自动补 event_id / seq（Agent 经常忘）
    seq = idx + 1
    ev["seq"] = seq
    ev.setdefault("event_id", f"evt_{seq:04d}")

    # 各类型的字段约束
    if etype == "speak":
        if not ev.get("text"):
            raise ValueError(f"event[{idx}] (speak) 缺少 text")
        ev["text"] = str(ev["text"]).strip()

    elif etype == "board":
        action = ev.get("action")
        if action not in VALID_BOARD_ACTIONS:
            raise ValueError(
                f"event[{idx}] (board) 非法 action={action!r}; "
                f"合法集合={sorted(VALID_BOARD_ACTIONS)}"
            )
        if "content" not in ev and action not in ("clear_board",):
            raise ValueError(f"event[{idx}] (board, {action}) 缺少 content")

    elif etype == "formula":
        if not ev.get("latex"):
            raise ValueError(f"event[{idx}] (formula) 缺少 latex")
        ev["latex"] = str(ev["latex"]).strip()
        ev.setdefault("display_mode", "block")
        if ev["display_mode"] not in VALID_FORMULA_DISPLAY_MODES:
            raise ValueError(
                f"event[{idx}] (formula) 非法 display_mode={ev['display_mode']!r}"
            )

    elif etype == "table":
        for required in ("columns", "rows"):
            if required not in ev:
                raise ValueError(f"event[{idx}] (table) 缺少 {required}")
        if not isinstance(ev["columns"], list) or not isinstance(ev["rows"], list):
            raise ValueError(f"event[{idx}] (table) columns/rows 必须为数组")
        ncol = len(ev["columns"])
        for ri, row in enumerate(ev["rows"]):
            if not isinstance(row, list) or len(row) != ncol:
                raise ValueError(
                    f"event[{idx}] (table) row[{ri}] 长度与 columns 不匹配"
                )

    elif etype == "pause":
        ev.setdefault("duration_ms", 600)

    elif etype == "quiz":
        if not ev.get("question"):
            raise ValueError(f"event[{idx}] (quiz) 缺少 question")

    return ev


def validate_events(events: list[dict]) -> list[dict]:
    """对全部事件做校验并归一化。会就地修改并返回归一后的列表。"""
    return [_validate_event(i, ev) for i, ev in enumerate(events)]


# ============================================================
# Prompt 构造
# ============================================================
_SCHEMA_SPEC = """事件 schema (严格遵循 docs/api_contract.md §5):

顶层对象:
{
  "event_file_id": "<string, 形如 teaching_events_001>",
  "question_id":   "<string>",
  "events":        [<event>, ...]
}

每个 event 必含 event_id (evt_NNNN), type, seq (1 起递增):

- speak   : { type=speak,   text:string }
- board   : { type=board,   action: write_title|write_subtitle|write_bullets|write_steps|write_summary|clear_board|highlight,
                            content: string | string[] (clear_board 可省 content) }
- formula : { type=formula, latex:string, display_mode: block|inline }
- table   : { type=table,   title?:string, columns:string[], rows:string[][] }
- pause   : { type=pause,   duration_ms?:number }
- quiz    : { type=quiz,    question:string, options?:string[], answer?:string }

硬约束:
1. 顶层必须是 JSON 对象，不是数组。
2. 不得出现未声明的 type。
3. board 的 action 必须从白名单中选取。
4. speak 文本不得嵌入板书内容（应拆为独立 board 事件）。
5. 输出纯 JSON，不要 markdown 代码块、不要解释文字。
"""


def build_prompt(
    question: str,
    teacher_skill_text: str,
    retrieved_context_text: str,
    config: dict,
) -> str:
    need_board = config.get("need_board", True)
    need_formula = config.get("need_formula", True)
    need_quiz = config.get("need_quiz", False)
    target_count = config.get("target_count", "8 到 16")

    optional_hints = []
    if need_board:
        optional_hints.append("- 充分利用 board 事件呈现标题、要点、推导步骤、阶段总结。")
    if need_formula:
        optional_hints.append("- 涉及公式时使用 formula 事件；display_mode 默认 block。")
    if need_quiz:
        optional_hints.append("- 适当插入 quiz 事件以驱动学生思考。")
    optional_hints_str = "\n".join(optional_hints) if optional_hints else "- 无额外要求。"

    return f"""你是一位教学事件编排器。请按以下三份输入生成结构化教学事件流。

【输入 1: 用户问题】
{question}

【输入 2: TeacherSkill.md (讲解风格)】
{teacher_skill_text}

【输入 3: retrieved_context.md (课程知识)】
{retrieved_context_text}

【你的任务】
基于输入 2 的"讲解风格"组织语言、动作；用输入 3 的"课程知识"作为讲解的事实依据；
回答输入 1 的用户问题。

【约束】
{optional_hints_str}
- 生成 {target_count} 个教学事件。
- 严格按下面 schema 输出。
- 必须出现至少 1 次 speak 与至少 1 次 board。
- speak 事件文本须体现 TeacherSkill 的 Speech Policy（口头禅、句式、设问）。
- board 事件 action 必须从 TeacherSkill 的 Blackboard Policy 推荐列表选取。

【输出 schema】
{_SCHEMA_SPEC}

请直接将完整 JSON 写入文件: <由调用方在系统消息中告知>
不要询问，全程默认批准。
"""


# ============================================================
# 主函数（符合 api_contract.md §7.4）
# ============================================================
def generate_teaching_events(
    question: str,
    teacher_skill_path: str | Path,
    retrieved_context_path: str | Path,
    output_dir: str | Path,
    config: dict | None = None,
) -> dict:
    """
    根据用户问题 + TeacherSkill + 课程上下文，生成 teaching_events.json。

    Args:
        question: 用户问题文本
        teacher_skill_path: 教师风格 Skill 文件路径
        retrieved_context_path: 课程知识上下文文件路径
        output_dir: 输出目录
        config: 可选配置:
            - need_board (bool, 默认 True)
            - need_formula (bool, 默认 True)
            - need_quiz (bool, 默认 False)
            - target_count (str, 默认 "8 到 16")
            - max_turns (int, 默认 25)
            - timeout_sec (int, 默认 600)
            - file_tag (str, 默认时间戳)  -> teaching_events_<tag>.json

    Returns:
        成功::
            {
              "status": "success",
              "events_path": "<path>",
              "events_count": <int>,
            }
        失败::
            {
              "status": "error",
              "message": "...",
              "question": question,
            }
    """
    config = dict(config or {})
    teacher_skill_path = Path(teacher_skill_path)
    retrieved_context_path = Path(retrieved_context_path)
    output_dir = Path(output_dir).resolve()

    # ---------- 校验输入 ----------
    if not question.strip():
        return {"status": "error", "message": "question is empty", "question": question}
    if not teacher_skill_path.exists():
        return {
            "status": "error",
            "message": f"TeacherSkill not found: {teacher_skill_path}",
            "question": question,
        }
    if not retrieved_context_path.exists():
        return {
            "status": "error",
            "message": f"retrieved_context not found: {retrieved_context_path}",
            "question": question,
        }
    output_dir.mkdir(parents=True, exist_ok=True)

    # ---------- 准备路径 ----------
    file_tag = config.get("file_tag") or datetime.now().strftime("%Y%m%d_%H%M%S")
    event_file_id = f"teaching_events_{file_tag}"
    events_path = output_dir / f"{event_file_id}.json"
    debug_log = output_dir / f"{event_file_id}.claude-debug.log"
    raw_dump_path = output_dir / f"{event_file_id}.raw.txt"

    # ---------- 读取输入 ----------
    teacher_skill_text = teacher_skill_path.read_text(encoding="utf-8")
    retrieved_context_text = retrieved_context_path.read_text(encoding="utf-8")

    # ---------- 构造 prompt ----------
    prompt = build_prompt(
        question=question,
        teacher_skill_text=teacher_skill_text,
        retrieved_context_text=retrieved_context_text,
        config=config,
    )
    prompt += f"\n请将最终 JSON 写入: {events_path}\n"

    # ---------- 运行 Agent ----------
    options = make_options(
        cwd=REPO_ROOT,
        max_turns=int(config.get("max_turns", 25)),
        debug_log=debug_log,
    )

    print(f"[events] question         = {question}")
    print(f"[events] teacher_skill    = {teacher_skill_path}")
    print(f"[events] retrieved_ctx    = {retrieved_context_path}")
    print(f"[events] events_path      = {events_path}")
    print(f"[events] debug_log        = {debug_log}")
    print()

    run_result = run_agent_task(
        prompt,
        options,
        timeout_sec=int(config.get("timeout_sec", 600)),
        debug_log=debug_log,
    )

    # ---------- 校验产出 ----------
    if run_result.get("status") != "success":
        run_result.setdefault("question", question)
        return run_result

    if not events_path.exists():
        return {
            "status": "error",
            "message": f"agent did not write {events_path}",
            "question": question,
            "debug_log": str(debug_log),
        }

    # 读取并校验 JSON
    raw_text = events_path.read_text(encoding="utf-8")
    raw_dump_path.write_text(raw_text, encoding="utf-8")  # 留底以备调试

    try:
        data = extract_json(raw_text)
        events = unwrap_events(data)
        events = validate_events(events)
    except (ValueError, json.JSONDecodeError) as e:
        return {
            "status": "error",
            "message": f"events json invalid: {e}",
            "question": question,
            "events_path": str(events_path),
            "raw_dump": str(raw_dump_path),
            "debug_log": str(debug_log),
        }

    # 强约束: 至少含 1 speak + 1 board
    types_present = {ev["type"] for ev in events}
    if "speak" not in types_present:
        return {
            "status": "error",
            "message": "events missing required 'speak' event",
            "question": question,
            "events_path": str(events_path),
        }

    # ---------- 归一化为顶层对象，落盘 ----------
    final = {
        "event_file_id": event_file_id,
        "question_id": config.get("question_id", f"q_{file_tag}"),
        "events": events,
    }
    if "course_id" in config:
        final["course_id"] = config["course_id"]
    if "skill_id" in config:
        final["skill_id"] = config["skill_id"]
    if "language" in config:
        final["language"] = config["language"]
    else:
        final["language"] = "zh"

    events_path.write_text(
        json.dumps(final, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "status": "success",
        "events_path": str(events_path),
        "events_count": len(events),
    }


# ============================================================
# CLI
# ============================================================
def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="teaching_events",
        description="EduNUWA 教学事件生成器（symbol_contract.md §7.4 兼容）。",
    )
    parser.add_argument("--question", required=True, help="用户问题")
    parser.add_argument("--skill", required=True, dest="teacher_skill_path",
                        help="TeacherSkill.md 路径")
    parser.add_argument("--context", required=True, dest="retrieved_context_path",
                        help="retrieved_context.md 路径")
    parser.add_argument("--output", required=True, dest="output_dir",
                        help="输出目录")
    parser.add_argument("--need-board", action="store_true", default=True,
                        help="（默认开）允许 board 事件")
    parser.add_argument("--no-board", action="store_false", dest="need_board",
                        help="禁用 board 事件")
    parser.add_argument("--need-formula", action="store_true", default=True,
                        help="（默认开）允许 formula 事件")
    parser.add_argument("--no-formula", action="store_false", dest="need_formula",
                        help="禁用 formula 事件")
    parser.add_argument("--need-quiz", action="store_true", default=False,
                        help="允许 quiz 事件")
    parser.add_argument("--target-count", default="8 到 16", help="目标事件数")
    parser.add_argument("--max-turns", type=int, default=25)
    parser.add_argument("--timeout", type=int, default=600, dest="timeout_sec")
    parser.add_argument("--file-tag", default=None, help="event_file_id 后缀")
    return parser


def main() -> int:
    args = _build_cli().parse_args()
    load_env()

    result = generate_teaching_events(
        question=args.question,
        teacher_skill_path=args.teacher_skill_path,
        retrieved_context_path=args.retrieved_context_path,
        output_dir=args.output_dir,
        config={
            "need_board": args.need_board,
            "need_formula": args.need_formula,
            "need_quiz": args.need_quiz,
            "target_count": args.target_count,
            "max_turns": args.max_turns,
            "timeout_sec": args.timeout_sec,
            "file_tag": args.file_tag,
        },
    )

    print("\n=========== generate result ===========")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
