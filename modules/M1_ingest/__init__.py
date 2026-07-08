"""
M1 Ingest 模块：教师素材摄取（视频/音频/PDF/PPTX → 结构化 transcript）。

使用方式：
    from modules.M1_ingest import ingest_teacher_material

    result = ingest_teacher_material(
        teacher_id="T_20260515_001",
        source_paths=["lecture1.mp4", "handout.pdf"],
        output_dir="data/teachers/T_20260515_001",
    )
"""

from .ingest_orchestrator.orchestrator import ingest_teacher_material  # noqa: F401
from .ingest_orchestrator.file_manager import (  # noqa: F401
    generate_upload_id,
    generate_transcript_id,
    setup_teacher_dirs,
    atomic_write_json,
)

__all__ = [
    "ingest_teacher_material",
    "generate_upload_id",
    "generate_transcript_id",
    "setup_teacher_dirs",
    "atomic_write_json",
]
