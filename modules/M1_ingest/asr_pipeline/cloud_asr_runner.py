"""M1 ASR 引擎：阿里云百炼 DashScope ASR（OpenAI 兼容接口）。

认证：设置环境变量 DASHSCOPE_API_KEY 或在 config 中传入 api_key。
模型：fun-asr（旗舰，推荐）/ paraformer-v2（免费）/ gummy-realtime-v1（多语种）。

长音频自动切分后逐段调用，带时间戳合并。
"""

import os
import math
import logging
from datetime import datetime, timezone, timedelta

# 自动加载项目根目录 .env 文件（防止 API Key 泄露到 Git）
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')
    load_dotenv(os.path.abspath(_env_path))
except ImportError:
    pass

from .config import get_engine_config

logger = logging.getLogger(__name__)

_openai_available = None
TZ_CHINA = timezone(timedelta(hours=8))

# OpenAI 音频接口限制：单文件 ~25MB，对应 WAV 16kHz 约 80 秒，取 60 秒安全值
MAX_SEGMENT_SEC = 60


def _check_openai() -> bool:
    """惰性检查 openai 包是否可用。"""
    global _openai_available
    if _openai_available is None:
        try:
            from openai import OpenAI  # noqa: F401
            _openai_available = True
        except ImportError:
            _openai_available = False
    return _openai_available


