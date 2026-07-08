"""M1 视觉提取测试：PPTX/PDF → 图片 → VLM → LaTeX 文本

使用前请先启动 vLLM:
    vllm serve Qwen/Qwen2.5-VL-7B-Instruct --host 0.0.0.0 --port 8000
        --max-model-len 8192 --gpu-memory-utilization 0.85

然后运行本脚本:
    python scripts/M1_Ingest/test_vision.py
    python scripts/M1_Ingest/test_vision.py --source test/1.2.1.pptx --dpi 150
"""

import sys
import os
import time
import argparse
import logging
import json

_this_dir = os.path.dirname(os.path.abspath(__file__))
# _this_dir = modules/M1_ingest/tests/ → 上 3 层到项目根
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(_this_dir)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("test_vision")

from modules.M1_ingest.doc_processing.pdf_parser import (
    extract_document_text,
    _render_document_to_images,
    _check_libreoffice,
    _check_vlm,
)


def main():
    parser = argparse.ArgumentParser(description="M1 Vision Extraction Test")
    parser.add_argument("--source", type=str, required=True,
                       help="文档路径 (.pdf 或 .pptx)")
    parser.add_argument("--api_url", type=str,
                       default="http://localhost:8000/v1/chat/completions",
                       help="VLM API 地址")
    parser.add_argument("--model", type=str,
                       default="Qwen2.5-VL-7B",
                       help="VLM 模型名称")
    parser.add_argument("--dpi", type=int, default=200,
                       help="渲染分辨率")
    parser.add_argument("--output", type=str, default=None,
                       help="输出 JSON 文件路径")
    parser.add_argument("--render_only", action="store_true",
                       help="仅渲染图片，不调用 VLM")
    args = parser.parse_args()

    source_path = args.source
    if not os.path.exists(source_path):
        logger.error(f"文件不存在: {source_path}")
        sys.exit(1)

    logger.info(f"文件: {source_path} ({os.path.getsize(source_path)/1024:.0f}KB)")
    logger.info(f"VLM API: {args.api_url}")
    logger.info(f"模型: {args.model}")

    # 检查依赖
    if not _check_vlm():
        logger.error("缺少 requests 库: pip install requests")
        sys.exit(1)

    lo_ok = _check_libreoffice()
    if lo_ok:
        logger.info("LibreOffice: 已就绪")
    else:
        logger.info("LibreOffice: 未安装 (将使用手动渲染，建议安装 LibreOffice)")

    if args.render_only:
        # 仅测试渲染阶段
        import tempfile
        tmp_dir = tempfile.mkdtemp(prefix="vision_test_")
        logger.info(f"渲染到: {tmp_dir}")
        images = _render_document_to_images(source_path, tmp_dir, dpi=args.dpi)
        logger.info(f"渲染完成: {len(images)} 张图片")
        for img in images:
            logger.info(f"  {img} ({os.path.getsize(img)/1024:.0f}KB)")
        print(f"\n图片已生成到: {tmp_dir}")
        return

    # 完整流程：渲染 + VLM 提取
    t0 = time.time()
    result = extract_document_text(source_path, config={
        "backend": "vision",
        "vision_api_url": args.api_url,
        "vision_model": args.model,
        "vision_dpi": args.dpi,
        "vision_batch_size": 1,  # 单页逐张发送
    })
    elapsed = time.time() - t0

    print(f"\n{'='*60}")
    print(f"视觉提取结果")
    print(f"{'='*60}")
    print(f"耗时: {elapsed:.1f}s ({elapsed/60:.1f}min)")
    print(f"类型: {result['source_type']}")
    print(f"页数: {result['total_pages']}")
    print(f"段落数: {len(result['segments'])}")
    print(f"总字符数: {sum(len(s['text']) for s in result['segments'])}")

    # 检查 LaTeX 公式覆盖率（支持 \(...\)、\[...\]、$...$、$$...$$）
    latex_count = 0
    for seg in result["segments"]:
        text = seg["text"]
        if "$" in text or r"\(" in text or r"\[" in text:
            latex_count += 1
    print(f"含公式段落: {latex_count}/{len(result['segments'])}")

    # 输出前几段预览
    print(f"\n--- 内容预览 (前5段) ---")
    for seg in result["segments"][:5]:
        text_preview = seg["text"][:200]
        if len(seg["text"]) > 200:
            text_preview += "..."
        print(f"\n[Page {seg['page']}] {text_preview}")

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存: {args.output}")


if __name__ == "__main__":
    main()
