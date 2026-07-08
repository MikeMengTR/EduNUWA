"""
M4 Orchestrator — Agent 编排

消费学生问题 + Skill + 课程上下文，产生符合 schema 的 teaching_events，
支持流式输出和文件监控模式。
"""
from .latency_config import LatencyConfig, DEFAULT_LATENCY_CONFIG
from .emitter.teaching_events import generate_teaching_events_v2_stream
from .pipeline import OrchestratorPipeline
