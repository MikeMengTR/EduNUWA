#!/usr/bin/env python3
"""
多会话多批处理演示 —— 模拟不同 JSON 文件在不同时间到达不同 session，
系统自动检测并依次转换。

演示场景：
  文件 1 (t=0s)   → sessions/SES_physics_001/events/turn_1.json   大学物理
  文件 2 (t=30s)  → sessions/SES_math_002/events/turn_1.json      高等数学
  文件 3 (t=60s)  → sessions/SES_demo_recap/events/turn_1.json    函数复习
"""
from __future__ import annotations
import sys
import os
import json
import time
import shutil
import threading
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_DEMO_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
_MODULE_DIR = _DEMO_DIR.parent
_MODULES_DIR = _MODULE_DIR.parent
_PROJECT_ROOT = _MODULES_DIR.parent
sys.path.insert(0, str(_MODULES_DIR))

from stream.pipeline import StreamingPipeline
from M5_runtime.tts_service.tts_engine import _preprocess_tts_text

SEP = "═" * 66

# 演示用的教学事件（3 份不同学科的简版 JSON）
SESSION_CONFIGS = [
    {
        "session_id": "SES_physics_001",
        "topic": "大学物理 · 质点运动学",
        "title": "质点的描述",
        "events": [
            {"event_id": "evt_0001", "type": "board",  "seq": 1,  "action": "write_title", "content": "质点运动学"},
            {"event_id": "evt_0002", "type": "speak",  "seq": 2,  "text": "今天我们来学习质点的运动描述。首先要搞清楚什么是参考系。"},
            {"event_id": "evt_0003", "type": "board",  "seq": 3,  "action": "write_subtitle", "content": "参考系与坐标系"},
            {"event_id": "evt_0004", "type": "speak",  "seq": 4,  "text": "参考系是描述物体运动的标准框架。同一个运动在不同参考系中看起来不同。"},
            {"event_id": "evt_0005", "type": "pause",  "seq": 5,  "duration_sec": 2.0},
            {"event_id": "evt_0006", "type": "speak",  "seq": 6,  "text": "比如坐在火车上看另一辆火车，和站在地面上看，运动状态完全不同。"},
            {"event_id": "evt_0007", "type": "quiz",   "seq": 7,  "question": "以下哪个不是运动描述的基本要素？",
             "options": ["参考系", "质点", "速度方向", "运动方程"], "blocking": True},
        ]
    },
    {
        "session_id": "SES_math_002",
        "topic": "高等数学 · 导数概念",
        "title": "导数的定义",
        "events": [
            {"event_id": "evt_0001", "type": "board",  "seq": 1,  "action": "write_title", "content": "导数的定义"},
            {"event_id": "evt_0002", "type": "speak",  "seq": 2,  "text": "导数描述的是函数变化率。简单来说，就是函数在某一点的瞬时变化速度。"},
            {"event_id": "evt_0003", "type": "formula","seq": 3,  "latex": "f'(x)=\\lim_{\\Delta x\\to 0}\\frac{f(x+\\Delta x)-f(x)}{\\Delta x}",
             "display_mode": "block"},
            {"event_id": "evt_0004", "type": "speak",  "seq": 4,  "text": "这个极限定义是微积分的基石。它告诉我们函数在一点的变化趋势。"},
            {"event_id": "evt_0005", "type": "pause",  "seq": 5,  "duration_sec": 1.5},
            {"event_id": "evt_0006", "type": "speak",  "seq": 6,  "text": "几何意义上，导数就是曲线在该点切线的斜率。"},
        ]
    },
    {
        "session_id": "SES_demo_recap",
        "topic": "函数复习 · 回顾总结",
        "title": "函数的基本概念",
        "events": [
            {"event_id": "evt_0001", "type": "board",  "seq": 1,  "action": "write_title", "content": "函数的基本概念"},
            {"event_id": "evt_0002", "type": "speak",  "seq": 2,  "text": "我们来快速回顾一下函数的概念。给定一个x，就有唯一确定的y与之对应。"},
            {"event_id": "evt_0003", "type": "table",  "seq": 3,  "title": "表示方法",
             "columns": ["方法", "优点", "缺点"],
             "rows": [["解析式", "精确", "不直观"], ["图像", "直观", "不精确"]]},
            {"event_id": "evt_0004", "type": "speak",  "seq": 4,  "text": "函数的三要素是定义域、对应法则和值域。"},
            {"event_id": "evt_0005", "type": "quiz",   "seq": 5,  "question": "下列哪项不是函数的基本要素？",
             "options": ["定义域", "图像", "值域", "对应法则"], "blocking": True},
        ]
    },
]


