"""
Streaming event generator — implements M4 spec §3.2 pattern.
Yields events one-by-one with proper L1-L7 latency timing.

Can work standalone (estimate speak durations from text length)
or with an audio_manifest (use actual durations).
"""
from __future__ import annotations
import os
import json
import time
from typing import Iterator

from .latency_config import LatencyConfig, DEFAULT_LATENCY_CONFIG


# Chinese speech rate estimate: ~4 chars/sec
_CHARS_PER_SEC = 4.0


def _load_events(events_path: str | list[dict]) -> list[dict]:
    """Load events from path or return the list as-is."""
    if isinstance(events_path, list):
        return events_path
    with open(events_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("events", [])


def _load_audio_manifest(audio_manifest_path: str | None) -> dict[str, dict]:
    """Load audio manifest and index by event_id. Returns empty dict if None."""
    if not audio_manifest_path or not os.path.exists(audio_manifest_path):
        return {}
    with open(audio_manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("items", [])
    return {item["event_id"]: item for item in items}


def _estimate_speak_duration(text: str) -> float:
    """Estimate speak duration from text length if no audio manifest.
    Chinese: ~4 chars/sec speaking rate.
    """
    return max(1.0, len(text) / _CHARS_PER_SEC)


def _get_event_duration(evt: dict, audio_items: dict) -> float:
    """Get duration for offset advancement after an event."""
    evt_type = evt.get("type")
    if evt_type == "speak":
        audio = audio_items.get(evt.get("event_id", ""), {})
        return audio.get("duration_sec", _estimate_speak_duration(evt.get("text", "")))
    elif evt_type == "board":
        return 0.0  # dwell is handled by next event's gap
    elif evt_type == "formula":
        return 0.0
    elif evt_type == "table":
        return 0.0
    elif evt_type == "pause":
        return evt.get("duration_sec", 1.0)
    elif evt_type == "quiz":
        return 0.0  # blocking, dwell handled by gap
    return 0.0


def classify_segments(events: list[dict]) -> list[int]:
    """Assign segment_id to each event.

    Segment increments on:
    - board:clear_board          (concept switch)
    - board:write_title          (new topic starts)
    - board:write_subtitle       (sub-topic starts)

    Returns list of segment_ids parallel to events list.
    """
    segment_ids = []
    current_seg = 0
    boundary_actions = {"clear_board", "write_title", "write_subtitle"}

    for evt in events:
        if evt.get("type") == "board" and evt.get("action") in boundary_actions:
            current_seg += 1
        segment_ids.append(current_seg)

    # Normalize: if no boundaries were found, every event is segment 0
    return segment_ids


def detect_latency_labels(
    events: list[dict],
    config: LatencyConfig | None = None,
) -> list[str]:
    """Classify each gap between consecutive events as an L-label.

    Returns list of labels (length = len(events)-1).
    Useful for testing and verification.
    """
    if config is None:
        config = DEFAULT_LATENCY_CONFIG
    segment_ids = classify_segments(events)

    labels = []
    for i in range(1, len(events)):
        prev = events[i - 1]
        curr = events[i]
        gap = config.get_gap_for_transition(
            prev_type=prev.get("type"),
            prev_action=prev.get("action"),
            next_type=curr.get("type"),
            next_action=curr.get("action"),
            prev_segment_id=segment_ids[i - 1],
            next_segment_id=segment_ids[i],
        )

        seg_changed = segment_ids[i - 1] != segment_ids[i]
        prev_action = prev.get("action")

        if prev.get("type") == "pause":
            labels.append("L5")
        elif seg_changed and prev_action == "clear_board":
            labels.append("L6")
        elif seg_changed:
            labels.append("L4")
        elif prev.get("type") in ("board", "formula", "table") and curr.get("type") == "speak":
            labels.append("L3")
        elif prev.get("type") == "speak" and curr.get("type") == "speak":
            labels.append("L2")
        else:
            labels.append("other")

    return labels


def generate_teaching_events_v2_stream(
    events_path: str | list[dict],
    latency_config: LatencyConfig | None = None,
    audio_manifest_path: str | None = None,
    follow_up_turn: bool = False,
    live_demo: bool = False,
) -> Iterator[dict]:
    """Stream teaching events one-by-one with L1-L7 latency timing.

    Implements M4 spec §3.2 pattern. Yields StreamChunk dicts:

        {"chunk_type": "plan",   "data": {...}}
        {"chunk_type": "event",  "data": {timeline_item}}
        {"chunk_type": "done",   "data": {"total": N}}
        {"chunk_type": "error",  "data": {"message": "..."}}

    Args:
        events_path: Path to teaching_events.json OR list of event dicts
        latency_config: L1-L7 latency parameters (default: DEFAULT_LATENCY_CONFIG)
        audio_manifest_path: Optional path to audio_manifest.json for real durations
        follow_up_turn: If True, applies L7 follow-up delay to first event
        live_demo: If True, adds real-time sleep between events for demo purposes

    Yields:
        StreamChunk dicts
    """
    if latency_config is None:
        latency_config = DEFAULT_LATENCY_CONFIG

    try:
        events = _load_events(events_path)
        audio_items = _load_audio_manifest(audio_manifest_path)
    except Exception as e:
        yield {"chunk_type": "error", "data": {"message": str(e)}}
        return

    if not events:
        yield {"chunk_type": "error", "data": {"message": "No events found"}}
        return

    # Sort by seq
    events_sorted = sorted(events, key=lambda e: e.get("seq", 0))

    # L1: Force first event to board:write_title if configured
    if (latency_config.l1_force_first_event
            and latency_config.l1_first_event_type.startswith("board:")):
        first = events_sorted[0]
        if first.get("type") != "board" or first.get("action") != "write_title":
            # Prepend a board:write_title event
            action = latency_config.l1_first_event_type.split(":", 1)[1]
            prepend = {
                "event_id": "evt_0000",
                "type": "board",
                "seq": 0,
                "action": action,
                "content": "",
            }
            events_sorted.insert(0, prepend)
            # Re-number seq
            for i, evt in enumerate(events_sorted):
                evt["seq"] = i + 1

    # Classify segments
    segment_ids = classify_segments(events_sorted)

    # Yield plan chunk
    plan_data = {
        "event_count": len(events_sorted),
        "total_estimated_sec": 0,
        "follow_up_turn": follow_up_turn,
    }
    yield {"chunk_type": "plan", "data": plan_data}

    # Build and yield events
    current_offset = 0.0
    total_duration = 0.0

    for i, evt in enumerate(events_sorted):
        # Compute gap from previous event
        if i == 0:
            gap = 0.0
            label = "L1"
        else:
            prev = events_sorted[i - 1]
            gap = latency_config.get_gap_for_transition(
                prev_type=prev.get("type"),
                prev_action=prev.get("action"),
                next_type=evt.get("type"),
                next_action=evt.get("action"),
                prev_segment_id=segment_ids[i - 1],
                next_segment_id=segment_ids[i],
            )

            if prev.get("type") == "pause":
                label = "L5"
            elif segment_ids[i - 1] != segment_ids[i] and prev.get("action") == "clear_board":
                label = "L6"
            elif segment_ids[i - 1] != segment_ids[i]:
                label = "L4"
            elif prev.get("type") in ("board", "formula", "table") and evt.get("type") == "speak":
                label = "L3"
            elif prev.get("type") == "speak" and evt.get("type") == "speak":
                label = "L2"
            else:
                label = "other"

        # Apply L7 for follow-up turn
        if i == 0 and follow_up_turn:
            gap = latency_config.l7_follow_up_first_utterance_sec
            label = "L7"

        current_offset += gap

        # Build timeline item
        evt_type = evt.get("type")
        item = {
            "seq": evt.get("seq", i + 1),
            "type": evt_type,
            "event_id": evt.get("event_id", f"evt_{i:04d}"),
            "start_offset_sec": round(current_offset, 3),
            "_latency_label": label,
            "_gap_sec": gap,
        }

        if evt_type == "speak":
            dur = _get_event_duration(evt, audio_items)
            item["text"] = evt.get("text", "")
            item["duration_sec"] = dur
            item["audio_path"] = audio_items.get(
                evt.get("event_id", ""), {}
            ).get("audio_path", "")
            current_offset += dur
            total_duration += gap + dur

        elif evt_type == "board":
            item["action"] = evt.get("action", "")
            item["content"] = evt.get("content", "")
            item["dwell_sec"] = latency_config.l3_board_to_speak_delay_sec
            total_duration += gap

        elif evt_type == "formula":
            item["latex"] = evt.get("latex", "")
            item["display_mode"] = evt.get("display_mode", "block")
            item["dwell_sec"] = 0.8
            total_duration += gap

        elif evt_type == "table":
            item["title"] = evt.get("title", "")
            item["columns"] = evt.get("columns", [])
            item["rows"] = evt.get("rows", [])
            item["dwell_sec"] = 1.0
            total_duration += gap

        elif evt_type == "pause":
            dur = evt.get("duration_sec", 1.0)
            dur = latency_config.enforce_pause_minimum(dur)
            item["duration_sec"] = dur
            current_offset += dur
            total_duration += gap + dur

        elif evt_type == "quiz":
            item["question"] = evt.get("question", "")
            item["options"] = evt.get("options", [])
            item["blocking"] = True
            total_duration += gap

        if live_demo and gap > 0:
            time.sleep(gap)

        yield {"chunk_type": "event", "data": item}

    # Yield done chunk
    yield {
        "chunk_type": "done",
        "data": {
            "total": len(events_sorted),
            "total_duration_sec": round(total_duration, 2),
        },
    }
