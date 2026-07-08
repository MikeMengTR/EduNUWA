"""
M2 指标提炼子模块（metric_extractor）。

职责：把转写/反馈变成可量化、可匹配的指标产物。
与 skill_distiller（产 TeacherSkill.md 文字）分工：本模块产「机器层」指标。

子模块：
    base_metrics   — 客观指标（语速/互动频次），纯计算，无 LLM
    style_tagger   — 开放风格标签（auto），LLM 提炼（Phase 2 完善）
    embedding      — 标签向量化（Phase 2，规模化召回时才需要）
    crowd_tagger   — 学生反馈 → crowd 标签归并（Phase 2）

MVP 已实现：base_metrics。
"""

from .base_metrics import extract_base_metrics  # noqa: F401
from .style_tagger import extract_style_tags  # noqa: F401

__all__ = ["extract_base_metrics", "extract_style_tags"]
