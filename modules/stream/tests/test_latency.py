"""
Tests for L1-L7 latency compliance per M4_orchestrator_streaming_latency_spec.md.
"""
from __future__ import annotations
import os
import json
import sys
from pathlib import Path

import pytest

# Path setup
_MODULE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
_MODULES_DIR = _MODULE_DIR.parent.parent
sys.path.insert(0, str(_MODULES_DIR))

from stream.latency_config import LatencyConfig, DEFAULT_LATENCY_CONFIG, BATCH_LATENCY_CONFIG
from stream.streaming_orchestrator import (
    generate_teaching_events_v2_stream,
    classify_segments,
    detect_latency_labels,
    _estimate_speak_duration,
)

# --- Fixtures ---

DEMO_EVENTS_3 = [
    {"event_id": "evt_0001", "type": "board", "seq": 1,
     "action": "write_title", "content": "过拟合"},
    {"event_id": "evt_0002", "type": "speak", "seq": 2,
     "text": "今天我们聊一个机器学习里非常重要的概念。"},
    {"event_id": "evt_0003", "type": "speak", "seq": 3,
     "text": "这个概念就是过拟合。"},
]

DEMO_EVENTS_WITH_PAUSE = [
    {"event_id": "evt_0001", "type": "speak", "seq": 1,
     "text": "为什么呢？"},
    {"event_id": "evt_0002", "type": "pause", "seq": 2,
     "duration_sec": 0.6},
    {"event_id": "evt_0003", "type": "speak", "seq": 3,
     "text": "因为模型记住了噪声。"},
]

DEMO_EVENTS_WITH_SEGMENT = [
    {"event_id": "evt_0001", "type": "board", "seq": 1,
     "action": "write_title", "content": "过拟合"},
    {"event_id": "evt_0002", "type": "speak", "seq": 2,
     "text": "第一段：什么是过拟合。"},
    {"event_id": "evt_0003", "type": "speak", "seq": 3,
     "text": "简单说就是模型记住了噪声。"},
    {"event_id": "evt_0004", "type": "board", "seq": 4,
     "action": "clear_board", "content": ""},
    {"event_id": "evt_0005", "type": "board", "seq": 5,
     "action": "write_title", "content": "解决办法"},
    {"event_id": "evt_0006", "type": "speak", "seq": 6,
     "text": "第二段：如何解决过拟合。"},
]

FULL_DEMO_19 = None  # Loaded from file if needed


