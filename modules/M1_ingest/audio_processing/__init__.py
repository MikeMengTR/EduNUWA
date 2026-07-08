"""M1 Audio Processing: extract, segment, pick TTS samples."""
from .extractor import extract_audio_from_video, save_audio_sample
from .segmenter import segment_audio, get_audio_duration_sec
