"""
M1 素材摄取主编排器：ingest_teacher_material()。

串联音频提取 → ASR 转写 → LLM 精修 → 文档（PDF/PPTX）提取的全流程。
所有文件输出通过 file_manager 原子写入，对齐 v2 多租户目录规范。
"""

import os
import sys
import json
import shutil
import logging

from . import file_manager
from ..audio_processing.extractor import extract_audio_from_video, save_audio_sample
from ..audio_processing.segmenter import segment_audio, get_audio_duration_sec

logger = logging.getLogger(__name__)

# 支持的视频/音频/文档扩展名
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}
DOCUMENT_EXTENSIONS = {".pdf", ".pptx"}


def _lazy_import_asr_engine():
    """惰性导入 ASR 引擎（依赖 faster_whisper，可能未安装）。"""
    from ..asr_pipeline import whisper_runner as mod
    return mod


def _lazy_import_text_refiner():
    """惰性导入文本精修器（依赖 requests + LLM API）。"""
    from ..text_cleaning import cleaner as mod
    return mod


def _lazy_import_pdf_processor():
    """惰性导入文档处理器（依赖 pdfplumber/PyMuPDF）。"""
    from ..doc_processing import pdf_parser as mod
    return mod


def _classify_source(source_path: str) -> str:
    """根据扩展名分类文件类型：video / audio / document / unknown"""
    ext = os.path.splitext(source_path)[1].lower()
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in DOCUMENT_EXTENSIONS:
        return "document"
    return "unknown"


def _transcribe_with_segmentation(
    audio_path: str,
    transcript_id: str,
    teacher_id: str,
    source_filename: str,
    asr_config: dict,
    segment_config: dict,
    tmp_dir: str,
) -> dict:
    """对音频执行 ASR 转写，必要时先切分长音频防止 Whisper OOM。"""
    segment_max = segment_config.get("segment_max_duration_sec", 1800)

    try:
        duration = get_audio_duration_sec(audio_path)
    except Exception:
        duration = 0.0

    if duration <= segment_max:
        asr_engine = _lazy_import_asr_engine()
        return asr_engine.transcribe_audio(
            audio_path, transcript_id, teacher_id,
            source_filename, config=asr_config,
        )

    logger.info(f"音频过长 ({duration:.0f}s)，按 {segment_max}s 切分")
    seg_dir = os.path.join(tmp_dir, f"segments_{transcript_id}")
    segment_paths = segment_audio(
        audio_path, seg_dir, max_duration_sec=segment_max,
    )

    asr_engine = _lazy_import_asr_engine()
    all_segments = []
    combined_result = None
    time_offset = 0.0
    total_low_conf = 0
    all_confidences = []

    for i, seg_path in enumerate(segment_paths):
        logger.info(f"转写分段 {i + 1}/{len(segment_paths)}: {os.path.basename(seg_path)}")
        seg_result = asr_engine.transcribe_audio(
            seg_path, transcript_id, teacher_id,
            source_filename, config=asr_config,
        )

        for s in seg_result["segments"]:
            s["start"] = round(s["start"] + time_offset, 2)
            s["end"] = round(s["end"] + time_offset, 2)
            s["segment_id"] = f"seg_{len(all_segments) + 1:04d}"
            all_segments.append(s)
            if "confidence" in s:
                all_confidences.append(s["confidence"])
                if s["confidence"] < 0.7:
                    total_low_conf += 1

        if combined_result is None:
            combined_result = seg_result

        try:
            seg_dur = get_audio_duration_sec(seg_path)
        except Exception:
            seg_dur = segment_max
        time_offset += seg_dur

    if combined_result is None:
        raise RuntimeError("所有分段转写均失败")

    combined_result["segments"] = all_segments
    avg_conf = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0
    combined_result["asr_quality"] = {
        "estimated_cer": round(max(0.0, min(1.0, 1.0 - avg_conf)), 4),
        "low_confidence_segments": total_low_conf,
    }

    logger.info(
        f"分段合并完成: {len(all_segments)} 段, "
        f"总偏移 {time_offset:.1f}s"
    )
    return combined_result


