"""
L1-L7 延迟配置 — 从 M4_orchestrator_streaming_latency_spec.md §6 迁移。
控制教学事件的输出节奏。
"""
import random
from dataclasses import dataclass, asdict


@dataclass
class LatencyConfig:
    # L1: 首句开口 — 第一个事件强制 board:write_title
    l1_first_event_type: str = "board:write_title"
    l1_force_first_event: bool = True

    # L2: 句间停顿 (0.3-0.6s)
    l2_sentence_gap_range_sec: tuple[float, float] = (0.3, 0.6)
    l2_default_sec: float = 0.4

    # L3: 板书→接话 (0.8s)
    l3_board_to_speak_delay_sec: float = 0.8

    # L4: 段间过渡 (1.5s)
    l4_segment_gap_sec: float = 1.5

    # L5: 设问停顿 (默认 1500ms)
    l5_pause_default_ms: int = 1500

    # L6: 概念切换 (2.5s)
    l6_concept_switch_gap_sec: float = 2.5

    # L7: 追问开口 (10s)
    l7_follow_up_first_utterance_sec: float = 10.0

    def get_gap_for_transition(self, prev_type, prev_action, next_type, next_action,
                                prev_seg, next_seg) -> float:
        if prev_type is None:
            return 0.0
        if prev_type == "pause":
            return 0.0
        seg_changed = (prev_seg is not None and next_seg is not None and prev_seg != next_seg)
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
