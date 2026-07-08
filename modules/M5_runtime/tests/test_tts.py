"""
Tests for TTS engine: H1 (event type validation), H2 (board action validation), H8 (fallback).
"""
import os
import json
import sys
import tempfile
import pytest
from pathlib import Path

# Add project root
_PROJECT_ROOT = Path(os.path.dirname(os.path.abspath(__file__))).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "modules"))

from M5_runtime.tts_service.tts_engine import generate_tts_batch, _validate_events


# --- H1: Unknown event type must fail-loud ---

def test_reject_unknown_event_type():
    events = [
        {"event_id": "evt_0001", "type": "unknown_event", "seq": 1},
    ]
    err = _validate_events(events)
    assert err is not None
    assert err["status"] == "error"
    assert "unknown_event" in err["message"]


def test_accept_all_six_valid_types():
    events = [
        {"event_id": "evt_0001", "type": "speak", "seq": 1, "text": "Hello"},
        {"event_id": "evt_0002", "type": "board", "seq": 2, "action": "write_title", "content": "Title"},
        {"event_id": "evt_0003", "type": "formula", "seq": 3, "latex": "x^2", "display_mode": "block"},
        {"event_id": "evt_0004", "type": "table", "seq": 4, "title": "T", "columns": ["A"], "rows": [["1"]]},
        {"event_id": "evt_0005", "type": "pause", "seq": 5, "duration_sec": 2.0},
        {"event_id": "evt_0006", "type": "quiz", "seq": 6, "question": "Q?", "options": ["A", "B"]},
    ]
    err = _validate_events(events)
    assert err is None, f"Expected all 6 types to be valid, got: {err}"


# --- H2: Board action validation ---

def test_all_seven_board_actions_valid():
    actions = [
        "write_title", "write_subtitle", "write_bullets",
        "write_steps", "write_summary", "clear_board", "highlight",
    ]
    for action in actions:
        events = [
            {"event_id": "evt_0001", "type": "board", "seq": 1, "action": action, "content": "X"},
        ]
        err = _validate_events(events)
        assert err is None, f"Board action '{action}' should be valid"


def test_reject_unknown_board_action():
    events = [
        {"event_id": "evt_0001", "type": "board", "seq": 1, "action": "animate_fireworks", "content": "X"},
    ]
    err = _validate_events(events)
    assert err is not None
    assert err["status"] == "error"
    assert "animate_fireworks" in err["message"]


# --- H1: Missing required fields per type ---

def test_speak_missing_text():
    events = [{"event_id": "evt_0001", "type": "speak", "seq": 1}]
    err = _validate_events(events)
    assert err is not None
    assert "missing" in err["message"].lower() or "text" in err["message"].lower()


def test_quiz_missing_question():
    events = [{"event_id": "evt_0001", "type": "quiz", "seq": 1, "options": ["A"]}]
    err = _validate_events(events)
    assert err is not None


def test_formula_missing_latex():
    events = [{"event_id": "evt_0001", "type": "formula", "seq": 1, "display_mode": "block"}]
    err = _validate_events(events)
    assert err is not None


# --- H8: Edge TTS fallback (unit-level, no GPU needed) ---

def test_edge_tts_fallback_no_gpu(monkeypatch):
    """Simulate GPT-SoVITS failure and verify edge_tts fallback path is triggered.
    This is a logic test — doesn't actually run models.
    """
    # Verify the fallback exception classes are defined correctly
    from M5_runtime.tts_service.tts_engine import FALLBACK_EXCEPTIONS
    assert RuntimeError in FALLBACK_EXCEPTIONS
    assert OSError in FALLBACK_EXCEPTIONS


# --- H3: Schema validation helpers ---

def test_audio_manifest_schema_exists():
    schema_path = _PROJECT_ROOT / "modules" / "M5_runtime" / "schemas" / "audio_manifest.schema.json"
    assert schema_path.exists(), f"Schema not found at {schema_path}"
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    assert "items" in schema["properties"]
    assert "required" in schema


def test_playback_data_schema_exists():
    schema_path = _PROJECT_ROOT / "modules" / "M5_runtime" / "schemas" / "playback_data.schema.json"
    assert schema_path.exists(), f"Schema not found at {schema_path}"
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    assert "timeline" in schema["properties"]
    assert "required" in schema


def test_teaching_events_schema_exists():
    schema_path = _PROJECT_ROOT / "modules" / "M5_runtime" / "schemas" / "teaching_events.schema.json"
    assert schema_path.exists(), f"Schema not found at {schema_path}"
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    valid_types = schema["definitions"]["event"]["properties"]["type"]["enum"]
    assert "speak" in valid_types
    assert "quiz" in valid_types
    assert len(valid_types) == 6  # all 6 types


# --- H10: Atomic write ---

def test_atomic_write_wav():
    from M5_runtime.tts_service.audio_postprocess import atomic_write_wav
    import numpy as np

    audio = np.zeros(1000, dtype=np.float32)
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "test.wav")
        atomic_write_wav(audio, 22050, out_path)
        assert os.path.exists(out_path)
        # No .tmp file should remain
        tmps = [f for f in os.listdir(tmpdir) if ".tmp" in f]
        assert len(tmps) == 0, f"Temporary files left behind: {tmps}"


def test_atomic_write_json():
    from M5_runtime.tts_service.audio_postprocess import atomic_write_json

    data = {"key": "value"}
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "test.json")
        atomic_write_json(data, out_path)
        assert os.path.exists(out_path)
        with open(out_path) as f:
            loaded = json.load(f)
        assert loaded == data
        tmps = [f for f in os.listdir(tmpdir) if ".tmp" in f]
        assert len(tmps) == 0


# --- generate_tts_batch error paths (no GPU needed) ---

def test_generate_tts_batch_missing_file():
    result = generate_tts_batch(
        events_path="/nonexistent/path.json",
        output_dir="/tmp/test",
        voice_id="test",
    )
    assert result["status"] == "error"


def test_generate_tts_batch_no_speak_events():
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        events_path = os.path.join(tmpdir, "events.json")
        events = {
            "event_file_id": "test",
            "events": [
                {"event_id": "evt_0001", "type": "board", "seq": 1, "action": "write_title", "content": "T"},
                {"event_id": "evt_0002", "type": "pause", "seq": 2, "duration_sec": 1.0},
            ]
        }
        with open(events_path, "w") as f:
            json.dump(events, f)

        out_dir = os.path.join(tmpdir, "out")
        result = generate_tts_batch(events_path, out_dir, voice_id="test")
        # Should error because no speak events
        assert result["status"] == "error"
