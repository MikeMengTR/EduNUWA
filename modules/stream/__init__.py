"""
Stream Module — Streaming latency layer for EduNUWA v2.
Bridges M4 (Orchestrator) and M5 (Runtime) with L1-L7 latency timing.
"""

from .latency_config import LatencyConfig, DEFAULT_LATENCY_CONFIG
from .streaming_orchestrator import generate_teaching_events_v2_stream

__all__ = [
    "LatencyConfig",
    "DEFAULT_LATENCY_CONFIG",
    "generate_teaching_events_v2_stream",
]
