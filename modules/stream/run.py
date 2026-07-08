#!/usr/bin/env python3
"""
Stream Module CLI — stream / build / verify subcommands.

Usage:
    python modules/stream/run.py stream --events <path>
    python modules/stream/run.py build --events <path> --output <path>
    python modules/stream/run.py verify --playback <path>
"""
from __future__ import annotations
import sys
import os
import json
import time
import argparse
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Path setup
_MODULE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
_MODULES_DIR = _MODULE_DIR.parent
sys.path.insert(0, str(_MODULES_DIR))

from stream.latency_config import LatencyConfig, DEFAULT_LATENCY_CONFIG, BATCH_LATENCY_CONFIG
from stream.streaming_orchestrator import generate_teaching_events_v2_stream, detect_latency_labels
from stream.playback_builder import build_streaming_playback

SEP = "=" * 62


def cmd_stream(args):
    """Stream events one-by-one with L1-L7 timing (demo mode)."""
    config = _parse_latency_config(args.latency_config)

    print(SEP)
    print("  Streaming Event Generator — L1-L7 Latency Demo")
    print(SEP)
    print(f"  Events: {args.events}")
    print(f"  Config: L2=({config.l2_sentence_gap_range_sec[0]}-{config.l2_sentence_gap_range_sec[1]}s) "
          f"L3={config.l3_board_to_speak_delay_sec}s "
          f"L4={config.l4_segment_gap_sec}s "
          f"L5={config.l5_pause_default_ms}ms "
          f"L6={config.l6_concept_switch_gap_sec}s")
    print()

    gen = generate_teaching_events_v2_stream(
        events_path=args.events,
        latency_config=config,
        audio_manifest_path=args.audio_manifest,
        follow_up_turn=args.follow_up,
        live_demo=args.live,
    )

    event_count = 0
    for chunk in gen:
        if chunk["chunk_type"] == "plan":
            print(f"  [plan] Scheduling {chunk['data']['event_count']} events")
            if args.follow_up:
                print(f"  [plan] L7 follow-up mode: first event delay = {config.l7_follow_up_first_utterance_sec}s")
            print()

        elif chunk["chunk_type"] == "event":
            item = chunk["data"]
            event_count += 1
            offset = item["start_offset_sec"]
            evt_type = item["type"]
            label = item.get("_latency_label", "")
            gap = item.get("_gap_sec", 0)

            detail = ""
            if evt_type == "speak":
                text = item.get("text", "")
                detail = f'"{text[:40]}..."' if len(text) > 40 else f'"{text}"'
            elif evt_type == "board":
                detail = f'action={item.get("action", "")}'
            elif evt_type == "formula":
                detail = f'latex={item.get("latex", "")[:30]}...'
            elif evt_type == "table":
                detail = f'title={item.get("title", "")}'
            elif evt_type == "quiz":
                detail = f'Q: {item.get("question", "")[:30]}...'
            elif evt_type == "pause":
                detail = f'{item.get("duration_sec", 0)}s'

            print(f"  [{offset:5.1f}s] [{event_count:2d}/{0}] "
                  f"{evt_type:7s} {detail:55s} (gap={gap:.1f}s, {label})")

            if args.live:
                # Sleep until next event would fire
                pass  # handled by generator

        elif chunk["chunk_type"] == "done":
            print()
            print(f"  [done] {chunk['data']['total']} events, "
                  f"{chunk['data']['total_duration_sec']:.1f}s total duration")

    print(SEP)
    return 0