def _process_video(
    video_path: str,
    transcript_id: str,
    teacher_id: str,
    teacher_dirs: dict[str, str],
    config: dict,
) -> dict:
    """处理单个视频文件：提取音频 → 转写 → 可选精修 → 保存样本"""
    source_filename = os.path.basename(video_path)

    # Step 1: 提取音频
    tmp_audio = os.path.join(
        teacher_dirs["uploads"], f"_tmp_{transcript_id}.wav"
    )
    try:
        extract_audio_from_video(video_path, tmp_audio)
    except ImportError as e:
        return {"status": "failed", "source": video_path, "error": str(e)}

    # Step 2: ASR 转写（自动处理长音频切分）
    try:
        asr_config_raw = {k: v for k, v in config.items()
                        if k.startswith("asr_")}
        asr_config = {k[4:]: v for k, v in asr_config_raw.items()}
        segment_config = {
            "segment_max_duration_sec": config.get("segment_max_duration_sec", 1800),
        }
        transcript = _transcribe_with_segmentation(
            tmp_audio, transcript_id, teacher_id,
            source_filename, asr_config, segment_config,
            teacher_dirs["uploads"],
        )
    except ImportError as e:
        _cleanup_tmp(tmp_audio)
        return {"status": "failed", "source": video_path, "error": str(e)}
    except Exception as e:
        _cleanup_tmp(tmp_audio)
        return {"status": "failed", "source": video_path, "error": str(e)}

    # Step 3: 保存音频样本
    sample_path = ""
    if config.get("save_audio_samples", True):
        sample_filename = f"{transcript_id}.wav"
        sample_path = os.path.join(
            teacher_dirs["audio_samples"], sample_filename
        )
        try:
            save_audio_sample(tmp_audio, sample_path)
        except Exception as e:
            logger.warning(f"保存音频样本失败: {e}")

    # Step 4: 写入 transcript JSON
    transcript_path = os.path.join(
        teacher_dirs["transcripts"], f"{transcript_id}.json"
    )
    file_manager.atomic_write_json(transcript_path, transcript)

    # Step 5: 可选 LLM 精修
    refined_path = ""
    if config.get("enable_refine"):
        try:
            text_refiner = _lazy_import_text_refiner()
            ref_config = {
                "api_url": config.get("refine_api_url",
                                      "http://localhost:8000/v1/chat/completions"),
                "model": config.get("refine_model", "qwen-32b"),
                "max_workers": config.get("refine_workers", 5),
                "api_key": config.get("refine_api_key"),
            }
            refined_output = os.path.join(
                teacher_dirs["transcripts"],
                f"{transcript_id}_refined.json",
            )
            ref_result = text_refiner.refine_transcript(
                transcript_path, refined_output, config=ref_config
            )
            if ref_result.get("status") == "success":
                refined_path = refined_output
        except ImportError:
            logger.warning("精修跳过: requests 不可用")
        except Exception as e:
            logger.warning(f"精修失败: {e}")

    _cleanup_tmp(tmp_audio)

    duration_sec = 0.0
    if transcript.get("segments"):
        segs = transcript["segments"]
        duration_sec = round(segs[-1]["end"] - segs[0]["start"], 1)

    return {
        "status": "success",
        "source": video_path,
        "transcript_id": transcript_id,
        "transcript_path": transcript_path,
        "refined_path": refined_path if refined_path else None,
        "segments_count": len(transcript.get("segments", [])),
        "duration_sec": duration_sec,
        "audio_sample_path": sample_path if sample_path else None,
    }


