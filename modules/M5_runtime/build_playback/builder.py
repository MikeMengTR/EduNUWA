"""
Playback data builder — merges teaching_events.json + audio_manifest.json + teacher_card.json
into playback_data.json for frontend PlayerRuntime consumption.
"""
from __future__ import annotations
import os
import json
from pathlib import Path
from datetime import datetime, timezone

from ..tts_service.audio_postprocess import atomic_write_json

# Module root
_MODULE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
_SCHEMA_DIR = _MODULE_DIR.parent / "schemas"

# Default dwell times per event type
DEFAULT_DWELL = {
    "board": 1.5,
    "formula": 1.5,
    "table": 2.0,
    "pause": 0,  # from event
}
DEFAULT_SPEAK_PAUSE = 0.3  # inter-sentence gap


def _load_json(path: str, label: str) -> dict:
    """Load and parse a JSON file with error context."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"{label} not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_playback_data(
    events_path: str,
    audio_manifest_path: str,
    output_dir: str,
    teacher_card_path: str,
    config: dict | None = None,
) -> dict:
    """Merge events + audio manifest + teacher card into playback_data.json.

    Args:
        events_path: Path to teaching_events.json
        audio_manifest_path: Path to audio_manifest.json (from generate_tts_batch)
        output_dir: Directory for output playback_data.json
        teacher_card_path: Path to teacher_card.json (from M6)
        config: Optional playback config (see M5 §3.3)

    Returns:
        dict with status, playback_data path, timeline_count
    """
    # Parse config
    speak_pause = DEFAULT_SPEAK_PAUSE
    board_dwell = DEFAULT_DWELL["board"]
    if config:
        pb = config.get("playback", {})
        speak_pause = pb.get("speak_pause_after_sec", speak_pause)
        board_dwell = pb.get("board_dwell_sec", board_dwell)

    # 1. Load all inputs
    try:
        events_data = _load_json(events_path, "teaching_events.json")
        audio_manifest = _load_json(audio_manifest_path, "audio_manifest.json")
        teacher_card = _load_json(teacher_card_path, "teacher_card.json")
    except FileNotFoundError as e:
        return {"status": "error", "message": str(e)}
    except json.JSONDecodeError as e:
        return {"status": "error", "message": f"JSON parse error: {e}"}

    events = events_data.get("events", [])
    audio_items = {item["event_id"]: item for item in audio_manifest.get("items", [])}

    if not events:
        return {"status": "error", "message": "No events found in teaching_events.json"}

    # 2. Extract session/turn metadata
    session_id = events_data.get("session_id", audio_manifest.get("session_id", "unknown"))
    turn = events_data.get("turn", audio_manifest.get("turn", 1))
    teacher_id = teacher_card.get("teacher_id", "unknown")
    skill_id = teacher_card.get("current_skill_version", None)
    if skill_id and teacher_id:
        compact = teacher_id.replace("_", "")
        skill_id = f"S_{compact}_v{skill_id}"
    voice_id = teacher_card.get("voice_id", audio_manifest.get("voice_id", ""))

    # 3. Build timeline
    timeline = []
    current_offset = 0.0

    for evt in sorted(events, key=lambda e: e.get("seq", 0)):
        evt_type = evt.get("type", "speak")
        evt_id = evt.get("event_id", "")
        seq = evt.get("seq", len(timeline) + 1)

        timeline_item = {
            "seq": seq,
            "type": evt_type,
            "event_id": evt_id,
            "start_offset_sec": round(current_offset, 3),
        }

        if evt_type == "speak":
            audio_info = audio_items.get(evt_id, {})
            duration = audio_info.get("duration_sec", 1.0)
            timeline_item.update({
                "text": evt.get("text", ""),
                "audio_path": audio_info.get("audio_path", ""),
                "duration_sec": duration,
            })
            current_offset += duration + speak_pause

        elif evt_type == "board":
            timeline_item.update({
                "action": evt.get("action", ""),
                "content": evt.get("content", ""),
                "dwell_sec": board_dwell,
            })
            current_offset += board_dwell

        elif evt_type == "formula":
            timeline_item.update({
                "latex": evt.get("latex", ""),
                "display_mode": evt.get("display_mode", "block"),
                "dwell_sec": DEFAULT_DWELL["formula"],
            })
            current_offset += DEFAULT_DWELL["formula"]

        elif evt_type == "table":
            timeline_item.update({
                "title": evt.get("title", ""),
                "columns": evt.get("columns", []),
                "rows": evt.get("rows", []),
                "dwell_sec": DEFAULT_DWELL["table"],
            })
            current_offset += DEFAULT_DWELL["table"]

        elif evt_type == "pause":
            pause_dur = evt.get("duration_sec", 1.0)
            timeline_item["duration_sec"] = pause_dur
            current_offset += pause_dur

        elif evt_type == "quiz":
            timeline_item.update({
                "question": evt.get("question", ""),
                "options": evt.get("options", []),
                "blocking": True,
            })
            # Quiz is blocking — we add nominal dwell + wait for student answer
            current_offset += board_dwell

        timeline.append(timeline_item)

    # 4. Build playback_data
    playback_data = {
        "session_id": session_id,
        "turn": turn,
        "teacher_id": teacher_id,
        "skill_id": skill_id,
        "avatar": teacher_card.get("avatar", {}),
        "voice_id": voice_id,
        "timeline": timeline,
        "total_duration_sec": round(current_offset, 2),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # 5. Write atomically
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "playback_data.json")
    atomic_write_json(playback_data, output_path)

    return {
        "status": "success",
        "playback_data": output_path,
        "timeline_count": len(timeline),
    }
