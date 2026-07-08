"""
Tests for playback data builder: H3 (schema), timeline calculation, quiz blocking.
"""
import os
import json
import sys
import tempfile
import pytest
from pathlib import Path

_PROJECT_ROOT = Path(os.path.dirname(os.path.abspath(__file__))).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "modules"))

from M5_runtime.build_playback.builder import build_playback_data


def _make_test_files(tmpdir, events_list, audio_items, teacher_card=None):
    """Create temporary test input files and return their paths."""
    # Events
    events_path = os.path.join(tmpdir, "events.json")
    events_data = {
        "event_file_id": "test_events",
        "session_id": "SES_test",
        "turn": 1,
        "events": events_list,
    }
    with open(events_path, "w") as f:
        json.dump(events_data, f)

    # Audio manifest
    manifest_path = os.path.join(tmpdir, "audio_manifest.json")
    manifest_data = {
        "event_file_id": "test_events",
        "session_id": "SES_test",
        "turn": 1,
        "tts_engine": "gpt_sovits",
        "voice_id": "test_voice",
        "items": audio_items,
    }
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f)

    # Teacher card
    if teacher_card is None:
        teacher_card = {
            "teacher_id": "T_20260515_001",
            "voice_id": "test_voice",
            "avatar": {"pixel_url": "/img/pixel.png", "live2d_model_id": "model_001"},
            "current_skill_version": 2,
        }
    card_path = os.path.join(tmpdir, "teacher_card.json")
    with open(card_path, "w") as f:
        json.dump(teacher_card, f)

    return events_path, manifest_path, card_path


def test_build_playback_basic():
    """Build playback_data with speak + board events."""
    with tempfile.TemporaryDirectory() as tmpdir:
        events = [
            {"event_id": "evt_0001", "type": "speak", "seq": 1, "text": "Hello"},
            {"event_id": "evt_0002", "type": "board", "seq": 2, "action": "write_title", "content": "Title"},
            {"event_id": "evt_0003", "type": "speak", "seq": 3, "text": "World"},
        ]
        audio = [
            {"event_id": "evt_0001", "seq": 1, "text": "Hello", "audio_path": "/audio/evt_0001.wav", "duration_sec": 2.0, "sample_rate": 22050},
            {"event_id": "evt_0003", "seq": 3, "text": "World", "audio_path": "/audio/evt_0003.wav", "duration_sec": 1.5, "sample_rate": 22050},
        ]
        events_p, manifest_p, card_p = _make_test_files(tmpdir, events, audio)
        out_dir = os.path.join(tmpdir, "out")

        result = build_playback_data(events_p, manifest_p, out_dir, card_p)

        assert result["status"] == "success"
        assert result["timeline_count"] == 3

        out_path = os.path.join(out_dir, "playback_data.json")
        assert os.path.exists(out_path)

        with open(out_path) as f:
            pb = json.load(f)

        assert pb["session_id"] == "SES_test"
        assert pb["turn"] == 1
        assert len(pb["timeline"]) == 3

        # Check timeline ordering and offsets
        timeline = pb["timeline"]
        assert timeline[0]["start_offset_sec"] == 0.0  # first speak starts at 0
        assert timeline[0]["duration_sec"] == 2.0
        assert timeline[1]["start_offset_sec"] == pytest.approx(2.0 + 0.3, abs=0.01)  # speak duration + pause
        assert timeline[1]["type"] == "board"