def _process_audio(
    audio_path: str,
    transcript_id: str,
    teacher_id: str,
    teacher_dirs: dict[str, str],
    config: dict,
) -> dict:
    """处理单个音频文件：直接转写 → 可选精修 → 保存样本"""
    source_filename = os.path.basename(audio_path)

    try:
        asr_config_raw = {k[4:]: v for k, v in config.items() if k.startswith("asr_")}
        asr_config = asr_config_raw
        segment_config = {
            "segment_max_duration_sec": config.get("segment_max_duration_sec", 1800),
        }
        transcript = _transcribe_with_segmentation(
            audio_path, transcript_id, teacher_id,
            source_filename, asr_config, segment_config,
            teacher_dirs["uploads"],
        )
    except ImportError as e:
        return {"status": "failed", "source": audio_path, "error": str(e)}
    except Exception as e:
        return {"status": "failed", "source": audio_path, "error": str(e)}

    sample_path = ""
    if config.get("save_audio_samples", True):
        sample_filename = f"{transcript_id}.wav"
        sample_path = os.path.join(
            teacher_dirs["audio_samples"], sample_filename
        )
        try:
            save_audio_sample(audio_path, sample_path)
        except Exception as e:
            logger.warning(f"保存音频样本失败: {e}")

    transcript_path = os.path.join(
        teacher_dirs["transcripts"], f"{transcript_id}.json"
    )
    file_manager.atomic_write_json(transcript_path, transcript)

    refined_path = ""
    if config.get("enable_refine"):
        try:
            text_refiner = _lazy_import_text_refiner()
            ref_config = {
                "api_url": config.get("refine_api_url",
                                      "http://localhost:8000/v1/chat/completions"),
                "model": config.get("refine_model", "qwen-32b"),
                "max_workers": config.get("refine_workers", 5),
                "api_key": config.get("refine_api_key"),
            }
            refined_output = os.path.join(
                teacher_dirs["transcripts"],
                f"{transcript_id}_refined.json",
            )
            ref_result = text_refiner.refine_transcript(
                transcript_path, refined_output, config=ref_config
            )
            if ref_result.get("status") == "success":
                refined_path = refined_output
        except Exception as e:
            logger.warning(f"精修失败: {e}")

    duration_sec = 0.0
    if transcript.get("segments"):
        segs = transcript["segments"]
        duration_sec = round(segs[-1]["end"] - segs[0]["start"], 1)

    return {
        "status": "success",
        "source": audio_path,
        "transcript_id": transcript_id,
        "transcript_path": transcript_path,
        "refined_path": refined_path if refined_path else None,
        "segments_count": len(transcript.get("segments", [])),
        "duration_sec": duration_sec,
        "audio_sample_path": sample_path if sample_path else None,
    }


def _process_document(
    doc_path: str,
    transcript_id: str,
    teacher_id: str,
    teacher_dirs: dict[str, str],
    config: dict,
) -> dict:
    """处理单个文档文件（PDF/PPTX）：提取文本 → 写入 transcript"""
    source_filename = os.path.basename(doc_path)
    try:
        pdf_processor = _lazy_import_pdf_processor()
        doc_config = {
            "backend": config.get("doc_backend", "auto"),
            "vision_api_url": config.get("vision_api_url",
                                         "http://localhost:8000/v1/chat/completions"),
            "vision_model": config.get("vision_model", "Qwen2.5-VL-7B"),
            "vision_dpi": config.get("vision_dpi", 200),
            "vision_batch_size": config.get("vision_batch_size", 1),
            "vision_prompt": config.get("vision_prompt"),
        }
        result = pdf_processor.extract_document_text(
            doc_path, teacher_id, source_filename, doc_config,
        )
        result["transcript_id"] = transcript_id
    except ImportError as e:
        return {"status": "failed", "source": doc_path, "error": str(e)}
    except Exception as e:
        return {"status": "failed", "source": doc_path, "error": str(e)}

    transcript_path = os.path.join(
        teacher_dirs["transcripts"], f"{transcript_id}.json"
    )
    file_manager.atomic_write_json(transcript_path, result)

    return {
        "status": "success",
        "source": doc_path,
        "transcript_id": transcript_id,
        "transcript_path": transcript_path,
        "refined_path": None,
        "segments_count": len(result.get("segments", [])),
        "duration_sec": 0.0,
        "audio_sample_path": None,
        "source_type": result.get("source_type", "document"),
    }


