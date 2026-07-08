"""
流式事件生成器 — 独立于原始 M4 模块的新增功能。

将事件以流式方式逐事件产出，应用 L1-L7 延迟节奏。
纯标准库依赖，不触发 M2_distill。
"""
import os
import json
import re
import time
import threading
import traceback
from pathlib import Path
from typing import Iterator
from dataclasses import dataclass, asdict
import random


# ============================================================
# L1-L7 延迟配置
# ============================================================
@dataclass
class LatencyConfig:
    l1_first_event_type: str = "board:write_title"
    l1_force_first_event: bool = True
    l2_sentence_gap_range_sec: tuple[float, float] = (0.3, 0.6)
    l2_default_sec: float = 0.4
    l3_board_to_speak_delay_sec: float = 0.8
    l4_segment_gap_sec: float = 1.5
    l5_pause_default_ms: int = 1500
    l6_concept_switch_gap_sec: float = 2.5
    l7_follow_up_first_utterance_sec: float = 10.0

    def get_gap_for_transition(self, prev_type=None, prev_action=None,
                                next_type=None, next_action=None,
                                prev_segment_idment_id=None, next_segment_idment_id=None) -> float:
        if prev_type is None:
            return 0.0
        if prev_type == "pause":
            return 0.0
        seg_changed = (prev_segment_idment_id is not None and next_segment_idment_id is not None and prev_segment_idment_id != next_segment_idment_id)
        if seg_changed and prev_action == "clear_board":
            return self.l6_concept_switch_gap_sec
        if seg_changed and prev_type == "board" and prev_action in ("write_title", "write_subtitle"):
            return self.l6_concept_switch_gap_sec
        if seg_changed:
            return self.l4_segment_gap_sec
        if prev_type in ("board", "formula", "table") and next_type == "speak":
            return self.l3_board_to_speak_delay_sec
        if prev_type == "speak" and next_type == "speak":
            return round(random.uniform(*self.l2_sentence_gap_range_sec), 3)
        if prev_type == "speak" and next_type == "board":
            return 0.0
        return self.l2_default_sec

    def enforce_pause_minimum(self, duration_sec: float) -> float:
        return max(duration_sec, self.l5_pause_default_ms / 1000.0)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "LatencyConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


DEFAULT_LATENCY_CONFIG = LatencyConfig()


# ============================================================
# 工具函数
# ============================================================
BOUNDARY_ACTIONS = {"write_title", "write_subtitle", "clear_board"}


def classify_segments(events: list[dict]) -> list[int]:
    seg_ids = []
    current_seg = 0
    for evt in events:
        if evt.get("type") == "board" and evt.get("action") in BOUNDARY_ACTIONS:
            current_seg += 1
        seg_ids.append(current_seg)
    return seg_ids


def _estimate_speak_duration(text: str) -> float:
    return max(1.0, len(text) / 4.0)