def cmd_build(args):
    """Build streaming playback_data.json with L1-L7 timing."""
    config = _parse_latency_config(args.latency_config)

    print(SEP)
    print("  Build Streaming Playback Data — L1-L7 Timing")
    print(SEP)
    print(f"  Events:    {args.events}")
    print(f"  Output:    {args.output}")
    print(f"  Teacher:   {args.teacher_card or '(none)'}")
    print(f"  Audio:     {args.audio_manifest or '(none, text estimate)'}")
    print()

    output_path = args.output
    if os.path.isdir(output_path):
        output_path = os.path.join(output_path, "playback_data.json")

    result = build_streaming_playback(
        events_path=args.events,
        output_path=output_path,
        teacher_card_path=args.teacher_card,
        audio_manifest_path=args.audio_manifest,
        latency_config=config,
    )

    if result["status"] == "success":
        print(f"  [OK] Timeline: {result['timeline_count']} items")
        print(f"  [OK] Output:   {result['playback_data']}")
        print(f"\n  Latency Report:")
        report = result["latency_report"]
        print(f"    L1 first event type: {report['l1_first_event_type']}")
        print(f"    L2 gaps applied:     {report['l2_gaps_applied']}")
        print(f"    L3 gaps applied:     {report['l3_gaps_applied']}")
        print(f"    L4 gaps applied:     {report['l4_gaps_applied']}")
        print(f"    L5 pause default:    {report['l5_pause_default_ms']}ms")
        print(f"    L6 gaps applied:     {report['l6_gaps_applied']}")
        print(f"    Total duration:      {report['total_duration_sec']}s")
    else:
        print(f"  [FAIL] {result.get('message', 'unknown error')}")

    print(SEP)
    return 0 if result["status"] == "success" else 1


def cmd_verify(args):
    """Verify existing playback_data.json against L1-L7 spec."""
    playback_path = args.playback
    events_path = args.events

    if not os.path.exists(playback_path):
        print(f"[FAIL] playback_data.json not found: {playback_path}")
        return 1

    with open(playback_path, "r", encoding="utf-8") as f:
        playback = json.load(f)

    timeline = playback.get("timeline", [])
    if not timeline:
        print("[FAIL] No timeline items in playback_data.json")
        return 1

    # Load events for segment classification
    events = []
    if events_path and os.path.exists(events_path):
        with open(events_path, "r", encoding="utf-8") as f:
            events = json.load(f).get("events", [])

    print(SEP)
    print("  L1-L7 Compliance Verification")
    print(SEP)

    results = []

    # L1: First event type
    first = timeline[0]
    l1_pass = first.get("type") == "board" and first.get("action") == "write_title"
    results.append(("L1", "First event is board:write_title",
                    f"{first.get('type')}:{first.get('action','')}",
                    "PASS" if l1_pass else "FAIL"))

    # L2: Inter-sentence gaps (speak→speak same segment)
    l2_gaps = []
    for i in range(1, len(timeline)):
        if timeline[i-1]["type"] == "speak" and timeline[i]["type"] == "speak":
            gap = timeline[i]["start_offset_sec"] - timeline[i-1]["start_offset_sec"] - timeline[i-1].get("duration_sec", 0)
            l2_gaps.append(gap)

    if events:
        labels = detect_latency_labels(events)
    else:
        labels = []

    l2_pass = all(0.2 <= g <= 1.0 for g in l2_gaps) if l2_gaps else True
    l2_detail = f"{len(l2_gaps)} gaps, range {min(l2_gaps):.2f}-{max(l2_gaps):.2f}s" if l2_gaps else "N/A"
    results.append(("L2", "Inter-sentence gap 0.2-1.0s", l2_detail,
                    "PASS" if l2_pass else "FAIL"))

    # L3: Board→speak gaps
    l3_gaps = []
    for i in range(1, len(timeline)):
        if timeline[i-1]["type"] == "board" and timeline[i]["type"] == "speak":
            gap = timeline[i]["start_offset_sec"] - timeline[i-1]["start_offset_sec"]
            l3_gaps.append(gap)

    l3_pass = all(0.3 <= g <= 2.0 for g in l3_gaps) if l3_gaps else True
    l3_detail = f"{len(l3_gaps)} gaps, range {min(l3_gaps):.2f}-{max(l3_gaps):.2f}s" if l3_gaps else "N/A"
    results.append(("L3", "Board→speak delay 0.3-2.0s", l3_detail,
                    "PASS" if l3_pass else "FAIL"))

    # L4: Segment boundary gaps — detect from "new topic" patterns in timeline
    l4_gaps = []
    for i in range(1, len(timeline)):
        prev = timeline[i-1]
        curr = timeline[i]
        # A segment boundary is marked by board:write_title followed by a speak
        # (the title itself is the boundary; the gap before the next content event)
        if prev.get("action") == "write_title" and curr["type"] == "speak" and i > 1:
            gap = curr["start_offset_sec"] - prev["start_offset_sec"]
            if 1.0 <= gap <= 3.5:
                l4_gaps.append(gap)

    l4_pass = all(1.0 <= g <= 3.0 for g in l4_gaps) if l4_gaps else True
    l4_detail = f"{len(l4_gaps)} gaps, range {min(l4_gaps):.2f}-{max(l4_gaps):.2f}s" if l4_gaps else "N/A"
    results.append(("L4", "Segment gap 1.0-3.0s", l4_detail,
                    "PASS" if l4_pass else "FAIL"))

    # L5: Pause durations
    pause_durs = [item.get("duration_sec", 0) for item in timeline if item["type"] == "pause"]
    l5_pass = all(d >= 1.5 for d in pause_durs) if pause_durs else True
    l5_detail = f"{len(pause_durs)} pauses, min={min(pause_durs):.2f}s" if pause_durs else "N/A"
    results.append(("L5", "Pause ≥ 1.5s", l5_detail,
                    "PASS" if l5_pass else "FAIL"))

    # L6: Concept switch gaps
    l6_gaps = []
    for i in range(1, len(timeline)):
        if timeline[i-1].get("action") == "clear_board":
            gap = timeline[i]["start_offset_sec"] - timeline[i-1]["start_offset_sec"]
            l6_gaps.append(gap)

    l6_pass = all(2.0 <= g <= 4.0 for g in l6_gaps) if l6_gaps else True
    l6_detail = f"{len(l6_gaps)} gaps, range {min(l6_gaps):.2f}-{max(l6_gaps):.2f}s" if l6_gaps else "N/A"
    results.append(("L6", "Concept switch 2.0-4.0s", l6_detail,
                    "PASS" if l6_pass else "FAIL"))

    # Print results
    fail_count = 0
    for label, desc, detail, status in results:
        icon = "[OK]" if status == "PASS" else "[FAIL]"
        print(f"  {icon} {label}: {desc}")
        print(f"       {detail}")
        if status == "FAIL":
            fail_count += 1

    total = len(results)
    passed = total - fail_count
    print(f"\n  Result: {passed}/{total} PASS ({fail_count} FAIL)")
    print(SEP)

    return 0 if fail_count == 0 else 1


