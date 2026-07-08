"""
teaching_events.py 离线单元测试。

不调用 Claude Agent SDK，只测试纯逻辑函数:
  - extract_json
  - unwrap_events
  - validate_events
  - 输入校验路径

运行:
    python modules/agent_generator/test_teaching_events.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import traceback
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))
# v2 路径调整: skill_distiller 现位于 modules/M2_distill/skill_distiller/
sys.path.insert(0, str(THIS_DIR.parents[2] / "M2_distill" / "skill_distiller"))

from teaching_events import (  # noqa: E402
    VALID_BOARD_ACTIONS,
    VALID_EVENT_TYPES,
    extract_json,
    generate_teaching_events,
    unwrap_events,
    validate_events,
)


# ============================================================
# 简易测试框架
# ============================================================
_passed: list[str] = []
_failed: list[tuple[str, str]] = []


def test(name: str):
    def decorator(fn):
        try:
            fn()
            _passed.append(name)
            print(f"  ✓ {name}")
        except AssertionError as e:
            _failed.append((name, str(e)))
            print(f"  ✗ {name}\n      AssertionError: {e}")
        except Exception:  # noqa: BLE001
            tb = traceback.format_exc()
            _failed.append((name, tb))
            print(f"  ✗ {name}\n      {tb}")
        return fn
    return decorator


def assert_eq(actual, expected, msg=""):
    assert actual == expected, f"{msg}\n  actual  : {actual!r}\n  expected: {expected!r}"


def assert_raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return
    except Exception as e:  # noqa: BLE001
        raise AssertionError(f"expected {exc_type.__name__}, got {type(e).__name__}: {e}")
    raise AssertionError(f"expected {exc_type.__name__}, no exception raised")


# ============================================================
# 1. extract_json
# ============================================================
print("\n[1] extract_json")


@test("纯 JSON 数组直接解析")
def _():
    assert_eq(extract_json('[1, 2, 3]'), [1, 2, 3])


@test("纯 JSON 对象直接解析")
def _():
    assert_eq(extract_json('{"a": 1}'), {"a": 1})


@test("剥离 ```json ... ``` markdown 代码块")
def _():
    raw = '```json\n{"a": 1}\n```'
    assert_eq(extract_json(raw), {"a": 1})


@test("剥离 ``` ... ``` markdown 代码块")
def _():
    raw = '```\n[1,2]\n```'
    assert_eq(extract_json(raw), [1, 2])


@test("前后混入解释文字（raw_decode 兜底）")
def _():
    raw = '这是结果:\n[10, 20, 30]\n仅供参考。'
    assert_eq(extract_json(raw), [10, 20, 30])


@test("无合法 JSON 时抛 ValueError")
def _():
    assert_raises(ValueError, extract_json, "no json here at all")


# ============================================================
# 2. unwrap_events
# ============================================================
print("\n[2] unwrap_events")


@test("顶层数组直接返回")
def _():
    data = [{"type": "speak", "text": "hi"}]
    assert_eq(unwrap_events(data), data)


@test("剥离 events 包装")
def _():
    data = {"events": [{"type": "speak", "text": "hi"}]}
    assert_eq(unwrap_events(data), [{"type": "speak", "text": "hi"}])


@test("剥离 result -> events 双层包装")
def _():
    data = {"result": {"events": [{"type": "speak", "text": "hi"}]}}
    assert_eq(unwrap_events(data), [{"type": "speak", "text": "hi"}])


@test("剥离 result -> data -> events 三层包装")
def _():
    data = {"result": {"data": {"events": [{"type": "speak", "text": "hi"}]}}}
    assert_eq(unwrap_events(data), [{"type": "speak", "text": "hi"}])


@test("api_contract 顶层对象（含 event_file_id + events）")
def _():
    data = {
        "event_file_id": "teaching_events_001",
        "question_id": "q_001",
        "events": [{"type": "speak", "text": "hi"}],
    }
    assert_eq(unwrap_events(data), [{"type": "speak", "text": "hi"}])


@test("剥到底仍非数组 -> ValueError")
def _():
    assert_raises(ValueError, unwrap_events, {"not_a_list": "value"})


@test("数组中含非对象元素 -> ValueError")
def _():
    assert_raises(ValueError, unwrap_events, [{"type": "speak"}, "bad"])


# ============================================================
# 3. validate_events — 各事件类型
# ============================================================
print("\n[3] validate_events")


@test("speak 事件最小字段")
def _():
    events = validate_events([{"type": "speak", "text": "我们先来看一个现象。"}])
    assert_eq(events[0]["seq"], 1)
    assert events[0]["event_id"].startswith("evt_")


@test("speak 缺 text -> ValueError")
def _():
    assert_raises(ValueError, validate_events, [{"type": "speak"}])


@test("board write_title 事件")
def _():
    events = validate_events([{
        "type": "board", "action": "write_title", "content": "过拟合",
    }])
    assert_eq(events[0]["action"], "write_title")


@test("board write_bullets 事件含数组 content")
def _():
    events = validate_events([{
        "type": "board", "action": "write_bullets",
        "content": ["训练集表现好", "测试集表现差"],
    }])
    assert isinstance(events[0]["content"], list)


@test("board 非法 action -> ValueError")
def _():
    assert_raises(ValueError, validate_events, [{
        "type": "board", "action": "draw_picture", "content": "x",
    }])


@test("board clear_board 可省略 content")
def _():
    events = validate_events([{"type": "board", "action": "clear_board"}])
    assert_eq(events[0]["action"], "clear_board")


@test("formula 事件")
def _():
    events = validate_events([{
        "type": "formula", "latex": "Train\\ Loss \\downarrow",
    }])
    assert_eq(events[0]["display_mode"], "block")


@test("formula 缺 latex -> ValueError")
def _():
    assert_raises(ValueError, validate_events, [{"type": "formula"}])


@test("table 事件 columns/rows 长度匹配")
def _():
    events = validate_events([{
        "type": "table",
        "columns": ["类型", "训练表现", "测试表现"],
        "rows": [["欠拟合", "差", "差"], ["过拟合", "好", "差"]],
    }])
    assert_eq(events[0]["type"], "table")


@test("table rows 长度不匹配 -> ValueError")
def _():
    assert_raises(ValueError, validate_events, [{
        "type": "table",
        "columns": ["a", "b"],
        "rows": [["x", "y", "z"]],  # 3 列 vs 2 列
    }])


@test("pause 事件默认 duration_ms")
def _():
    events = validate_events([{"type": "pause"}])
    assert_eq(events[0]["duration_ms"], 600)


@test("quiz 事件")
def _():
    events = validate_events([{
        "type": "quiz", "question": "什么是过拟合?",
        "options": ["A", "B"], "answer": "A",
    }])
    assert_eq(events[0]["type"], "quiz")


@test("非法 type -> ValueError")
def _():
    assert_raises(ValueError, validate_events, [{"type": "xxxx", "text": "x"}])


@test("seq 自动从 1 递增")
def _():
    events = validate_events([
        {"type": "speak", "text": "a"},
        {"type": "speak", "text": "b"},
        {"type": "speak", "text": "c"},
    ])
    assert_eq([e["seq"] for e in events], [1, 2, 3])


@test("event_id 自动填充为 evt_NNNN")
def _():
    events = validate_events([{"type": "speak", "text": "a"}])
    assert_eq(events[0]["event_id"], "evt_0001")


@test("已有 event_id 不被覆盖")
def _():
    events = validate_events([
        {"event_id": "custom_xx", "type": "speak", "text": "a"},
    ])
    assert_eq(events[0]["event_id"], "custom_xx")


# ============================================================
# 4. 与 demo_cases 样例兼容性
# ============================================================
print("\n[4] demo_cases 样例兼容性")

DEMO_PATH = Path("data/demo_cases/demo_case_001/teaching_events.json")


@test("demo_case_001/teaching_events.json 通过完整校验")
def _():
    if not DEMO_PATH.exists():
        print(f"      (skip — sample missing: {DEMO_PATH})")
        return
    data = json.loads(DEMO_PATH.read_text(encoding="utf-8"))
    events = unwrap_events(data)
    validate_events(events)
    assert len(events) > 0


@test("demo 样例所有 type 都在 VALID_EVENT_TYPES")
def _():
    if not DEMO_PATH.exists():
        return
    data = json.loads(DEMO_PATH.read_text(encoding="utf-8"))
    for ev in data["events"]:
        assert ev["type"] in VALID_EVENT_TYPES, f"unexpected type: {ev['type']}"


@test("demo 样例所有 board action 都在白名单")
def _():
    if not DEMO_PATH.exists():
        return
    data = json.loads(DEMO_PATH.read_text(encoding="utf-8"))
    for ev in data["events"]:
        if ev["type"] == "board":
            assert ev["action"] in VALID_BOARD_ACTIONS, \
                f"unexpected board action: {ev['action']}"


# ============================================================
# 5. generate_teaching_events 输入校验路径（不调 SDK）
# ============================================================
print("\n[5] 输入校验（错误路径）")


@test("空 question -> error")
def _():
    r = generate_teaching_events(
        question="  ",
        teacher_skill_path="/nope",
        retrieved_context_path="/nope",
        output_dir="/tmp/edunuwa_test_out",
    )
    assert_eq(r["status"], "error")
    assert "empty" in r["message"]


@test("缺 TeacherSkill 文件 -> error")
def _():
    with tempfile.TemporaryDirectory() as td:
        ctx = Path(td) / "ctx.md"
        ctx.write_text("# Retrieved Course Context\n\n## Query\n\nx")
        r = generate_teaching_events(
            question="什么是过拟合?",
            teacher_skill_path="/non/existent/skill.md",
            retrieved_context_path=str(ctx),
            output_dir=td,
        )
        assert_eq(r["status"], "error")
        assert "TeacherSkill not found" in r["message"]


@test("缺 retrieved_context 文件 -> error")
def _():
    with tempfile.TemporaryDirectory() as td:
        skill = Path(td) / "s.md"
        skill.write_text("# TeacherSkill: test\n\n## Skill Purpose\nx")
        r = generate_teaching_events(
            question="什么是过拟合?",
            teacher_skill_path=str(skill),
            retrieved_context_path="/non/existent/ctx.md",
            output_dir=td,
        )
        assert_eq(r["status"], "error")
        assert "retrieved_context not found" in r["message"]


# ============================================================
# 总结
# ============================================================
total = len(_passed) + len(_failed)
print(f"\n{'=' * 60}")
print(f"PASSED: {len(_passed)}/{total}    FAILED: {len(_failed)}")
if _failed:
    print("\nFailed tests:")
    for name, err in _failed:
        print(f"  - {name}\n    {err}")
    sys.exit(1)
print("ALL TESTS PASSED ✓")
sys.exit(0)