def _preprocess_text(text: str) -> str:
    superscripts = str.maketrans({
        '⁰': '0', '¹': '1', '⁴': '4', '⁵': '5', '⁶': '6',
        '⁷': '7', '⁸': '8', '⁹': '9',
        '₀': '0', '₁': '1', '₂': '2', '₃': '3', '₄': '4',
        '₅': '5', '₆': '6', '₇': '7', '₈': '8', '₉': '9',
    })
    text = text.translate(superscripts)
    replacements = [
        ('²', '平方'), ('³', '立方'), ('½', '二分之一'),
        ('√', '根号'), ('∫', '积分'), ('∑', '求和'),
        ('→', '到'), ('∈', '属于'), ('≈', '约等于'),
        ('≠', '不等于'), ('α', '阿尔法'), ('β', '贝塔'),
        ('π', '派'), ('·', '点'), ('×', '乘'), ('÷', '除以'),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    text = re.sub(r'\\([a-zA-Z]+)', '', text)
    text = re.sub(r'([一-鿿])([a-zA-Z])', r'\1 \2', text)
    text = re.sub(r'([a-zA-Z])([一-鿿])', r'\1 \2', text)
    text = re.sub(r'[{}[\]\'\"`]', '', text)
    text = text.replace(',', '，').replace(';', '；').replace(':', '：')
    return text


# ============================================================
# 流式生成器
# ============================================================
def generate_teaching_events_v2_stream(
    events_source: str | list[dict],
    latency_config: LatencyConfig | None = None,
    audio_manifest_path: str | None = None,
    follow_up_turn: bool = False,
) -> Iterator[dict]:
    """流式逐事件产出，应用 L1-L7 节奏。不依赖任何外部模块。"""
    if latency_config is None:
        latency_config = DEFAULT_LATENCY_CONFIG

    if isinstance(events_source, str):
        with open(events_source, "r", encoding="utf-8") as f:
            data = json.load(f)
        events = data.get("events", [])
    else:
        events = events_source
        data = {}

    if not events:
        yield {"chunk_type": "error", "data": {"message": "No events"}}
        return

    events_sorted = sorted(events, key=lambda e: e.get("seq", 0))

    # L1: 首事件强制 board:write_title
    if (latency_config.l1_force_first_event and
        (events_sorted[0].get("type") != "board" or
         events_sorted[0].get("action") != "write_title")):
        events_sorted.insert(0, {
            "event_id": f"evt_L1_{events_sorted[0].get('event_id', '0000')}",
            "type": "board", "seq": 0,
            "action": "write_title", "content": data.get("topic", ""),
            "_l1_prepend": True,
        })

    yield {"chunk_type": "plan", "data": {"event_count": len(events_sorted)}}

    audio_items = {}
    if audio_manifest_path and os.path.exists(audio_manifest_path):
        with open(audio_manifest_path, "r", encoding="utf-8") as f:
            am = json.load(f)
            audio_items = {i["event_id"]: i for i in am.get("items", [])}

    seg_ids = classify_segments(events_sorted)
    current_offset = 0.0
    event_count = 0

    for i, evt in enumerate(events_sorted):
        evt_type = evt.get("type", "speak")
        event_count += 1

        gap = 0.0
        label = "L1"
        if i == 0:
            if follow_up_turn:
                gap = latency_config.l7_follow_up_first_utterance_sec
                label = "L7"
        else:
            prev = events_sorted[i - 1]
            gap = latency_config.get_gap_for_transition(
                prev_type=prev.get("type"), prev_action=prev.get("action"),
                next_type=evt_type, next_action=evt.get("action"),
                prev_segment_idment_id=seg_ids[i - 1], next_segment_idment_id=seg_ids[i],
            )
            label = "L2" if prev.get("type") == "speak" and evt_type == "speak" else \
                    "L3" if prev.get("type") in ("board", "formula", "table") and evt_type == "speak" else \
                    "L4" if seg_ids[i - 1] != seg_ids[i] else \
                    "L6" if prev.get("action") == "clear_board" else \
                    "L5" if evt_type == "pause" else "other"

        current_offset += gap

        item = {
            "seq": event_count, "type": evt_type,
            "event_id": evt.get("event_id", f"evt_{event_count:04d}"),
            "start_offset_sec": round(current_offset, 3),
            "_latency_label": label, "_gap_sec": round(gap, 3),
        }

        if evt_type == "speak":
            text = evt.get("text", "")
            ai = audio_items.get(item["event_id"], {})
            item.update({"text": text, "tts_text": _preprocess_text(text),
                         "audio_path": ai.get("audio_path", ""),
                         "duration_sec": ai.get("duration_sec", _estimate_speak_duration(text))})
            current_offset += item["duration_sec"]

        elif evt_type == "board":
            item.update({"action": evt.get("action", ""), "content": evt.get("content", ""), "dwell_sec": 1.5})
            current_offset += 1.5

        elif evt_type == "formula":
            item.update({"latex": evt.get("latex", ""), "display_mode": evt.get("display_mode", "block")})
            current_offset += 1.5

        elif evt_type == "table":
            item.update({"title": evt.get("title", ""), "columns": evt.get("columns", []), "rows": evt.get("rows", [])})
            current_offset += 2.0

        elif evt_type == "pause":
            dur = latency_config.enforce_pause_minimum(evt.get("duration_sec", 1.0))
            item["duration_sec"] = dur
            current_offset += dur

        elif evt_type == "quiz":
            item.update({"question": evt.get("question", ""), "options": evt.get("options", []), "blocking": True})
            current_offset += 1.5

        yield {"chunk_type": "event", "data": item}

    yield {"chunk_type": "done", "data": {"total": event_count, "total_duration_sec": round(current_offset, 2)}}


# ============================================================
# 自动管道 + 监控模式
# ============================================================
class OrchestratorPipeline:
    def __init__(self, latency_config: LatencyConfig | None = None):
        self.config = latency_config or DEFAULT_LATENCY_CONFIG

    def run(self, session_id: str, user_question: str, **kwargs) -> dict:
        events = self._generate_events_from_question(user_question)
        output_dir = f"data/sessions/{session_id}"
        os.makedirs(f"{output_dir}/events", exist_ok=True)

        turn = 1
        events_data = {
            "event_file_id": f"teaching_events_{session_id}_t{turn}",
            "session_id": session_id, "turn": turn,
            "question": user_question,
            "events": events,
        }
        events_path = f"{output_dir}/events/turn_{turn}.json"
        with open(events_path, "w", encoding="utf-8") as f:
            json.dump(events_data, f, ensure_ascii=False, indent=2)

        return {"status": "success", "session_id": session_id,
                "events_path": events_path, "events_count": len(events)}

    def _generate_events_from_question(self, question: str) -> list[dict]:
        return [
            {"event_id": "evt_0001", "type": "board", "seq": 1,
             "action": "write_title", "content": question[:15]},
            {"event_id": "evt_0002", "type": "speak", "seq": 2,
             "text": f"今天我们来讲一下{question[:20]}。这是一个非常重要的概念。"},
            {"event_id": "evt_0003", "type": "speak", "seq": 3,
             "text": "我们先来看一个生活中的例子，帮助大家建立直觉。"},
            {"event_id": "evt_0004", "type": "pause", "seq": 4, "duration_sec": 2.0},
            {"event_id": "evt_0005", "type": "speak", "seq": 5,
             "text": "从这个例子可以看出，理解这个概念的关键在于把握它的本质。"},
            {"event_id": "evt_0006", "type": "quiz", "seq": 6,
             "question": "以下哪个最能描述这个概念的核心理念？",
             "options": ["定义", "应用", "历史", "误用"], "blocking": True},
        ]

    def watch(self, watch_dir: str = "data/requests", poll_interval: float = 3.0):
        """监控模式：监听新请求文件并自动处理。"""
        print(f"\n{'='*60}")
        print(f"  M4 Watch Mode — 监控: {watch_dir}")
        print(f"  Poll 间隔: {poll_interval}s")
        print(f"{'='*60}\n")

        os.makedirs(watch_dir, exist_ok=True)
        seen = set()

        while True:
            for req_file in sorted(Path(watch_dir).glob("*_request.json")):
                fpath = str(req_file)
                if fpath in seen:
                    continue
                seen.add(fpath)
                print(f"\n>>> 检测到新请求: {req_file.name}")
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        req = json.load(f)
                    sid = req.get("session_id", req_file.stem.replace("_request", ""))
                    self.run(session_id=sid, user_question=req.get("user_question", ""))
                    processed = fpath.replace("_request.json", "_done.json")
                    os.rename(fpath, processed)
                    print(f"  ✅ 完成: {sid}")
                except Exception as e:
                    print(f"  [ERROR] {e}")
                    traceback.print_exc()
            time.sleep(poll_interval)