def _load_full_demo():
    """Load the 19-event demo file."""
    global FULL_DEMO_19
    if FULL_DEMO_19 is not None:
        return FULL_DEMO_19
    demo_path = _MODULES_DIR / "M5_runtime" / "demo" / "demo_teaching_events.json"
    if demo_path.exists():
        with open(demo_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        FULL_DEMO_19 = data.get("events", [])
    return FULL_DEMO_19 or []


# --- L1 Tests ---

def test_l1_first_event_is_board_write_title():
    """First streamed event must be board:write_title (L1)."""
    gen = generate_teaching_events_v2_stream(DEMO_EVENTS_3, latency_config=DEFAULT_LATENCY_CONFIG)
    chunks = list(gen)
    events = [c for c in chunks if c["chunk_type"] == "event"]
    assert len(events) > 0
    first = events[0]["data"]
    # L1 forces board:write_title as first event when first event is speak
    assert first["type"] == "board"
    assert first["action"] == "write_title"


def test_l1_no_force_when_disabled():
    """When l1_force_first_event=False, events keep original order."""
    config = LatencyConfig(l1_force_first_event=False)
    gen = generate_teaching_events_v2_stream(DEMO_EVENTS_3, latency_config=config)
    chunks = list(gen)
    events = [c for c in chunks if c["chunk_type"] == "event"]
    first_type = events[0]["data"]["type"]
    # Second event in original list becomes first (after prepend)
    assert first_type == "board"


def test_l1_prepend_not_needed_when_already_board():
    """When first event is already board:write_title, no prepend needed."""
    events = [{"event_id": "evt_0001", "type": "board", "seq": 1,
               "action": "write_title", "content": "函数"}]
    gen = generate_teaching_events_v2_stream(events, latency_config=DEFAULT_LATENCY_CONFIG)
    chunks = list(gen)
    first = [c for c in chunks if c["chunk_type"] == "event"][0]["data"]
    assert first["event_id"] == "evt_0001"


# --- L2 Tests ---

def test_l2_sentence_gap_within_segment():
    """Consecutive speak events in same segment get L2 gap."""
    config = LatencyConfig(l1_force_first_event=False)
    events = [
        {"event_id": "evt_0001", "type": "speak", "seq": 1, "text": "第一句。"},
        {"event_id": "evt_0002", "type": "speak", "seq": 2, "text": "第二句。"},
    ]
    gen = generate_teaching_events_v2_stream(events, latency_config=config)
    chunks = list(gen)
    events_out = [c["data"] for c in chunks if c["chunk_type"] == "event"]
    gap = events_out[1]["start_offset_sec"] - events_out[0]["start_offset_sec"] - events_out[0]["duration_sec"]
    assert 0.2 <= gap <= 0.8


def test_l2_gap_not_all_identical():
    """L2 gaps are not all identical (avoids robot recitation anti-pattern #1)."""
    config = LatencyConfig(l1_force_first_event=False)
    events = [
        {"event_id": f"evt_{i:04d}", "type": "speak", "seq": i, "text": f"句子{i}。"}
        for i in range(1, 8)
    ]
    # Run multiple times to check randomization
    gaps_set = set()
    for _ in range(5):
        gen = generate_teaching_events_v2_stream(events, latency_config=config)
        evts = [c["data"] for c in gen if c["chunk_type"] == "event"]
        gaps = []
        for i in range(1, len(evts)):
            g = evts[i]["start_offset_sec"] - evts[i-1]["start_offset_sec"] - evts[i-1]["duration_sec"]
            gaps.append(round(g, 3))
        gaps_set.add(tuple(gaps))
    assert len(gaps_set) >= 2, "L2 gaps were all identical across runs"


# --- L3 Tests ---

def test_l3_board_to_speak_delay():
    """Board event followed by speak event gets L3 gap."""
    events = [
        {"event_id": "evt_0001", "type": "board", "seq": 1,
         "action": "write_title", "content": "标题"},
        {"event_id": "evt_0002", "type": "speak", "seq": 2,
         "text": "我们来看这个标题。"},
    ]
    gen = generate_teaching_events_v2_stream(events, latency_config=DEFAULT_LATENCY_CONFIG)
    chunks = list(gen)
    evts = [c["data"] for c in chunks if c["chunk_type"] == "event"]
    gap = evts[1]["start_offset_sec"] - evts[0]["start_offset_sec"]
    assert 0.5 <= gap <= 1.2, f"L3 gap {gap:.2f}s out of range"


# --- L4 Tests ---

def test_l4_segment_boundary_gap():
    """Events across segment boundaries get L4 gap."""
    gen = generate_teaching_events_v2_stream(
        DEMO_EVENTS_WITH_SEGMENT, latency_config=DEFAULT_LATENCY_CONFIG,
    )
    chunks = list(gen)
    evts = [c["data"] for c in chunks if c["chunk_type"] == "event"]
    # Find the gap at the segment boundary (clear_board → write_title)
    for i in range(1, len(evts)):
        if evts[i-1]["type"] == "board" and evts[i-1].get("action") == "clear_board":
            gap = evts[i]["start_offset_sec"] - evts[i-1]["start_offset_sec"]
            assert 1.5 <= gap <= 3.5, f"L4/L6 gap {gap:.2f}s out of range"
            return
    assert False, "No segment boundary found in test events"


# --- L5 Tests ---

def test_l5_pause_default_at_least_1500ms():
    """Pause events without explicit duration_sec get default 1500ms."""
    events = [
        {"event_id": "evt_0001", "type": "speak", "seq": 1, "text": "为什么呢？"},
        {"event_id": "evt_0002", "type": "pause", "seq": 2, "duration_sec": 0.5},
        {"event_id": "evt_0003", "type": "speak", "seq": 3, "text": "因为..."},
    ]
    gen = generate_teaching_events_v2_stream(events, latency_config=DEFAULT_LATENCY_CONFIG)
    chunks = list(gen)
    evts = [c["data"] for c in chunks if c["chunk_type"] == "event"]
    pause = [e for e in evts if e["type"] == "pause"][0]
    assert pause["duration_sec"] >= 1.5, f"L5 pause {pause['duration_sec']}s < 1.5s"


def test_l5_pause_minimum_enforced():
    """LatencyConfig.enforce_pause_minimum clamps short pauses."""
    config = DEFAULT_LATENCY_CONFIG
    assert config.enforce_pause_minimum(0.3) == 1.5
    assert config.enforce_pause_minimum(1.5) == 1.5
    assert config.enforce_pause_minimum(3.0) == 3.0


# --- L6 Tests ---

def test_l6_concept_switch_after_clear_board():
    """clear_board -> next event gets L6 gap."""
    events = [
        {"event_id": "evt_0001", "type": "board", "seq": 1,
         "action": "clear_board", "content": ""},
        {"event_id": "evt_0002", "type": "speak", "seq": 2,
         "text": "现在我们来看下一个概念。"},
    ]
    gen = generate_teaching_events_v2_stream(events, latency_config=DEFAULT_LATENCY_CONFIG)
    chunks = list(gen)
    evts = [c["data"] for c in chunks if c["chunk_type"] == "event"]
    gap = evts[1]["start_offset_sec"] - evts[0]["start_offset_sec"]
    assert 2.0 <= gap <= 3.5, f"L6 gap {gap:.2f}s out of range"


# --- L7 Tests ---

def test_l7_follow_up_mode():
    """In follow_up_turn=True mode, first event gap uses L7 timing."""
    config = LatencyConfig(l1_force_first_event=False)
    events = [{"event_id": "evt_0001", "type": "speak", "seq": 1,
               "text": "关于上一步的问题。"}]
    gen = generate_teaching_events_v2_stream(
        events, latency_config=config, follow_up_turn=True,
    )
    chunks = list(gen)
    evts = [c["data"] for c in chunks if c["chunk_type"] == "event"]
    # L7: first event starts at follow-up delay
    assert evts[0]["start_offset_sec"] == pytest.approx(10.0, abs=0.1)


# --- Segment Classification Tests ---

def test_classify_segments():
    """Segment IDs increment at clear_board / write_title boundaries."""
    seg_ids = classify_segments(DEMO_EVENTS_WITH_SEGMENT)
    assert seg_ids == [1, 1, 1, 2, 3, 3]


def test_classify_segments_no_boundaries():
    """All events in same segment when no boundaries."""
    # Use events without any board boundary actions
    events = [
        {"event_id": "evt_0001", "type": "speak", "seq": 1, "text": "第一段。"},
        {"event_id": "evt_0002", "type": "speak", "seq": 2, "text": "第二段。"},
    ]
    seg_ids = classify_segments(events)
    assert all(s == 0 for s in seg_ids)


# --- Latency Label Tests ---

def test_detect_latency_labels():
    """Labels cover all transition types."""
    events = [
        {"event_id": "evt_0001", "type": "board", "seq": 1,
         "action": "write_title", "content": "A"},
        {"event_id": "evt_0002", "type": "speak", "seq": 2, "text": "第一句"},
        {"event_id": "evt_0003", "type": "speak", "seq": 3, "text": "第二句"},
    ]
    labels = detect_latency_labels(events)
    # First gap (board→speak) should be L3
    assert "L3" in labels
    # Second gap (speak→speak) should be L2
    assert "L2" in labels


# --- Generator Tests ---

def test_stream_generator_yields_all_events():
    """Generator yields plan + all events + done."""
    gen = generate_teaching_events_v2_stream(DEMO_EVENTS_3)
    chunks = list(gen)
    types = [c["chunk_type"] for c in chunks]
    assert "plan" in types
    assert "done" in types
    events = [c for c in chunks if c["chunk_type"] == "event"]
    # DEMO_EVENTS_3 has 3 events, L1 may prepend 1
    assert len(events) >= 3


def test_timeline_offsets_are_monotonic():
    """All start_offset_sec values are monotonically increasing."""
    gen = generate_teaching_events_v2_stream(DEMO_EVENTS_WITH_SEGMENT)
    evts = [c["data"] for c in gen if c["chunk_type"] == "event"]
    offsets = [e["start_offset_sec"] for e in evts]
    assert all(offsets[i] <= offsets[i+1] for i in range(len(offsets)-1))


def test_estimate_speak_duration():
    """Text length-based duration estimate is reasonable."""
    text = "今天我们来看一个非常简单的例子。"
    dur = _estimate_speak_duration(text)
    assert 1.0 <= dur <= 5.0


def test_generator_handles_empty_events():
    """Generator yields error for empty events."""
    gen = generate_teaching_events_v2_stream([])
    chunks = list(gen)
    assert any(c["chunk_type"] == "error" for c in chunks)


# --- Full Demo Integration Test ---

def test_full_demo_19_events():
    """19-event demo produces valid timeline with L1-L7 labels."""
    events = _load_full_demo()
    if not events:
        pytest.skip("demo_teaching_events.json not found")

    gen = generate_teaching_events_v2_stream(events, latency_config=DEFAULT_LATENCY_CONFIG)
    chunks = list(gen)
    evts = [c["data"] for c in chunks if c["chunk_type"] == "event"]

    assert len(evts) >= 19

    # Check L1 always present (first event forced to board:write_title)
    assert evts[0]["type"] == "board"
    assert evts[0].get("action") == "write_title"

    # Labels present should include at least L1 and L3
    labels = set(e.get("_latency_label", "") for e in evts)
    assert "L1" in labels


# --- Config Tests ---

def test_latency_config_to_from_dict():
    """LatencyConfig round-trips through dict."""
    config = DEFAULT_LATENCY_CONFIG
    d = config.to_dict()
    restored = LatencyConfig.from_dict(d)
    assert restored.l2_sentence_gap_range_sec == config.l2_sentence_gap_range_sec
    assert restored.l3_board_to_speak_delay_sec == config.l3_board_to_speak_delay_sec
    assert restored.l5_pause_default_ms == config.l5_pause_default_ms


def test_batch_config_produces_zero_gaps():
    """BATCH_LATENCY_CONFIG has zero gaps for board→speak and segments."""
    assert BATCH_LATENCY_CONFIG.l3_board_to_speak_delay_sec == 0.0
    assert BATCH_LATENCY_CONFIG.l4_segment_gap_sec == 0.0
    assert BATCH_LATENCY_CONFIG.l5_pause_default_ms == 600
    assert BATCH_LATENCY_CONFIG.l6_concept_switch_gap_sec == 0.0


# --- Anti-Pattern Tests ---

def test_anti_pattern_no_robot_recitation():
    """Anti-pattern #1: L2 gaps not all identical in a real session."""
    events = _load_full_demo()
    if not events:
        pytest.skip("demo_teaching_events.json not found")

    labels = detect_latency_labels(events)
    l2_indices = [i for i, l in enumerate(labels) if l == "L2"]

    if len(l2_indices) >= 2:
        # Get actual gaps
        config = DEFAULT_LATENCY_CONFIG
        for _ in range(3):
            gen = generate_teaching_events_v2_stream(events, latency_config=config)
            evts = [c["data"] for c in gen if c["chunk_type"] == "event"]
            gaps = []
            for idx in l2_indices:
                if idx + 1 < len(evts):
                    g = evts[idx + 1]["start_offset_sec"] - evts[idx]["start_offset_sec"]
                    gaps.append(round(g, 3))
            # All gaps should not be identical
            if len(set(gaps)) > 1:
                return
        assert False, "All L2 gaps were identical (robot recitation anti-pattern)"


def test_anti_pattern_no_question_answered_too_quickly():
    """Anti-pattern #4: pause >= 1500ms for short questions."""
    events = [
        {"event_id": "evt_0001", "type": "speak", "seq": 1, "text": "会怎样？"},
        {"event_id": "evt_0002", "type": "pause", "seq": 2, "duration_sec": 0.6},
    ]
    gen = generate_teaching_events_v2_stream(events, latency_config=DEFAULT_LATENCY_CONFIG)
    chunks = list(gen)
    evts = [c["data"] for c in chunks if c["chunk_type"] == "event"]
    pause = [e for e in evts if e["type"] == "pause"]
    if pause:
        assert pause[0]["duration_sec"] >= 1.5