def _create_session_events(config: dict) -> str:
    """Create teaching_events.json in the session's events directory."""
    session_dir = _PROJECT_ROOT / "data" / "sessions" / config["session_id"]
    events_dir = session_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)

    events_data = {
        "event_file_id": f"teaching_events_{config['session_id']}_t1",
        "question_id": f"q_{config['session_id']}_001",
        "session_id": config["session_id"],
        "turn": 1,
        "topic": config["topic"],
        "events": config["events"],
    }

    path = events_dir / "turn_1.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(events_data, f, ensure_ascii=False, indent=2)

    return str(path)


def _print_timing_table(sessions: list[dict], start_time: float, results: dict):
    """Print final timing summary table."""
    print(f"\n{SEP}")
    print(f"  多会话多批处理 — 时序汇总")
    print(f"{SEP}")
    print(f"  {'会话':25s} {'到达时间':>12s} {'事件数':>8s} {'音频':>8s} {'耗时':>8s} {'结果'}")
    print(f"  {'-'*25} {'-'*12} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for s in sessions:
        sid = s["session_id"]
        r = results.get(sid, {})
        arrival = s.get("arrival_time", 0)
        count = r.get("timeline_count", r.get("event_count", 0))
        audio = r.get("audio_count", 0)
        elapsed = r.get("elapsed_sec", 0)
        status = "✅" if r.get("status") == "success" else "❌"
        print(f"  {sid:25s} {arrival:>5.0f}s  {count:>6d}  {audio:>6d}  {elapsed:>5.0f}s  {status}")
    print()


def main():
    print(f"\n{SEP}")
    print(f"  多会话多批处理演示")
    print(f"  EduNUWA v2 · Stream Pipeline Auto-Watch")
    print(f"{SEP}")
    print(f"  模拟 3 份 JSON 在不同时间到达不同 session")
    print(f"  系统自动检测新文件 → 流式输出 + TTS 合成 → 产出 playback_data")
    print()

    # Step 1: 清理旧数据
    clean = "--clean" in sys.argv
    skip_tts = "--skip-tts" in sys.argv

    if clean:
        print(f"  清理旧数据...")
        for s in SESSION_CONFIGS:
            session_dir = _PROJECT_ROOT / "data" / "sessions" / s["session_id"]
            if session_dir.exists():
                shutil.rmtree(str(session_dir))

    # Step 2: 打印每个会话的配置
    print(f"  {'会话ID':25s} {'学科':20s} {'事件数':>8s}")
    print(f"  {'-'*25} {'-'*20} {'-'*8}")
    for s in SESSION_CONFIGS:
        print(f"  {s['session_id']:25s} {s['topic']:20s} {len(s['events']):>5d}")
    print()

    # Step 3: 模拟文件陆续到达 + 自动处理
    print(f"{SEP}")
    print(f"  开始模拟文件到达...\n")

    results = {}
    pipeline = StreamingPipeline()
    t_start = time.time()

    for i, config in enumerate(SESSION_CONFIGS):
        # 模拟文件在不同时间到达
        if i > 0:
            gap = 5  # 间隔 5 秒
            print(f"  ⏳ 等待 {gap}s 模拟下一文件到达...")
            time.sleep(gap)

        # 写入事件文件
        events_path = _create_session_events(config)
        arrival = time.time() - t_start
        config["arrival_time"] = arrival
        print(f"  📥 [{arrival:3.0f}s] 文件到达: {config['session_id']} ({config['topic']})")

        # 自动处理
        t_proc = time.time()
        result = pipeline.run(
            events_path=events_path,
            teacher_card_path=str(_PROJECT_ROOT / "data" / "teachers" / "T_20260515_001" / "teacher_card.json"),
            voice_id="songhao_teacher",
            wait_tts=not skip_tts,
        )
        proc_time = time.time() - t_proc
        result["elapsed_sec"] = round(proc_time, 1)
        results[config["session_id"]] = result

        status_icon = "✅" if result.get("status") == "success" else "❌"
        print(f"  {status_icon} [{arrival:3.0f}s] 完成: {result.get('timeline_count', 0)} events, "
              f"耗时 {proc_time:.0f}s")
        if "audio_count" in result:
            print(f"         音频: {result.get('audio_count', 0)} 段, "
                  f"时长: {result.get('total_duration_sec', 0):.1f}s")
        print()

    # Step 4: 时序汇总
    _print_timing_table(SESSION_CONFIGS, t_start, results)

    # Step 5: 查看生成的 playback_data
    print(f"  生成的播放数据：")
    for s in SESSION_CONFIGS:
        sid = s["session_id"]
        playback = _PROJECT_ROOT / "data" / "sessions" / sid / "playback_data.json"
        if playback.exists():
            size = os.path.getsize(playback) // 1024
            print(f"    📄 {sid}/playback_data.json  ({size}KB)")

    print(f"\n{SEP}")
    print(f"  演示完成！")
    print(f"  --skip-tts  跳过 TTS 快速演示")
    print(f"  --clean     清理旧数据后重来")
    print(f"{SEP}\n")


if __name__ == "__main__":
    main()
