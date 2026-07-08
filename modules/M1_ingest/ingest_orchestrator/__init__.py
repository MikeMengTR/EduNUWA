"""M1 Ingest Orchestrator: main pipeline + async tasks."""
from .orchestrator import ingest_teacher_material
from .file_manager import generate_upload_id, generate_transcript_id, setup_teacher_dirs, atomic_write_json
