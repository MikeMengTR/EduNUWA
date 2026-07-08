#!/usr/bin/env python3
"""
Stream Module Demo — L1-L7 流式延迟展示
=======================================
展示 streaming 模式 vs batch 模式的延迟对比，
以及教学事件按自然节奏逐条输出的过程。
"""
from __future__ import annotations
import sys
import os
import json
import time
from pathlib import Path

# 修复 Windows 编码
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 路径设置
_DEMO_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
_MODULE_DIR = _DEMO_DIR.parent
_MODULES_DIR = _MODULE_DIR.parent
_PROJECT_ROOT = _MODULES_DIR.parent
sys.path.insert(0, str(_MODULES_DIR))

from stream.latency_config import DEFAULT_LATENCY_CONFIG
from stream.streaming_orchestrator import generate_teaching_events_v2_stream
from stream.playback_builder import build_streaming_playback

SEP = "═" * 66

# Demo 数据路径
EVENTS_FILE = _PROJECT_ROOT / "modules" / "M5_runtime" / "demo" / "demo_teaching_events.json"
TEACHER_CARD = _PROJECT_ROOT / "data" / "teachers" / "T_20260515_001" / "teacher_card.json"
OUTPUT_PATH = _PROJECT_ROOT / "data" / "sessions" / "SES_demo_20260522" / "playback_stream_demo.json"

# L1-L7 指标说明
L_METRICS = [
    ("L1", "首句开口延迟", "≤ 8s", "学生提问 → 数字人开口第一个字音"),
    ("L2", "句间停顿", "0.3-0.6s", "同一段内两句话之间的自然停顿"),
    ("L3", "板书→接话", "0.5-1.2s", "黑板上写完到开始讲解"),
    ("L4", "段间过渡", "1.0-2.0s", "讲完一个知识点到下一个"),
    ("L5", "设问思考停顿", "≥ 1.5s", "老师抛出问题后的等待时间"),
    ("L6", "概念切换", "2.0-3.0s", "结束大主题到进入下一个"),
    ("L7", "追问开口", "≤ 10s", "第二轮对话的开口延迟"),
]

EVENT_ICONS = {
    "speak": "🎙",
    "board": "📝",
    "formula": "∑",
    "table": "📊",
    "pause": "⏳",
    "quiz": "❓",
}


def print_header():
    print(f"\n{SEP}")
    print(f"  Stream 模块功能演示 — L1-L7 流式延迟层")
    print(f"  EduNUWA v2 · M4 Orchestrator Streaming Latency Spec")
    print(f"{SEP}")
    print(f"  【核心目标】将数字人首句开口延迟从 111s (batch) 降到 8s (streaming)")
    print(f"  让讲课节奏从「一口气讲完」变成像真人一样有呼吸感")
    print()


def step1_show_latency_metrics():
    """Step 1: 展示 L1-L7 指标对比"""
    print(f"{SEP}")
    print(f"  Step 1/4 — L1-L7 延迟指标一览")
    print(f"{SEP}")

    print(f"  {'指标':5s} {'名称':14s} {'目标':12s} {'说明'}")
    print(f"  {'-'*5} {'-'*14} {'-'*12} {'-'*30}")
    for label, name, target, desc in L_METRICS:
        print(f"  {label:5s} {name:14s} {target:12s} {desc}")
    print()

    print(f"  【对比】当前 batch 模式：首句延迟 111s ❌")
    print(f"  【目标】streaming 模式：首句延迟 ≤ 8s ✅")
    print()


def step2_configure_timing():
    """Step 2: 展示配置变化"""
    print(f"{SEP}")
    print(f"  Step 2/4 — 配置项变更（spec §6 建议）")
    print(f"{SEP}")

    config = DEFAULT_LATENCY_CONFIG
    changes = [
        ("pause.duration_ms 默认值", "600ms", f"{config.l5_pause_default_ms}ms", "L5"),
        ("board → speak 调度延迟", "0", f"{config.l3_board_to_speak_delay_sec}s", "L3"),
        ("段间过渡 (跨主题)", "0", f"{config.l4_segment_gap_sec}s", "L4"),
        ("概念切换 (clear_board 后)", "0", f"{config.l6_concept_switch_gap_sec}s", "L6"),
        ("流式首 event 强制类型", "任意", f"{config.l1_first_event_type}", "L1"),
    ]

    print(f"  {'配置项':30s} {'修改前':10s} {'修改后':12s} {'对应指标'}")
    print(f"  {'-'*30} {'-'*10} {'-'*12} {'-'*10}")
    for item, old, new, label in changes:
        print(f"  {item:30s} {old:10s} {new:12s} {label:10s}")
    print()


