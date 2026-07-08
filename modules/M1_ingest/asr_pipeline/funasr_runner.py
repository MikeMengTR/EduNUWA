"""M1 ASR 引擎：FunASR Paraformer 高精度语音转写 (funasr)。"""

import os
import logging
from datetime import datetime, timezone, timedelta

from .config import get_engine_config

logger = logging.getLogger(__name__)

_funasr_available = None
TZ_CHINA = timezone(timedelta(hours=8))


def _check_funasr() -> bool:
    """惰性检查 funasr 是否可用。"""
    global _funasr_available
    if _funasr_available is None:
        try:
            from funasr import AutoModel  # noqa: F401
            _funasr_available = True
        except ImportError:
            _funasr_available = False
    return _funasr_available


def transcribe_audio(
    audio_path: str,
    transcript_id: str,
    teacher_id: str,
    source_file: str,
    config: dict | None = None,
) -> dict:
    """对单个音频文件执行高精度 ASR 转写，返回标准 teacher_transcript dict（对齐 §3.4）。

    config 键: model("paraformer-zh"), vad_model("fsmn-vad"), punc_model("ct-punc"),
    device("cuda"), ncpu(16), use_vad(True), hotwords(学科术语), batch_size_s(300)

    Requires: pip install funasr
    """
    if not _check_funasr():
        raise ImportError("funasr 未安装，请执行: pip install funasr")
    from funasr import AutoModel

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")

    cfg = get_engine_config("funasr", config)
    model_name = cfg["model"]

    logger.info(f"加载 FunASR 模型 [{model_name}]，首次使用将自动下载")

    # 组装 AutoModel 参数（引擎不认识的键静默忽略）
    model_kwargs = {
        "model": model_name,
        "device": cfg.get("device", "cuda"),
        "ncpu": cfg.get("ncpu", 16),
        "hub": cfg.get("hub", "ms"),
    }
    if cfg.get("use_vad", True) and cfg.get("vad_model"):
        model_kwargs["vad_model"] = cfg["vad_model"]
    if cfg.get("punc_model"):
        model_kwargs["punc_model"] = cfg["punc_model"]
    # hotwords：新版 FunASR 直接支持字符串
    if cfg.get("hotwords"):
        model_kwargs["hotword"] = cfg["hotwords"]

    try:
        model = AutoModel(**model_kwargs)
    except Exception as e:
        msg = str(e)
        if any(kw in msg for kw in ("Network", "ConnectError", "unreachable", "download")):
            raise ConnectionError(
                f"无法下载 FunASR 模型 [{model_name}]，请检查网络。\n原始错误: {msg}"
            )
        raise

    logger.info(f"开始转写: {audio_path}")
    try:
        output = model.generate(
            input=audio_path,
            batch_size_s=cfg.get("batch_size_s", 300),
        )
    except Exception as e:
        raise RuntimeError(f"FunASR 转写失败: {e}")

    # 解析 FunASR 输出 → 标准 segments 结构
    # output 为列表 [per_file_results]，per_file_results 为 list[dict] 或 dict
    raw = output[0] if output else []

    segments = []
    confidences = []
    low_conf_count = 0

    if isinstance(raw, list) and raw:
        # 标准格式: [{"text": "...", "start": 100, "end": 3200}, ...]
        for idx, seg in enumerate(raw):
            if not isinstance(seg, dict):
                continue
            text = seg.get("text", "").strip()
            if not text:
                continue

            # 时间戳（FunASR 输出毫秒，转换为秒）
            start_ms = seg.get("start", 0)
            end_ms = seg.get("end", 0)
            if (start_ms == 0 and end_ms == 0) and "timestamp" in seg:
                ts = seg["timestamp"]
                if ts and isinstance(ts, list) and ts[0]:
                    start_ms = ts[0][0] if isinstance(ts[0], list) else 0
                    end_ms = ts[-1][-1] if isinstance(ts[-1], list) else 0

            start_sec = round(start_ms / 1000.0, 2) if start_ms else round(idx * 5.0, 2)
            end_sec = round(end_ms / 1000.0, 2) if end_ms else round((idx + 1) * 5.0, 2)

            confidence = seg.get("confidence", seg.get("score", 1.0))
            if isinstance(confidence, (int, float)):
                confidence = round(float(confidence), 4)
            else:
                confidence = 1.0
            confidences.append(confidence)
            if confidence < 0.7:
                low_conf_count += 1

            segments.append({
                "segment_id": f"seg_{idx + 1:04d}",
                "start": start_sec,
                "end": end_sec,
                "text": text,
                "speaker": "teacher",
                "confidence": confidence,
            })

    elif isinstance(raw, dict):
        # 单段返回 {"text": "..."}，尝试从 sentence_info 展开
        full_text = raw.get("text", "").strip()
        sentence_info = raw.get("sentence_info", [])
        if sentence_info and isinstance(sentence_info, list):
            for idx, si in enumerate(sentence_info):
                text = si.get("text", "").strip()
                if not text:
                    continue
                start_sec = round(si.get("start", idx * 5.0) / 1000.0, 2)
                end_sec = round(si.get("end", (idx + 1) * 5.0) / 1000.0, 2)
                segments.append({
                    "segment_id": f"seg_{idx + 1:04d}",
                    "start": start_sec,
                    "end": end_sec,
                    "text": text,
                    "speaker": "teacher",
                    "confidence": si.get("confidence", 1.0),
                })
        elif full_text:
            segments.append({
                "segment_id": "seg_0001",
                "start": 0.0,
                "end": 0.0,
                "text": full_text,
                "speaker": "teacher",
                "confidence": 0.5,
            })

    # 兜底：没有任何有效段
    if not segments:
        logger.warning("FunASR 未返回可解析的内容，返回空 segments")
        segments.append({
            "segment_id": "seg_0001",
            "start": 0.0,
            "end": 0.0,
            "text": "",
            "speaker": "teacher",
            "confidence": 0.0,
        })
        confidences = [0.0]

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

    result = {
        "transcript_id": transcript_id,
        "teacher_id": teacher_id,
        "source_file": source_file,
        "source_audio": audio_path,
        "language": cfg.get("language", "zh"),
        "asr_backend": f"funasr-{model_name}",
        "asr_quality": {
            "estimated_cer": round(max(0.0, min(1.0, 1.0 - avg_conf)), 4),
            "low_confidence_segments": low_conf_count,
        },
        "ingested_at": datetime.now(TZ_CHINA).isoformat(),
        "segments": segments,
    }

    total_dur = segments[-1]["end"] - segments[0]["start"] if segments else 0.0
    logger.info(
        f"转写完成: {len(segments)} 段, 时长 {total_dur:.1f}s, "
        f"estimated_cer={result['asr_quality']['estimated_cer']}, "
        f"low_conf_segments={low_conf_count}"
    )
    return result


# ============================================================
# 冒烟测试
# ============================================================
if __name__ == "__main__":
    print("=== funasr_runner 冒烟测试 ===\n")

    if not _check_funasr():
        try:
            transcribe_audio("fake.wav", "TR_T_001", "T_001", "test.mp4")
            assert False
        except ImportError as e:
            print(f"[OK] ImportError: {e}")
    else:
        print("[OK] funasr 可用")
        try:
            transcribe_audio("nonexistent.wav", "TR_T_001", "T_001", "test.mp4")
            assert False
        except FileNotFoundError as e:
            print(f"[OK] FileNotFoundError: {e}")

    print("[PASS]")