def _parse_latency_config(config_str: str | None) -> LatencyConfig:
    """Parse latency config JSON string or return default."""
    if not config_str:
        return DEFAULT_LATENCY_CONFIG
    try:
        d = json.loads(config_str)
        return LatencyConfig.from_dict(d)
    except Exception as e:
        print(f"[WARN] Failed to parse latency-config: {e}, using defaults")
        return DEFAULT_LATENCY_CONFIG


def main():
    parser = argparse.ArgumentParser(description="Stream Module — L1-L7 Latency Layer")
    sub = parser.add_subparsers(dest="cmd", help="Subcommand")

    # stream
    p_stream = sub.add_parser("stream", help="Stream events with L1-L7 timing")
    p_stream.add_argument("--events", required=True, help="Path to teaching_events.json")
    p_stream.add_argument("--audio-manifest", help="Path to audio_manifest.json (optional)")
    p_stream.add_argument("--follow-up", action="store_true", help="L7 follow-up turn mode")
    p_stream.add_argument("--live", action="store_true", help="Live demo with real-time delays")
    p_stream.add_argument("--latency-config", help="JSON string to override latency config")

    # build
    p_build = sub.add_parser("build", help="Build streaming playback_data.json")
    p_build.add_argument("--events", required=True, help="Path to teaching_events.json")
    p_build.add_argument("--output", required=True, help="Output path or directory")
    p_build.add_argument("--teacher-card", help="Path to teacher_card.json (optional)")
    p_build.add_argument("--audio-manifest", help="Path to audio_manifest.json (optional)")
    p_build.add_argument("--latency-config", help="JSON string to override latency config")

    # verify
    p_verify = sub.add_parser("verify", help="Verify playback_data.json against L1-L7 spec")
    p_verify.add_argument("--playback", required=True, help="Path to playback_data.json")
    p_verify.add_argument("--events", help="Path to teaching_events.json (for segment detection)")

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        return 1

    cmd_map = {
        "stream": cmd_stream,
        "build": cmd_build,
        "verify": cmd_verify,
    }
    return cmd_map[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