def transcribe_audio(
    audio_path: str,
    transcript_id: str,
    teacher_id: str,
    source_file: str,
    config: dict | None = None,
) -> dict:
    """使用阿里云百炼 DashScope ASR 转写，返回标准 teacher_transcript dict（对齐 §3.4）。

    config 键:
        api_key   — 百炼 API Key（默认读环境变量 DASHSCOPE_API_KEY）
        model     — "fun-asr"（推荐）/ "paraformer-v2"（免费）/ "gummy-realtime-v1"（多语种）
        base_url  — API 端点（默认兼容模式地址）

    Requires: pip install openai
    """
    if not _check_openai():
        raise ImportError("openai 未安装，请执行: pip install openai")
    from openai import OpenAI

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")

    cfg = get_engine_config("cloud", config)

    api_key = cfg.get("api_key") or os.getenv("DASHSCOPE_API_KEY", "")
    if not api_key:
        raise ValueError(
            "缺少 DashScope API Key。请设置环境变量 DASHSCOPE_API_KEY 或 "
            "在 config 中传入 api_key。获取地址: https://bailian.console.aliyun.com/"
        )

    model = cfg.get("model", "fun-asr")
    base_url = cfg.get(
        "base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )

    client = OpenAI(api_key=api_key, base_url=base_url)

    # 检查音频时长，超限则切分
    from ..audio_processing.segmenter import get_audio_duration_sec, segment_audio
    import tempfile

    try:
        duration = get_audio_duration_sec(audio_path)
    except Exception:
        duration = 0.0

    if duration <= MAX_SEGMENT_SEC:
        audio_segments = [(audio_path, 0.0)]
    else:
        logger.info(f"音频过长 ({duration:.0f}s)，按 {MAX_SEGMENT_SEC}s 切分")
        tmp_dir = tempfile.mkdtemp(prefix="dashscope_asr_")
        seg_paths = segment_audio(audio_path, tmp_dir, MAX_SEGMENT_SEC)

        audio_segments = []
        time_offset = 0.0
        for seg_path in seg_paths:
            audio_segments.append((seg_path, time_offset))
            try:
                time_offset += get_audio_duration_sec(seg_path)
            except Exception:
                time_offset += MAX_SEGMENT_SEC

    # 逐段调用 DashScope ASR
    all_segments = []
    confidences = []
    low_conf_count = 0

    for seg_idx, (seg_path, time_offset) in enumerate(audio_segments):
        logger.info(
            f"DashScope ASR 分段 {seg_idx + 1}/{len(audio_segments)}: "
            f"{os.path.basename(seg_path)}"
        )

        try:
            with open(seg_path, "rb") as f:
                resp = client.audio.transcriptions.create(
                    model=model,
                    file=f,
                    response_format="verbose_json",
                )
        except Exception as e:
            msg = str(e)
            if any(kw in msg for kw in ("Unauthorized", "401", "auth")):
                raise ConnectionError(
                    f"DashScope API Key 无效。请检查 DASHSCOPE_API_KEY 环境变量。\n"
                    f"获取 Key: https://bailian.console.aliyun.com/"
                )
            logger.error(f"分段 {seg_idx + 1} 识别失败: {e}")
            all_segments.append({
                "segment_id": f"seg_{len(all_segments) + 1:04d}",
                "start": round(time_offset, 2),
                "end": round(time_offset + MAX_SEGMENT_SEC, 2),
                "text": f"[识别失败: {e}]",
                "speaker": "teacher",
                "confidence": 0.0,
            })
            confidences.append(0.0)
            low_conf_count += 1
            continue

        # 解析 DashScope 返回的 segments（verbose_json 格式含时间戳）
        raw_segs = getattr(resp, "segments", None)
        if raw_segs:
            for s in raw_segs:
                start_sec = round(getattr(s, "start", 0.0) + time_offset, 2)
                end_sec = round(getattr(s, "end", 0.0) + time_offset, 2)
                text = getattr(s, "text", "").strip()
                if not text:
                    continue
                confidence = round(
                    float(getattr(s, "confidence", getattr(s, "score", 0.9))), 4
                )
                confidences.append(confidence)
                if confidence < 0.7:
                    low_conf_count += 1
                all_segments.append({
                    "segment_id": f"seg_{len(all_segments) + 1:04d}",
                    "start": start_sec,
                    "end": end_sec,
                    "text": text,
                    "speaker": "teacher",
                    "confidence": confidence,
                })
        else:
            # 无分段信息：用全文作为单段
            full_text = getattr(resp, "text", "") or str(resp)
            if full_text.strip():
                all_segments.append({
                    "segment_id": f"seg_{len(all_segments) + 1:04d}",
                    "start": round(time_offset, 2),
                    "end": round(time_offset + MAX_SEGMENT_SEC, 2),
                    "text": full_text.strip(),
                    "speaker": "teacher",
                    "confidence": 0.9,
                })
                confidences.append(0.9)

    # 清理临时目录
    if duration > MAX_SEGMENT_SEC:
        import shutil
        shutil.rmtree(os.path.dirname(seg_paths[0]), ignore_errors=True)

    if not all_segments:
        logger.warning("DashScope ASR 未返回可解析的内容")
        all_segments.append({
            "segment_id": "seg_0001",
            "start": 0.0, "end": 0.0,
            "text": "", "speaker": "teacher", "confidence": 0.0,
        })
        confidences = [0.0]

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

    result = {
        "transcript_id": transcript_id,
        "teacher_id": teacher_id,
        "source_file": source_file,
        "source_audio": audio_path,
        "language": cfg.get("language", "zh"),
        "asr_backend": f"cloud-dashscope-{model}",
        "asr_quality": {
            "estimated_cer": round(max(0.0, min(1.0, 1.0 - avg_conf)), 4),
            "low_confidence_segments": low_conf_count,
        },
        "ingested_at": datetime.now(TZ_CHINA).isoformat(),
        "segments": all_segments,
    }

    total_dur = (
        all_segments[-1]["end"] - all_segments[0]["start"]
        if all_segments else 0.0
    )
    logger.info(
        f"DashScope ASR 完成: {len(all_segments)} 段, 时长 {total_dur:.1f}s, "
        f"estimated_cer={result['asr_quality']['estimated_cer']}"
    )
    return result


# ============================================================
# 冒烟测试
# ============================================================
if __name__ == "__main__":
    print("=== cloud_asr_runner 冒烟测试 ===\n")

    if not _check_openai():
        try:
            transcribe_audio("fake.wav", "TR_T_001", "T_001", "test.mp4")
            assert False
        except ImportError as e:
            print(f"[OK] ImportError: {e}")
    else:
        print("[OK] openai 可用")
        try:
            transcribe_audio("nonexistent.wav", "TR_T_001", "T_001", "test.mp4")
            assert False
        except FileNotFoundError as e:
            print(f"[OK] FileNotFoundError: {e}")

    print("[PASS]")
