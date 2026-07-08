"""
M1 Ingest 命令行测试入口。

用法示例：
    # 单文件测试
    python -m modules.M1_ingest.run --teacher_id T_test_001 \\
        --source ./test_data/lecture1.mp4 \\
        --output ./test_output/teachers/T_test_001

    # 多文件 + 精修
    python -m modules.M1_ingest.run --teacher_id T_test_001 \\
        --source ./videos/lecture1.mp4 ./handouts/slides.pdf \\
        --output ./test_output/teachers/T_test_001 \\
        --refine --refine_api http://localhost:8000/v1/chat/completions

    # 从目录批量摄取
    python -m modules.M1_ingest.run --teacher_id T_test_001 \\
        --source_dir ./videos/ --output ./test_output/teachers/T_test_001
"""

import os
import sys
import json
import argparse
import logging
from glob import glob

# 确保项目根目录在 sys.path 中
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("M1.run")


def main():
    parser = argparse.ArgumentParser(
        description="EduNUWA M1 Ingest - 教师素材摄取工具"
    )
    parser.add_argument(
        "--teacher_id", type=str, required=True,
        help="教师 ID，如 T_20260515_001"
    )
    parser.add_argument(
        "--source", type=str, nargs="+", default=[],
        help="源文件路径列表（视频/音频/PDF/PPTX）"
    )
    parser.add_argument(
        "--source_dir", type=str, default=None,
        help="源文件目录（将扫描目录下所有 mp4/wav/mp3/pdf/pptx 文件）"
    )
    parser.add_argument(
        "--output", type=str, required=True,
        help="输出根目录，推荐 data/teachers/{teacher_id}"
    )
    parser.add_argument(
        "--refine", action="store_true", default=False,
        help="启用 LLM 文本精修"
    )
    parser.add_argument(
        "--refine_api", type=str,
        default="http://localhost:8000/v1/chat/completions",
        help="LLM 精修 API 地址"
    )
    parser.add_argument(
        "--refine_model", type=str, default="qwen-32b",
        help="LLM 精修模型名称"
    )
    parser.add_argument(
        "--refine_workers", type=int, default=5,
        help="LLM 精修并发线程数"
    )
    parser.add_argument(
        "--no_audio_samples", action="store_true", default=False,
        help="不保留音频样本"
    )
    parser.add_argument(
        "--asr_model", type=str, default="large-v3",
        help="Whisper 模型大小"
    )
    parser.add_argument(
        "--asr_device", type=str, default="cuda",
        help="Whisper 推理设备 (cuda/cpu)"
    )
    parser.add_argument(
        "--asr_cache_dir", type=str, default=None,
        help="Whisper 模型缓存目录（默认使用 HF_HUB_CACHE 或 ~/.cache/huggingface）"
    )
    parser.add_argument(
        "--doc_backend", type=str, default="auto",
        choices=["auto", "vision", "pdfplumber", "fitz", "PyPDF2"],
        help="文档提取后端: auto=自动, vision=VLM 视觉提取（含 LaTeX 公式）"
    )
    parser.add_argument(
        "--vision_api", type=str,
        default="http://localhost:8000/v1/chat/completions",
        help="VLM API 地址（doc_backend=vision 时使用）"
    )
    parser.add_argument(
        "--vision_model", type=str, default="Qwen2.5-VL-7B",
        help="VLM 模型名称"
    )
    parser.add_argument(
        "--vision_dpi", type=int, default=200,
        help="文档渲染分辨率（DPI）"
    )
    parser.add_argument(
        "--json_output", type=str, default=None,
        help="将结果 JSON 写入指定文件"
    )

    args = parser.parse_args()

    # 收集源文件
    source_paths = list(args.source)
    if args.source_dir:
        for ext in ["*.mp4", "*.mkv", "*.mov", "*.avi",
                     "*.wav", "*.mp3", "*.m4a", "*.flac",
                     "*.pdf", "*.pptx"]:
            source_paths.extend(
                glob(os.path.join(args.source_dir, "**", ext),
                     recursive=True)
            )

    if not source_paths:
        logger.error("未指定源文件（--source 或 --source_dir）")
        sys.exit(1)

    logger.info(f"教师 ID: {args.teacher_id}")
    logger.info(f"源文件数: {len(source_paths)}")
    logger.info(f"输出目录: {args.output}")
    logger.info(f"LLM 精修: {'启用' if args.refine else '关闭'}")

    from modules.M1_ingest import ingest_teacher_material

    result = ingest_teacher_material(
        teacher_id=args.teacher_id,
        source_paths=source_paths,
        output_dir=args.output,
        config={
            "enable_refine": args.refine,
            "refine_api_url": args.refine_api,
            "refine_model": args.refine_model,
            "refine_workers": args.refine_workers,
            "save_audio_samples": not args.no_audio_samples,
            "asr_model": args.asr_model,
            "asr_device": args.asr_device,
            "asr_cache_dir": args.asr_cache_dir,
            "doc_backend": args.doc_backend,
            "vision_api_url": args.vision_api,
            "vision_model": args.vision_model,
            "vision_dpi": args.vision_dpi,
        },
    )

    print("\n" + "=" * 60)
    print(f"摄取结果: {result['status']}")
    print(f"upload_id: {result['upload_id']}")
    print(f"成功: {result['succeeded']} / 总数: {result['total_source_files']}")
    print(f"失败: {result['failed_count']}")
    print(f"音频样本: {len(result['audio_samples'])}")

    if result.get("stats"):
        s = result["stats"]
        print(f"总时长: {s.get('total_duration_sec', 0)}s, "
              f"段落数: {s.get('segments_count', 0)}, "
              f"est.CER: {s.get('estimated_cer', 0)}")

    if result["transcripts"]:
        print("\nTranscripts:")
        for t in result["transcripts"]:
            print(f"  - {t['transcript_id']}: {t['segments_count']} segments, "
                  f"{t.get('duration_sec', 0)}s")
            if t.get("refined_path"):
                print(f"    精修版: {t['refined_path']}")

    if result.get("failed"):
        print("\nFailed:")
        for f in result["failed"]:
            print(f"  - {f['source']}: {f.get('error', 'unknown')}")

    if args.json_output:
        os.makedirs(os.path.dirname(args.json_output) or ".", exist_ok=True)
        with open(args.json_output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n结果已写入: {args.json_output}")


if __name__ == "__main__":
    main()
