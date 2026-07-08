"""
Centralized L1-L7 latency configuration per M4_orchestrator_streaming_latency_spec.md §6.

Provides LatencyConfig dataclass with all timing parameters,
transition gap computation, and segment boundary detection.
"""
from __future__ import annotations
import random
from dataclasses import dataclass, field, asdict


@dataclass
class LatencyConfig:
    """L1-L7 latency parameters for natural teaching rhythm.

    All timing values are in seconds unless otherwise noted.
    """

    # L1: First event type (board:write_title to signal teacher is ready)
    l1_first_event_type: str = "board:write_title"
    l1_force_first_event: bool = True

    # L2: Inter-sentence gap within same segment
    # Spec: 0.3-0.6s, randomized for natural variation
    l2_sentence_gap_range_sec: tuple[float, float] = (0.3, 0.6)
    l2_default_sec: float = 0.4

    # L3: Board written -> teacher speaks about it
    # 原 0.8s → 0.3s（减少板书后等待）
    l3_board_to_speak_delay_sec: float = 0.3

    # L4: Cross-segment transition
    # 原 1.5s → 0.6s
    l4_segment_gap_sec: float = 0.6

    # L5: Pause / questioning pause
    # 原 1500ms → 800ms（减少设问思考时间）
    l5_pause_default_ms: int = 800
    l5_short_question_range_sec: tuple[float, float] = (0.8, 1.2)
    l5_medium_question_range_sec: tuple[float, float] = (1.5, 2.5)
    l5_deep_question_range_sec: tuple[float, float] = (3.0, 5.0)
    l5_max_sec: float = 5.0

    # L6: Concept switch / clear_board
    # 原 2.5s → 1.0s
    l6_concept_switch_gap_sec: float = 1.0

    # L7: Follow-up utterance delay (second round)
    l7_follow_up_first_utterance_sec: float = 10.0

    def _random_l2_gap(self) -> float:
        """Return randomized L2 gap within spec range (avoids robot recitation)."""
        lo, hi = self.l2_sentence_gap_range_sec
        return round(random.uniform(lo, hi), 3)

    def get_gap_for_transition(
        self,
        prev_type: str | None,
        prev_action: str | None,
        next_type: str,
        next_action: str | None,
        prev_segment_id: int | None,
        next_segment_id: int | None,
    ) -> float:
        """Compute the gap between two consecutive timeline events.

        Args:
            prev_type: Type of previous event (None for first event)
            prev_action: Board action of previous event (if board type)
            next_type: Type of next event
            next_action: Board action of next event (if board type)
            prev_segment_id: Segment ID of previous event
            next_segment_id: Segment ID of next event

        Returns:
            Gap in seconds between the two events
        """
        # First event: no gap
        if prev_type is None:
            return 0.0

        # Pause event already has its duration built in
        if prev_type == "pause":
            return 0.0

        # Segment boundary check
        segment_changed = (prev_segment_id is not None and next_segment_id is not None
                           and prev_segment_id != next_segment_id)

        # L6: Concept switch (clear_board → next, or segment boundary on clear_board)
        if segment_changed and prev_action == "clear_board":
            return self.l6_concept_switch_gap_sec

        # L6: Concept switch on segment boundary with board clear
        if segment_changed and prev_type == "board" and prev_action in ("write_title", "write_subtitle"):
            return self.l6_concept_switch_gap_sec

        # L4: Cross-segment transition
        if segment_changed:
            return self.l4_segment_gap_sec

        # L3: Board → speak
        if prev_type in ("board", "formula", "table") and next_type == "speak":
            return self.l3_board_to_speak_delay_sec

        # L2: Speak → speak (same segment) — randomized
        if prev_type == "speak" and next_type == "speak":
            return self._random_l2_gap()

        # Speak → board: no gap (board renders during speaking pause)
        if prev_type == "speak" and next_type == "board":
            return 0.0

        # Default: L2 gap
        return self.l2_default_sec

    def enforce_pause_minimum(self, duration_sec: float) -> float:
        """Enforce L5 minimum pause duration (spec: ≥1500ms)."""
        min_sec = self.l5_pause_default_ms / 1000.0
        return max(duration_sec, min_sec)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "LatencyConfig":
        return cls(**{
            k: v for k, v in d.items()
            if k in cls.__dataclass_fields__
        })


# Spec-recommended defaults
DEFAULT_LATENCY_CONFIG = LatencyConfig()

# Batch-compatible config (mirrors old M5 builder behavior)
BATCH_LATENCY_CONFIG = LatencyConfig(
    l3_board_to_speak_delay_sec=0.0,
    l4_segment_gap_sec=0.0,
    l5_pause_default_ms=600,
    l6_concept_switch_gap_sec=0.0,
)
