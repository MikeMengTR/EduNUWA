"""M1 ASR 引擎：Whisper 高精度语音转写 (faster_whisper)。"""

import os
import math
import logging
from datetime import datetime, timezone, timedelta

from .config import get_engine_config

logger = logging.getLogger(__name__)

_whisper_available = None
TZ_CHINA = timezone(timedelta(hours=8))


def _check_whisper() -> bool:
    """惰性检查 faster_whisper 是否可用。"""
    global _whisper_available
    if _whisper_available is None:
        try:
            from faster_whisper import WhisperModel  # noqa: F401
            _whisper_available = True
        except ImportError:
            _whisper_available = False
    return _whisper_available


def transcribe_audio(
    audio_path: str,
    transcript_id: str,
    teacher_id: str,
    source_file: str,
    config: dict | None = None,
) -> dict:
    """对单个音频文件执行高精度 ASR 转写，返回标准 teacher_transcript dict（对齐 §3.4）。

    config 键: model_size("large-v3"), device("cuda"), compute_type("float16"),
    cpu_threads(16), cache_dir(None), language("zh"), beam_size(5),
    initial_prompt(MATH_ASR_PROMPT), vad_filter(True),
    compression_ratio_threshold(2.4), no_speech_threshold(0.6)

    Requires: pip install faster_whisper
    """
    if not _check_whisper():
        raise ImportError("faster_whisper 未安装，请执行: pip install faster_whisper")
    from faster_whisper import WhisperModel

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")

    cfg = get_engine_config("whisper", config)
    model_size = cfg["model_size"]
    logger.info(f"加载 Whisper 模型 [{model_size}]，首次使用将自动下载约 3GB")
    try:
        model = WhisperModel(
            model_size,
            device=cfg["device"],
            compute_type=cfg["compute_type"],
            cpu_threads=cfg["cpu_threads"],
            download_root=cfg.get("cache_dir"),
        )
    except Exception as e:
        msg = str(e)
        if any(kw in msg for kw in ("Network", "ConnectError", "unreachable")):
            raise ConnectionError(
                f"无法下载 Whisper 模型 [{model_size}]，请检查网络。"
                f"可设置 HF_MIRROR 环境变量使用镜像加速。\n原始错误: {msg}"
            )
        raise

    logger.info(f"开始转写: {audio_path}")
    segments, info = model.transcribe(
        audio_path,
        vad_filter=cfg["vad_filter"],
        beam_size=cfg["beam_size"],
        initial_prompt=cfg["initial_prompt"],
        language=cfg["language"],
        condition_on_previous_text=False,
        compression_ratio_threshold=cfg["compression_ratio_threshold"],
        no_speech_threshold=cfg["no_speech_threshold"],
    )

    result = {
        "transcript_id": transcript_id,
        "teacher_id": teacher_id,
        "source_file": source_file,
        "source_audio": audio_path,
        "language": info.language,
        "asr_backend": f"whisper-{model_size}",
        "ingested_at": datetime.now(TZ_CHINA).isoformat(),
        "segments": [],
    }

    confidences = []
    low_conf_count = 0
    for idx, seg in enumerate(segments):
        confidence = round(math.exp(seg.avg_logprob), 4) if seg.avg_logprob is not None else 1.0
        confidences.append(confidence)
        if confidence < 0.7:
            low_conf_count += 1
        result["segments"].append({
            "segment_id": f"seg_{idx + 1:04d}",
            "start": round(seg.start, 2),
            "end": round(seg.end, 2),
            "text": seg.text.strip(),
            "speaker": "teacher",
            "confidence": confidence,
        })

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    result["asr_quality"] = {
        "estimated_cer": round(max(0.0, min(1.0, 1.0 - avg_conf)), 4),
        "low_confidence_segments": low_conf_count,
    }

    total_dur = (
        result["segments"][-1]["end"] - result["segments"][0]["start"]
        if result["segments"]
        else 0.0
    )
    logger.info(
        f"转写完成: {len(result['segments'])} 段, 时长 {total_dur:.1f}s, "
        f"estimated_cer={result['asr_quality']['estimated_cer']}, "
        f"low_conf_segments={low_conf_count}"
    )
    return result


# ============================================================
# 冒烟测试
# ============================================================
if __name__ == "__main__":
    print("=== whisper_runner 冒烟测试 ===\n")

    # 缺少依赖时抛 ImportError
    if not _check_whisper():
        try:
            transcribe_audio("fake.wav", "TR_T_001", "T_001", "test.mp4")
            assert False
        except ImportError as e:
            print(f"[OK] ImportError: {e}")
    else:
        print("[OK] faster_whisper 可用")
        try:
            transcribe_audio("nonexistent.wav", "TR_T_001", "T_001", "test.mp4")
            assert False
        except FileNotFoundError as e:
            print(f"[OK] FileNotFoundError: {e}")

    print("[PASS]")