def test_timeline_offset_calculation():
    """Verify start_offset_sec accumulates correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        events = [
            {"event_id": "evt_0001", "type": "speak", "seq": 1, "text": "A"},
            {"event_id": "evt_0002", "type": "speak", "seq": 2, "text": "B"},
            {"event_id": "evt_0003", "type": "speak", "seq": 3, "text": "C"},
        ]
        audio = [
            {"event_id": "evt_0001", "seq": 1, "text": "A", "audio_path": "a.wav", "duration_sec": 3.0, "sample_rate": 22050},
            {"event_id": "evt_0002", "seq": 2, "text": "B", "audio_path": "b.wav", "duration_sec": 2.0, "sample_rate": 22050},
            {"event_id": "evt_0003", "seq": 3, "text": "C", "audio_path": "c.wav", "duration_sec": 4.0, "sample_rate": 22050},
        ]
        events_p, manifest_p, card_p = _make_test_files(tmpdir, events, audio)
        out_dir = os.path.join(tmpdir, "out")

        result = build_playback_data(events_p, manifest_p, out_dir, card_p)
        assert result["status"] == "success"

        out_path = os.path.join(out_dir, "playback_data.json")
        with open(out_path) as f:
            pb = json.load(f)

        t = pb["timeline"]
        gap = 0.3  # speak_pause_after_sec
        assert t[0]["start_offset_sec"] == 0.0
        assert t[1]["start_offset_sec"] == pytest.approx(3.0 + gap, abs=0.01)
        assert t[2]["start_offset_sec"] == pytest.approx(3.0 + gap + 2.0 + gap, abs=0.01)


def test_quiz_marked_blocking():
    """Quiz events must have blocking: true."""
    with tempfile.TemporaryDirectory() as tmpdir:
        events = [
            {"event_id": "evt_0001", "type": "speak", "seq": 1, "text": "Question time"},
            {"event_id": "evt_0002", "type": "quiz", "seq": 2, "question": "What?", "options": ["A", "B"]},
        ]
        audio = [
            {"event_id": "evt_0001", "seq": 1, "text": "Question time", "audio_path": "q.wav", "duration_sec": 2.0, "sample_rate": 22050},
        ]
        events_p, manifest_p, card_p = _make_test_files(tmpdir, events, audio)
        out_dir = os.path.join(tmpdir, "out")

        result = build_playback_data(events_p, manifest_p, out_dir, card_p)
        assert result["status"] == "success"

        out_path = os.path.join(out_dir, "playback_data.json")
        with open(out_path) as f:
            pb = json.load(f)

        quiz_item = pb["timeline"][1]
        assert quiz_item["type"] == "quiz"
        assert quiz_item["blocking"] is True


def test_board_dwell_time():
    """Board events should have dwell_sec set."""
    with tempfile.TemporaryDirectory() as tmpdir:
        events = [
            {"event_id": "evt_0001", "type": "speak", "seq": 1, "text": "Look"},
            {"event_id": "evt_0002", "type": "board", "seq": 2, "action": "write_bullets", "content": ["A", "B"]},
        ]
        audio = [
            {"event_id": "evt_0001", "seq": 1, "text": "Look", "audio_path": "l.wav", "duration_sec": 1.0, "sample_rate": 22050},
        ]
        events_p, manifest_p, card_p = _make_test_files(tmpdir, events, audio)
        out_dir = os.path.join(tmpdir, "out")

        result = build_playback_data(events_p, manifest_p, out_dir, card_p)
        assert result["status"] == "success"

        out_path = os.path.join(out_dir, "playback_data.json")
        with open(out_path) as f:
            pb = json.load(f)

        board_item = pb["timeline"][1]
        assert board_item["type"] == "board"
        assert "dwell_sec" in board_item
        assert board_item["dwell_sec"] > 0


def test_builder_missing_file():
    """Missing input file should return error."""
    result = build_playback_data(
        events_path="/nonexistent.json",
        audio_manifest_path="/also_nonexistent.json",
        output_dir="/tmp",
        teacher_card_path="/nope.json",
    )
    assert result["status"] == "error"


def test_all_six_event_types_in_timeline():
    """All 6 event types should appear correctly in timeline."""
    with tempfile.TemporaryDirectory() as tmpdir:
        events = [
            {"event_id": "evt_0001", "type": "speak", "seq": 1, "text": "Intro"},
            {"event_id": "evt_0002", "type": "board", "seq": 2, "action": "write_title", "content": "T"},
            {"event_id": "evt_0003", "type": "formula", "seq": 3, "latex": "x^2", "display_mode": "block"},
            {"event_id": "evt_0004", "type": "table", "seq": 4, "title": "Data", "columns": ["X"], "rows": [["1"]]},
            {"event_id": "evt_0005", "type": "pause", "seq": 5, "duration_sec": 2.0},
            {"event_id": "evt_0006", "type": "quiz", "seq": 6, "question": "Q?", "options": ["A", "B"]},
        ]
        audio = [
            {"event_id": "evt_0001", "seq": 1, "text": "Intro", "audio_path": "i.wav", "duration_sec": 1.0, "sample_rate": 22050},
        ]
        events_p, manifest_p, card_p = _make_test_files(tmpdir, events, audio)
        out_dir = os.path.join(tmpdir, "out")

        result = build_playback_data(events_p, manifest_p, out_dir, card_p)
        assert result["status"] == "success"

        out_path = os.path.join(out_dir, "playback_data.json")
        with open(out_path) as f:
            pb = json.load(f)

        types_in_timeline = {item["type"] for item in pb["timeline"]}
        expected = {"speak", "board", "formula", "table", "pause", "quiz"}
        assert types_in_timeline == expected