def _cleanup_tmp(path: str) -> None:
    """安全删除临时文件。"""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def ingest_teacher_material(
    teacher_id: str,
    source_paths: list[str],
    output_dir: str,
    config: dict | None = None,
) -> dict:
    """教师素材摄取主入口。

    处理流程：
    1. 生成 upload_id，创建多租户目录结构
    2. 将源文件复制到 uploads/{upload_id}/ 目录
    3. 逐个处理源文件（video→提取音频→ASR, audio→ASR, pdf→文本提取）
    4. 可选 LLM 精修、可选音频样本保留
    5. 返回带 status 字段的结果 dict

    Args:
        teacher_id: 教师 ID，如 T_20260515_001
        source_paths: 源文件路径列表（视频/音频/PDF）
        output_dir: 输出根目录，推荐 "data/teachers/{teacher_id}"
        config: 可选配置字典：
            - language: str = "zh"
            - enable_refine: bool = False
            - save_audio_samples: bool = True
            - segment_max_duration_sec: int = 1800
            - refine_api_url / refine_model / refine_workers
            - asr_model / asr_device / asr_compute_type / asr_cpu_threads
            - doc_backend / vision_api_url / vision_model / vision_dpi

    Returns:
        {"status": "success|partial|error", "message": "...", "upload_id": "...",
         "transcripts": [...], "audio_samples": [...], "stats": {...}, "warnings": [...]}
    """
    cfg = {
        "language": "zh",
        "enable_refine": False,
        "save_audio_samples": True,
        "segment_max_duration_sec": 1800,
        "refine_api_url": "http://localhost:8000/v1/chat/completions",
        "refine_model": "qwen-32b",
        "refine_workers": 5,
        "asr_model": "large-v3",
        "asr_device": "cuda",
        "asr_compute_type": "float16",
        "asr_cpu_threads": 16,
        "asr_cache_dir": None,
        "doc_backend": "auto",
        "vision_api_url": "http://localhost:8000/v1/chat/completions",
        "vision_model": "Qwen2.5-VL-7B",
        "vision_dpi": 200,
        "vision_batch_size": 1,
        "vision_prompt": None,
    }
    if config:
        cfg.update(config)

    if not source_paths:
        return {
            "status": "error",
            "message": "source_paths 为空",
            "upload_id": None,
            "teacher_id": teacher_id,
            "transcripts": [],
            "audio_samples": [],
            "total_source_files": 0,
            "succeeded": 0,
            "failed_count": 0,
            "failed": [],
        }

    upload_id = file_manager.generate_upload_id()
    teacher_dirs = file_manager.setup_teacher_dirs(
        teacher_id, upload_id,
        base_dir=os.path.dirname(output_dir.rstrip("/\\")) or "data",
    )
    teacher_dirs["root"] = output_dir
    teacher_dirs["transcripts"] = os.path.join(output_dir, "transcripts")
    teacher_dirs["audio_samples"] = os.path.join(output_dir, "audio_samples")
    teacher_dirs["uploads"] = os.path.join(output_dir, "uploads", upload_id)
    os.makedirs(teacher_dirs["transcripts"], exist_ok=True)
    os.makedirs(teacher_dirs["audio_samples"], exist_ok=True)
    os.makedirs(teacher_dirs["uploads"], exist_ok=True)

    logger.info(
        f"开始摄取: teacher_id={teacher_id}, upload_id={upload_id}, "
        f"文件数={len(source_paths)}"
    )

    for src in source_paths:
        if os.path.exists(src):
            dst = os.path.join(
                teacher_dirs["uploads"], os.path.basename(src)
            )
            shutil.copy2(src, dst)

    transcripts = []
    audio_samples = []
    failed = []
    seq = 0

    for src in source_paths:
        if not os.path.exists(src):
            failed.append({"source": src, "error": f"文件不存在: {src}"})
            continue

        file_type = _classify_source(src)
        if file_type == "unknown":
            failed.append({
                "source": src,
                "error": f"不支持的文件类型: {os.path.splitext(src)[1]}",
            })
            continue

        seq += 1
        transcript_id = file_manager.generate_transcript_id(teacher_id, seq)

        logger.info(f"[{seq}/{len(source_paths)}] 处理: {os.path.basename(src)} "
                     f"type={file_type} -> {transcript_id}")

        try:
            if file_type == "video":
                item = _process_video(src, transcript_id, teacher_id, teacher_dirs, cfg)
            elif file_type == "audio":
                item = _process_audio(src, transcript_id, teacher_id, teacher_dirs, cfg)
            elif file_type == "document":
                item = _process_document(src, transcript_id, teacher_id, teacher_dirs, cfg)
            else:
                item = {"status": "failed", "source": src,
                        "error": f"不支持的类型: {file_type}"}
        except Exception as e:
            item = {"status": "failed", "source": src, "error": str(e)}
            logger.error(f"处理异常: {src}: {e}")

        if item.get("status") == "success":
            transcripts.append(item)
            if item.get("audio_sample_path"):
                audio_samples.append(item["audio_sample_path"])
        else:
            failed.append(item)

    # 汇总结果
    if not failed:
        overall_status = "success"
        status_message = "全部处理成功"
    elif not transcripts:
        overall_status = "error"
        status_message = f"全部 {len(failed)} 个文件处理失败"
    else:
        overall_status = "partial"
        status_message = f"部分成功: {len(transcripts)} 个, 失败: {len(failed)} 个"

    # 计算 stats
    warnings_list = []
    total_duration = 0.0
    total_segments = 0
    for t in transcripts:
        total_duration += t.get("duration_sec", 0.0)
        total_segments += t.get("segments_count", 0)
    avg_seg_dur = round(total_duration / total_segments, 1) if total_segments > 0 else 0.0

    cer_values = []
    for t in transcripts:
        tp = t.get("transcript_path", "")
        if tp and os.path.exists(tp):
            try:
                with open(tp, "r", encoding="utf-8") as f:
                    tj = json.load(f)
                aq = tj.get("asr_quality", {})
                if "estimated_cer" in aq:
                    cer_values.append(aq["estimated_cer"])
            except Exception:
                pass
    avg_cer = round(sum(cer_values) / len(cer_values), 4) if cer_values else 0.0

    stats = {
        "total_duration_sec": round(total_duration, 1),
        "segments_count": total_segments,
        "avg_segment_duration_sec": avg_seg_dur,
        "estimated_cer": avg_cer,
    }

    if not transcripts and not failed:
        warnings_list.append("无有效文件被处理")
    for f_item in failed:
        if "不支持" in str(f_item.get("error", "")):
            warnings_list.append(f"跳过不支持的文件: {f_item.get('source', 'unknown')}")

    result = {
        "status": overall_status,
        "message": status_message,
        "upload_id": upload_id,
        "teacher_id": teacher_id,
        "teacher_dirs": teacher_dirs,
        "transcripts": transcripts,
        "audio_samples": audio_samples,
        "stats": stats,
        "warnings": warnings_list,
        "total_source_files": len(source_paths),
        "succeeded": len(transcripts),
        "failed_count": len(failed),
        "failed": failed if failed else [],
    }

    logger.info(
        f"摄取完成: status={overall_status}, "
        f"succeeded={len(transcripts)}, failed={len(failed)}, "
        f"total_duration={stats['total_duration_sec']}s, "
        f"segments={stats['segments_count']}"
    )
    return result


