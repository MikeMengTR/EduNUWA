"""M2 标签进化器：学生反馈 → 风格标签梯度更新（textual gradient）。"""
from .evolver import refresh_crowd_tags, extract_md_sections, _calibrate
from .revision import propose_skill_revision

__all__ = ["refresh_crowd_tags", "propose_skill_revision", "extract_md_sections", "_calibrate"]