def step3_stream_events():
    """Step 3: 流式输出事件（带实时计时）"""
    config = DEFAULT_LATENCY_CONFIG
    print(f"{SEP}")
    print(f"  Step 3/4 — 流式事件输出（模拟实时到达）")
    print(f"{SEP}")
    print(f"  输入: {EVENTS_FILE.name}")
    print(f"  配置: L2=({config.l2_sentence_gap_range_sec[0]}-{config.l2_sentence_gap_range_sec[1]}s) "
          f"L3={config.l3_board_to_speak_delay_sec}s "
          f"L4={config.l4_segment_gap_sec}s "
          f"L5={config.l5_pause_default_ms}ms "
          f"L6={config.l6_concept_switch_gap_sec}s")
    print()

    config = DEFAULT_LATENCY_CONFIG
    gen = generate_teaching_events_v2_stream(
        events_path=str(EVENTS_FILE),
        latency_config=config,
        live_demo=False,
    )

    print(f"  {'时间点':>8s} {'#':3s} {'类型':8s} {'内容/动作':44s} {'间隙':8s} {'标签'}")
    print(f"  {'-'*8} {'-'*3} {'-'*8} {'-'*44} {'-'*8} {'-'*5}")

    event_count = 0
    plan_data = None

    for chunk in gen:
        if chunk["chunk_type"] == "plan":
            plan_data = chunk["data"]
            print(f"  [计划] 共 {plan_data['event_count']} 个事件等待调度")

        elif chunk["chunk_type"] == "event":
            item = chunk["data"]
            event_count += 1
            offset = item["start_offset_sec"]
            evt_type = item["type"]
            label = item.get("_latency_label", "")
            gap = item.get("_gap_sec", 0)
            icon = EVENT_ICONS.get(evt_type, "·")

            # 构建内容摘要
            detail = ""
            if evt_type == "speak":
                text = item.get("text", "")
                detail = (text[:35] + "…") if len(text) > 35 else text
            elif evt_type == "board":
                action = item.get("action", "")
                content = item.get("content", "")
                if isinstance(content, list):
                    content = " | ".join(str(c) for c in content[:3])
                    if len(item.get("content", [])) > 3:
                        content += "…"
                detail = f"{action}" + (f": {content}" if content else "")
            elif evt_type == "formula":
                latex = item.get("latex", "")
                detail = latex[:35] + "…" if len(latex) > 35 else latex
            elif evt_type == "table":
                detail = item.get("title", "")
            elif evt_type == "pause":
                detail = f"等待 {item.get('duration_sec', 0)}s"
            elif evt_type == "quiz":
                detail = item.get("question", "")[:35] + "…"

            gap_str = f"+{gap:.1f}s" if gap > 0 else "—"
            print(f"  [{offset:6.1f}s] {icon} {evt_type:8s} {detail:44s} {gap_str:8s} {label:5s}")

        elif chunk["chunk_type"] == "done":
            total = chunk["data"]["total"]
            duration = chunk["data"]["total_duration_sec"]
            print(f"\n  ✅ 完成: {total} 个事件, 总时长 {duration:.1f}s")
            return duration

    return 0