# ============================================================
# 本地测试入口
# ============================================================
if __name__ == "__main__":
    import tempfile

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    print("=== ingest orchestrator unit tests ===\n")

    tmp_dir = tempfile.mkdtemp()
    test_output_dir = os.path.join(tmp_dir, "teachers", "T_TEST_001")

    import wave
    import struct
    test_wav = os.path.join(tmp_dir, "test_lecture.wav")
    with wave.open(test_wav, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        for _ in range(16000 * 2):
            wf.writeframes(struct.pack('<h', 0))

    # 测试 1：source_paths 为空
    result = ingest_teacher_material("T_TEST_001", [], test_output_dir)
    assert result["status"] == "error", f"空输入应返回 error: {result}"
    print(f"[OK] 空 source_paths -> status=error: {result['message']}")

    # 测试 2：不存在的文件
    result = ingest_teacher_material(
        "T_TEST_001", ["nonexistent_file.mp4"], test_output_dir,
    )
    assert result["status"] == "error"
    assert result["failed_count"] == 1
    print(f"[OK] 不存在的文件 -> status=error, failed_count=1")

    # 测试 3：不支持的文件类型
    result = ingest_teacher_material(
        "T_TEST_001", [test_wav.replace(".wav", ".xyz")], test_output_dir,
    )
    print(f"[OK] 不支持类型测试 -> status={result['status']}")

    # 测试 4：WAV 文件处理
    result = ingest_teacher_material(
        "T_TEST_001", [test_wav], test_output_dir,
        config={"save_audio_samples": True, "enable_refine": False},
    )
    print(f"[OK] WAV 处理 -> status={result['status']}, "
          f"succeeded={result['succeeded']}, failed={result['failed_count']}")
    if result["transcripts"]:
        t = result["transcripts"][0]
        print(f"     transcript_id={t.get('transcript_id')}")
    if result["audio_samples"]:
        print(f"     audio_samples={result['audio_samples']}")

    expected_dirs = ["transcripts", "audio_samples", "uploads"]
    for d in expected_dirs:
        full = os.path.join(test_output_dir, d)
        if os.path.isdir(full):
            print(f"[OK] 目录已创建: {full}")

    assert result["upload_id"].startswith("UP_"), "upload_id 格式错误"
    print(f"[OK] upload_id={result['upload_id']}")

    import shutil as _shutil
    _shutil.rmtree(tmp_dir, ignore_errors=True)
    print("\n[PASS] orchestrator tests passed")
