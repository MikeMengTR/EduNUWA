"""
Streaming-aware playback builder.

Similar to M5_runtime/build_playback/builder.py but:
- Computes start_offset_sec from L1-L7 latency rules instead of fixed dwells
- Audio manifest is optional (estimates duration from text when absent)
- Returns a latency report alongside playback_data
"""
from __future__ import annotations
import os
import json
from datetime import datetime, timezone

from .latency_config import LatencyConfig, DEFAULT_LATENCY_CONFIG
from .streaming_orchestrator import generate_teaching_events_v2_stream


def _atomic_write_json(data: dict, target_path: str):
    """Atomic JSON write (H10 pattern)."""
    os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)
    tmp_path = target_path + ".tmp." + str(os.getpid())
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, target_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _load_json(path: str, label: str) -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(f"{label} not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_streaming_playback(
    events_path: str,
    output_path: str,
    teacher_card_path: str | None = None,
    audio_manifest_path: str | None = None,
    latency_config: LatencyConfig | None = None,
    config: dict | None = None,
) -> dict:
    """Build playback_data.json with L1-L7 latency-aware timing.

    Args:
        events_path: Path to teaching_events.json
        output_path: Full output path for playback_data.json
        teacher_card_path: Optional path to teacher_card.json (from M6)
        audio_manifest_path: Optional path to audio_manifest.json
        latency_config: L1-L7 latency configuration
        config: Optional dict with extra params (playback.speak_pause, etc.)

    Returns:
        dict with status, playback_data path, timeline_count, latency_report
    """
    if latency_config is None:
        latency_config = DEFAULT_LATENCY_CONFIG

    # Load teacher card for metadata
    teacher_card = {}
    if teacher_card_path and os.path.exists(teacher_card_path):
        try:
            teacher_card = _load_json(teacher_card_path, "teacher_card.json")
        except Exception:
            pass

    # Load events data for session/turn info
    events_data = {}
    try:
        with open(events_path, "r", encoding="utf-8") as f:
            events_data = json.load(f)
    except Exception:
        pass

    session_id = events_data.get("session_id", "unknown")
    turn = events_data.get("turn", 1)
    teacher_id = teacher_card.get("teacher_id", "unknown")
    skill_id = teacher_card.get("current_skill_version", None)
    if skill_id and teacher_id:
        compact = teacher_id.replace("_", "")
        skill_id = f"S_{compact}_v{skill_id}"
    voice_id = teacher_card.get("voice_id", "")

    # Consume all chunks from the stream generator
    timeline = []
    total_duration = 0.0
    latency_report = {
        "l1_first_event_type": "",
        "l2_gaps_applied": 0,
        "l3_gaps_applied": 0,
        "l4_gaps_applied": 0,
        "l5_pause_default_ms": latency_config.l5_pause_default_ms,
        "l6_gaps_applied": 0,
        "l7_applied": False,
        "total_duration_sec": 0.0,
    }

    for chunk in generate_teaching_events_v2_stream(
        events_path=events_path,
        latency_config=latency_config,
        audio_manifest_path=audio_manifest_path,
        follow_up_turn=False,
    ):
        if chunk["chunk_type"] == "event":
            item = chunk["data"]
            label = item.pop("_latency_label", "")
            _gap = item.pop("_gap_sec", 0)  # noqa: F841

            if label == "L1":
                latency_report["l1_first_event_type"] = f"{item.get('type')}:{item.get('action','')}"
            elif label == "L2":
                latency_report["l2_gaps_applied"] += 1
            elif label == "L3":
                latency_report["l3_gaps_applied"] += 1
            elif label == "L4":
                latency_report["l4_gaps_applied"] += 1
            elif label == "L6":
                latency_report["l6_gaps_applied"] += 1
            elif label == "L7":
                latency_report["l7_applied"] = True

            timeline.append(item)
            # track duration for non-blocking events
            if item.get("type") == "speak":
                total_duration = item["start_offset_sec"] + item["duration_sec"]
            elif item.get("type") == "pause":
                total_duration = item["start_offset_sec"] + item["duration_sec"]
            else:
                total_duration = item["start_offset_sec"]

        elif chunk["chunk_type"] == "done":
            total_duration = chunk["data"].get("total_duration_sec", total_duration)

    # Build payload
    payload = {
        "session_id": session_id,
        "turn": turn,
        "teacher_id": teacher_id,
        "skill_id": skill_id,
        "avatar": teacher_card.get("avatar", {}),
        "voice_id": voice_id,
        "timeline": timeline,
        "total_duration_sec": round(total_duration, 2),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Write output
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    _atomic_write_json(payload, output_path)

    latency_report["total_duration_sec"] = round(total_duration, 2)

    return {
        "status": "success",
        "playback_data": output_path,
        "timeline_count": len(timeline),
        "latency_report": latency_report,
    }