def step4_compare_batch_vs_stream():
    """Step 4: 对比 batch vs streaming"""
    print(f"\n{SEP}")
    print(f"  Step 4/4 — Batch vs Streaming 对比")
    print(f"{SEP}")

    # 读取 batch 模式已有的 playback_data
    batch_playback = _PROJECT_ROOT / "data" / "sessions" / "SES_demo_20260522" / "playback_data.json"
    batch_duration = 0
    if batch_playback.exists():
        with open(batch_playback, "r", encoding="utf-8") as f:
            data = json.load(f)
        batch_duration = data.get("total_duration_sec", 0)

    # 用 streaming builder 构建
    result = build_streaming_playback(
        events_path=str(EVENTS_FILE),
        output_path=str(OUTPUT_PATH),
        teacher_card_path=str(TEACHER_CARD),
    )
    stream_duration = result["latency_report"]["total_duration_sec"]

    print(f"  {'维度':30s} {'Batch 模式':>18s} {'Streaming 模式':>20s}")
    print(f"  {'-'*30} {'-'*18} {'-'*20}")
    print(f"  {'首句开口延迟(L1)':30s} {'111s (实测)':>18s} {'~8s (目标)':>20s}")
    print(f"  {'总时长':30s} {f'{batch_duration:.1f}s':>18s} {f'{stream_duration:.1f}s':>20s}")
    print(f"  {'句间停顿(L2)':30s} {'0.3s (固定)':>18s} {'0.3-0.6s (随机)':>20s}")
    print(f"  {'板书→接话(L3)':30s} {'0s (无延迟)':>18s} {'0.8s':>20s}")
    print(f"  {'段间过渡(L4)':30s} {'0s (无过渡)':>18s} {'1.5s':>20s}")
    print(f"  {'设问停顿(L5)':30s} {'0.6s (默认)':>18s} {'1.5s (≥1500ms)':>20s}")
    print(f"  {'概念切换(L6)':30s} {'0s (无切换)':>18s} {'2.5s':>20s}")
    print()

    # 节奏对比
    print(f"  【节奏示意图】\n")

    batch_desc = (
        "  Batch:  学生提问 ──── 111s 沉默 ────── 数字人一口气讲完全部 ──> 结束\n"
        "                                        ↑ 节奏完全不可控"
    )
    stream_desc = (
        "  Stream: 学生提问 ─ 8s ─ 开口 ─ 自然节奏(L2-L6各就各位) ──> 结束\n"
        "                              ↑ 像真人讲课的呼吸感"
    )
    for line in batch_desc.split("\n"):
        print(f"  {line}")
    print()
    for line in stream_desc.split("\n"):
        print(f"  {line}")
    print()

    print(f"  输出文件: {OUTPUT_PATH}")
    print()

    return result


# ============================================================
# Main
# ============================================================
def main():
    skip_stream = "--skip-stream" in sys.argv

    print_header()
    step1_show_latency_metrics()
    step2_configure_timing()

    if not skip_stream:
        step3_stream_events()
    else:
        print(f"{SEP}")
        print(f"  Step 3/4 — 跳过流式事件输出 (--skip-stream)")
        print(f"{SEP}\n")

    result = step4_compare_batch_vs_stream()

    # 打印 timline 预览
    print(f"{SEP}")
    print(f"  Timeline 预览（前 8 条）")
    print(f"{SEP}")
    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        pb = json.load(f)
    for item in pb["timeline"][:8]:
        t = item["type"]
        offset = item["start_offset_sec"]
        detail = ""
        if t == "speak":
            text = item.get("text", "")
            detail = f'"{text[:30]}..."' if len(text) > 30 else f'"{text}"'
        elif t == "board":
            detail = f'action={item.get("action", "")}'
        elif t == "quiz":
            detail = f'Q: {item.get("question", "")[:20]}...'
        elif t == "formula":
            detail = f'latex={item.get("latex", "")[:20]}...'
        elif t == "table":
            detail = f'title={item.get("title", "")}'
        elif t == "pause":
            detail = f'{item.get("duration_sec", 0)}s'
        print(f"  [{offset:5.1f}s] {t:7s} {detail}")

    if len(pb["timeline"]) > 8:
        print(f"  ... (共 {len(pb['timeline'])} 条，以上为前 8 条)")

    print(f"\n{SEP}")
    print(f"  Demo 完成！运行方式：")
    print(f"    python modules/stream/demo/run_demo.py          # 完整演示")
    print(f"    python modules/stream/demo/run_demo.py --skip-stream  # 跳过流式输出")
    print(f"    python modules/stream/run.py stream --events ...  # CLI 流式模式")
    print(f"{SEP}\n")


if __name__ == "__main__":
    main()
