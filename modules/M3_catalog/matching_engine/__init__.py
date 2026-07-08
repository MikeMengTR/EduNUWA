"""
M3 匹配引擎（matching_engine）。

MVP：LLM 直接语义匹配——学生用自然语言描述想要的老师，
LLM 读候选老师的开放风格标签 + 基础指标，输出排序 + 推荐理由。

规模化（Phase 2）再换 embedding 向量召回 + LLM 精排两阶段。
"""

from .matcher import load_teachers, match_teachers  # noqa: F401

__all__ = ["load_teachers", "match_teachers"]
