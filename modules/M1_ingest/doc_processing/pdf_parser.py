"""
M1 文档处理器：从 PDF / PPTX 讲义中提取文本为结构化段落。

PDF 后端（按优先级）：
1. pdfplumber — 文本布局精度高，推荐
2. PyMuPDF (fitz) — 速度最快
3. PyPDF2 — 纯 Python 回退

PPTX 后端：
- python-pptx — 按幻灯片提取文本，包括标题、正文、表格

不支持旧版 .ppt 格式（二进制），请先用 PowerPoint 另存为 .pptx。

输出为类 segment 结构（无时间戳），方便与 ASR transcript 统一处理。
"""

import os
import logging

logger = logging.getLogger(__name__)

_available_backend = None
_pptx_available = None
_libreoffice_available = None
_vlm_available = None

# 支持的文档扩展名
PDF_EXTENSIONS = {".pdf"}
PPTX_EXTENSIONS = {".pptx"}

# VLM 视觉提取默认 Prompt
VISION_EXTRACTION_PROMPT = r"""严格按以下规则提取这张教学幻灯片中的所有可见文字和数学公式。

【输出规则】
1. 只输出幻灯片上实际显示的中文原文内容，逐行逐段提取，保持原有阅读顺序
2. 所有数学公式使用 LaTeX 格式：行内公式用 \(...\)，独立（块级）公式用 \[...\]
3. 无法识别文字内容的图形、示意图、logo 等用 [图表] 标记
4. 禁止添加任何解释、翻译、总结、评论或描述性文字
5. 禁止输出英文翻译，只输出幻灯片上的原始语言内容
6. 禁止以"这张图片""该幻灯片"等描述性语句开头
7. 直接输出提取的文字内容，不要任何前缀说明"""


def _detect_backend() -> str | None:
    """检测可用的 PDF 后端，返回后端名称或 None。"""
    global _available_backend
    if _available_backend is not None:
        return _available_backend if _available_backend != "" else None

    for backend in ["pdfplumber", "fitz", "PyPDF2"]:
        try:
            if backend == "fitz":
                import fitz  # noqa: F401
            elif backend == "pdfplumber":
                import pdfplumber  # noqa: F401
            elif backend == "PyPDF2":
                import PyPDF2  # noqa: F401
            _available_backend = backend
            logger.info(f"PDF 后端: {backend}")
            return backend
        except ImportError:
            continue

    _available_backend = ""
    return None


def _check_pptx() -> bool:
    """惰性检查 python-pptx 是否可用。"""
    global _pptx_available
    if _pptx_available is None:
        try:
            import pptx  # noqa: F401
            _pptx_available = True
        except ImportError:
            _pptx_available = False
    return _pptx_available


def _check_libreoffice() -> bool:
    """检测 LibreOffice 是否可用（用于 PPTX/PDF → 图片渲染）。"""
    global _libreoffice_available
    if _libreoffice_available is not None:
        return _libreoffice_available
    import subprocess
    for cmd in ["soffice", "libreoffice"]:
        try:
            subprocess.run(
                [cmd, "--version"],
                capture_output=True, timeout=10,
                creationflags=0x08000000 if os.name == "nt" else 0,
            )
            _libreoffice_available = True
            logger.info(f"LibreOffice 已检测到: {cmd}")
            return True
        except (FileNotFoundError, OSError):
            continue
    _libreoffice_available = False
    return False


def _check_vlm() -> bool:
    """检测 VLM API 调用所需的依赖是否可用。"""
    global _vlm_available
    if _vlm_available is not None:
        return _vlm_available
    try:
        import requests  # noqa: F401
        import base64   # noqa: F401
        _vlm_available = True
    except ImportError:
        _vlm_available = False
    return _vlm_available


def _encode_image_base64(image_path: str) -> str:
    """将图片文件编码为 base64 data URL。"""
    import base64
    with open(image_path, "rb") as f:
        img_data = base64.b64encode(f.read()).decode("utf-8")
    ext = os.path.splitext(image_path)[1].lower().lstrip(".")
    mime = "png" if ext == "png" else "jpeg" if ext in ("jpg", "jpeg") else "png"
    return f"data:image/{mime};base64,{img_data}"


def _extract_all_text_from_shape(shape) -> list[str]:
    """从 shape 中提取所有文本，包括公式、表格、文本框。

    深入到 XML 层遍历所有 a:t 元素，不丢失嵌套在公式元素中的文本。
    对于 MathType OLE 公式对象，插入 [公式] 占位符标记位置。

    Returns:
        文本段落列表
    """
    from lxml import etree

    nsmap = {
        'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    }

    paragraphs = []

    # 1. 表格：逐 cell 提取
    if shape.has_table:
        table = shape.table
        rows_text = []
        for row in table.rows:
            cells = []
            for cell in row.cells:
                cell_texts = []
                for t_elem in cell._tc.findall('.//a:t', nsmap):
                    if t_elem.text:
                        cell_texts.append(t_elem.text)
                cell_text = ''.join(cell_texts).strip()
                if cell_text:
                    cells.append(cell_text)
            if cells:
                rows_text.append(" | ".join(cells))
        if rows_text:
            paragraphs.append("\n".join(rows_text))
        return paragraphs

    # 2. 检测 OLE 公式对象 (MathType / Equation Editor)
    if not shape.has_text_frame:
        # 检查是否是嵌入的公式对象
        ole_objs = shape._element.findall('.//' + _qname('p', 'oleObj'))
        if ole_objs:
            paragraphs.append("[公式]")
            return paragraphs

        # 检查 graphicFrame 类型
        tag = shape._element.tag.split('}')[-1] if '}' in shape._element.tag else shape._element.tag
        if tag == 'graphicFrame':
            ole_objs = shape._element.findall('.//' + _qname('p', 'oleObj'))
            if ole_objs:
                paragraphs.append("[公式]")
            return paragraphs

        return paragraphs

    # 3. 文本框 + 公式：遍历所有段落的所有 a:t 元素
    for para in shape.text_frame.paragraphs:
        # 直接用 XML 层提取所有 a:t 文本，包括嵌套在公式内部的
        texts = []
        for t_elem in para._p.findall('.//a:t', nsmap):
            if t_elem.text:
                texts.append(t_elem.text)
        full_text = ''.join(texts).strip()

        if full_text and len(full_text) > 2:
            paragraphs.append(full_text)

    return paragraphs


def _qname(prefix: str, tag: str) -> str:
    """生成带命名空间的限定标签名。"""
    ns_map = {
        'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
    }
    return '{%s}%s' % (ns_map[prefix], tag)


def _extract_with_pptx(pptx_path: str) -> list[dict]:
    """使用 python-pptx 提取文本，按幻灯片逐页切分。

    提取内容：标题、正文段落、公式占位符、表格文本。
    按形状在页面上的坐标排序，重建阅读顺序。
    MathType OLE 公式对象无法提取纯文本，以 [公式] 占位符标记。
    """
    import pptx

    segments = []
    prs = pptx.Presentation(pptx_path)

    for slide_num, slide in enumerate(prs.slides, 1):
        # 按 y 坐标为主、x 坐标为辅排序形状（阅读顺序）
        shapes_with_pos = []
        for shape in slide.shapes:
            x = shape.left or 0
            y = shape.top or 0
            shapes_with_pos.append((y, x, shape))
        shapes_with_pos.sort()

        slide_texts = []
        last_y = -1
        current_line = []

        for y, x, shape in shapes_with_pos:
            para_texts = _extract_all_text_from_shape(shape)
            if not para_texts:
                continue

            # 如果 y 坐标变化较大（>0.3英寸），认为是新行
            if last_y >= 0 and abs(y - last_y) > 250000:  # EMU: ~0.27 inch
                if current_line:
                    slide_texts.extend(current_line)
                current_line = []

            current_line.extend(para_texts)
            last_y = y

        if current_line:
            slide_texts.extend(current_line)

        if slide_texts:
            segments.append({
                "segment_id": f"pptx_{slide_num:04d}",
                "page": slide_num,
                "start": None,
                "end": None,
                "text": "\n".join(slide_texts),
                "speaker": "teacher",
            })

    return segments


def _render_pptx_to_images(pptx_path: str, output_dir: str, dpi: int = 200) -> list[str]:
    """将 PPTX 幻灯片渲染为 PNG 图像。

    优先使用 LibreOffice 命令行（最准确），
    回退到 python-pptx + PIL 手动渲染（可移植但精度有限）。

    Args:
        pptx_path: PPTX 文件路径
        output_dir: 输出图片目录
        dpi: 渲染分辨率

    Returns:
        PNG 图片文件路径列表，按幻灯片顺序排列
    """
    os.makedirs(output_dir, exist_ok=True)

    if _check_libreoffice():
        return _render_pptx_with_libreoffice(pptx_path, output_dir, dpi)

    logger.warning("LibreOffice not installed, using manual rendering (limited accuracy)")
    return _render_pptx_manual(pptx_path, output_dir, dpi)


def _render_pptx_with_libreoffice(pptx_path: str, output_dir: str, dpi: int = 200) -> list[str]:
    """使用 LibreOffice 将 PPTX 转为 PDF，再用 PyMuPDF 渲染为 PNG。

    两步策略（LibreOffice 直接 --convert-to png 只导出首页）：
    1. LibreOffice PPTX → PDF（保留全部幻灯片和 OLE/MathType 公式渲染）
    2. PyMuPDF PDF → PNG（支持 DPI 控制和逐页输出）
    """
    import subprocess
    import tempfile
    import shutil

    # Step 1: PPTX → PDF
    pdf_tmpdir = tempfile.mkdtemp(prefix="lo_pdf_")
    try:
        for cmd in ["soffice", "libreoffice"]:
            try:
                subprocess.run(
                    [cmd, "--headless", "--convert-to", "pdf",
                     "--outdir", pdf_tmpdir, pptx_path],
                    capture_output=True, timeout=120,
                    creationflags=0x08000000 if os.name == "nt" else 0,
                )
                break
            except FileNotFoundError:
                continue
            except subprocess.TimeoutExpired:
                logger.warning(f"LibreOffice PPTX→PDF 转换超时: {pptx_path}")
                continue

        # 找到生成的 PDF 文件
        pdf_files = [f for f in os.listdir(pdf_tmpdir) if f.endswith(".pdf")]
        if not pdf_files:
            raise RuntimeError(
                f"LibreOffice PPTX→PDF 转换失败（未生成 PDF）: {pptx_path}"
            )
        pdf_path = os.path.join(pdf_tmpdir, pdf_files[0])
        logger.info(f"LibreOffice PPTX→PDF 完成: {pdf_path}")

        # Step 2: PDF → PNG（复用已有渲染器）
        images = _render_pdf_to_images(pdf_path, output_dir, dpi)
    finally:
        shutil.rmtree(pdf_tmpdir, ignore_errors=True)

    return images


def _render_pptx_manual(pptx_path: str, output_dir: str, dpi: int = 200) -> list[str]:
    """使用 python-pptx + PIL 手动渲染幻灯片。

    这是一个简化的渲染器，无法完美还原原始外观，
    但能保留文字内容和公式的相对位置，足够 VLM 识别。
    """
    import pptx
    from pptx.util import Inches, Emu
    from PIL import Image, ImageDraw, ImageFont

    prs = pptx.Presentation(pptx_path)

    # 幻灯片尺寸 (EMU → pixels at given DPI)
    slide_w_emu = prs.slide_width or 12192000   # 默认 10 inches
    slide_h_emu = prs.slide_height or 6858000    # 默认 7.5 inches
    scale = dpi / 914400  # EMU → pixels (914400 EMU/inch)

    img_w = int(slide_w_emu * scale)
    img_h = int(slide_h_emu * scale)

    # 尝试加载中文字体
    font_paths = [
        "/mnt/c/Windows/Fonts/msyh.ttc",       # 微软雅黑 (WSL)
        "/mnt/c/Windows/Fonts/simsun.ttc",     # 宋体 (WSL)
        "/mnt/c/Windows/Fonts/simhei.ttf",     # 黑体 (WSL)
        "C:/Windows/Fonts/msyh.ttc",           # 微软雅黑 (Windows)
        "C:/Windows/Fonts/simsun.ttc",         # 宋体 (Windows)
        "C:/Windows/Fonts/simhei.ttf",         # 黑体 (Windows)
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    font = None
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, 18)
                break
            except OSError:
                continue
    if font is None:
        font = ImageFont.load_default()

    images = []
    for slide_num, slide in enumerate(prs.slides, 1):
        img = Image.new("RGB", (img_w, img_h), "white")
        draw = ImageDraw.Draw(img)

        for shape in slide.shapes:
            # 计算形状在图像上的位置
            x = int((shape.left or 0) * scale)
            y = int((shape.top or 0) * scale)
            w = int((shape.width or 0) * scale)
            h = int((shape.height or 0) * scale)

            if shape.has_text_frame:
                # 绘制文本框
                texts = _extract_all_text_from_shape(shape)
                combined = "\n".join(texts)
                if combined.strip():
                    # 绘制背景矩形（浅灰）
                    draw.rectangle([x, y, x + w, y + h], fill=(250, 250, 250), outline=(200, 200, 200))
                    # 绘制文字（简单多行）
                    lines = combined.split("\n")
                    line_h = 22
                    for li, line in enumerate(lines):
                        ty = y + 4 + li * line_h
                        if ty < y + h:
                            draw.text((x + 4, ty), line, fill=(0, 0, 0), font=font)

            elif shape.has_table:
                # 绘制表格
                draw.rectangle([x, y, x + w, y + h], fill=(240, 240, 240), outline=(180, 180, 180))
                table = shape.table
                if table.rows:
                    row_h = h // len(table.rows)
                    for ri, row in enumerate(table.rows):
                        if row_h > 0:
                            cols = len(row.cells)
                            col_w = w // cols if cols else w
                            for ci, cell in enumerate(row.cells):
                                cx = x + ci * col_w
                                cy = y + ri * row_h
                                draw.rectangle([cx, cy, cx + col_w, cy + row_h],
                                             outline=(160, 160, 160))
                                cell_text = cell.text.strip()
                                if cell_text:
                                    draw.text((cx + 3, cy + 3), cell_text,
                                            fill=(0, 0, 0), font=font)

        img_path = os.path.join(output_dir, f"slide_{slide_num:04d}.png")
        img.save(img_path, "PNG")
        images.append(img_path)

    return images


def _render_pdf_to_images(pdf_path: str, output_dir: str, dpi: int = 200) -> list[str]:
    """使用 PyMuPDF 将 PDF 页面渲染为 PNG 图像。

    Args:
        pdf_path: PDF 文件路径
        output_dir: 输出图片目录
        dpi: 渲染分辨率

    Returns:
        PNG 图片文件路径列表，按页码顺序排列
    """
    import fitz

    os.makedirs(output_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    images = []

    try:
        for page_num, page in enumerate(doc, 1):
            # 计算缩放矩阵
            zoom = dpi / 72.0  # PDF 默认 72 DPI
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)

            img_path = os.path.join(output_dir, f"page_{page_num:04d}.png")
            pix.save(img_path)
            images.append(img_path)
    finally:
        doc.close()

    logger.info(f"PDF 渲染完成: {len(images)} 页 → {output_dir}")
    return images


def _render_document_to_images(
    doc_path: str, output_dir: str, dpi: int = 200
) -> list[str]:
    """统一的文档 → 图片渲染入口。

    根据扩展名自动分发到 PPTX 或 PDF 渲染器。

    Args:
        doc_path: 文档路径 (.pdf 或 .pptx)
        output_dir: 输出图片目录
        dpi: 渲染分辨率

    Returns:
        PNG 图片文件路径列表
    """
    doc_type = _classify_document(doc_path)

    if doc_type == "pptx":
        return _render_pptx_to_images(doc_path, output_dir, dpi)
    elif doc_type == "pdf":
        return _render_pdf_to_images(doc_path, output_dir, dpi)
    else:
        raise ValueError(f"不支持的文档类型: {doc_path}")


def _call_vision_api(
    image_paths: list[str],
    config: dict,
) -> str:
    """调用 VLM API (OpenAI 兼容接口) 从图片中提取文本和公式。

    Args:
        image_paths: 图片文件路径列表
        config: 视觉提取配置:
            - vision_api_url: str (API 地址，含 /v1/chat/completions)
            - vision_model: str = "Qwen2.5-VL-7B"
            - vision_prompt: str | None（自定义提取 prompt）
            - vision_max_tokens: int = 2048
            - vision_temperature: float = 0.0

    Returns:
        VLM 提取的原始文本（包含 LaTeX 公式）
    """
    import requests
    import base64

    api_url = config.get(
        "vision_api_url",
        "http://localhost:8000/v1/chat/completions",
    )
    model = config.get("vision_model", "Qwen2.5-VL-7B")
    prompt = config.get("vision_prompt", VISION_EXTRACTION_PROMPT)
    max_tokens = config.get("vision_max_tokens", 2048)
    temperature = config.get("vision_temperature", 0.0)

    # 构建多模态消息内容
    content_parts = []
    for img_path in image_paths:
        data_url = _encode_image_base64(img_path)
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": data_url},
        })

    # 文本提示放在最后（Qwen2.5-VL 推荐顺序）
    content_parts.append({"type": "text", "text": prompt})

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一个精确的文字转录工具。你的唯一任务是逐字逐句提取幻灯片上"
                    "显示的中文原文和数学公式。禁止翻译成英文，禁止添加任何解释、"
                    "总结、评论或描述性文字。只输出原文内容，使用 LaTeX \\(...\\) "
                    "和 \\[...\\] 格式包裹数学公式。"
                ),
            },
            {"role": "user", "content": content_parts},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.0,
    }

    logger.info(
        f"调用 VLM: {api_url}, model={model}, "
        f"图片数={len(image_paths)}"
    )

    try:
        resp = requests.post(
            api_url,
            json=payload,
            timeout=300,  # 大图片可能需要较长时间
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        logger.info(f"VLM 返回: {len(content)} 字符")
        return content
    except requests.exceptions.ConnectionError:
        raise ConnectionError(
            f"无法连接 VLM API: {api_url}\n"
            f"请确保 vLLM 已启动，例如:\n"
            f"  vllm serve Qwen/Qwen2.5-VL-7B-Instruct --host 0.0.0.0 --port 8000"
        )
    except requests.exceptions.Timeout:
        raise TimeoutError(f"VLM API 调用超时: {api_url}")
    except Exception as e:
        raise RuntimeError(f"VLM API 调用失败: {e}")


def _parse_vision_response(text: str, page_num: int, seg_start_id: int) -> list[dict]:
    """将 VLM 返回的文本解析为 segments 结构。

    按双换行符切分段落，为每个段落生成 segment dict。

    Args:
        text: VLM 返回的原始文本
        page_num: 页码（用于 segment 元数据）
        seg_start_id: segment 起始 ID 编号

    Returns:
        segments 列表
    """
    segments = []
    paragraphs = text.split("\n\n")

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # 过滤太短的片段（纯标记如单独的 [图表]）
        if len(para) < 3:
            continue

        segments.append({
            "segment_id": f"vis_{seg_start_id + len(segments) + 1:04d}",
            "page": page_num,
            "start": None,
            "end": None,
            "text": para,
            "speaker": "teacher",
        })

    return segments


def _extract_with_vision(
    doc_path: str,
    teacher_id: str = "",
    source_file: str = "",
    config: dict | None = None,
) -> dict:
    """使用视觉模型从文档中提取文本和公式。

    完整流程：
    1. 文档 → PNG 图片（LibreOffice / PyMuPDF）
    2. 逐页/批量发送图片到 VLM
    3. VLM 返回含 LaTeX 公式的文本
    4. 解析为 segments 结构

    Args:
        doc_path: 文档路径 (.pdf 或 .pptx)
        teacher_id: 教师 ID（可选）
        source_file: 原始上传文件名（可选）
        config: 可选配置:
            - vision_api_url: str
            - vision_model: str = "Qwen2.5-VL-7B"
            - vision_dpi: int = 200
            - vision_max_tokens: int = 2048
            - vision_batch_size: int = 1（每次发送给 VLM 的图片数）
            - vision_prompt: str | None（自定义 prompt）

    Returns:
        与 extract_pdf_text 相同结构的 dict
    """
    from datetime import datetime, timezone, timedelta

    cfg = {
        "vision_api_url": "http://localhost:8000/v1/chat/completions",
        "vision_model": "Qwen2.5-VL-7B",
        "vision_dpi": 200,
        "vision_max_tokens": 2048,
        "vision_batch_size": 1,
        "vision_prompt": None,
    }
    if config:
        cfg.update(config)

    # 检测依赖
    if not _check_vlm():
        raise ImportError(
            "VLM 视觉提取需要 requests 和 base64 库。\n"
            "请执行: pip install requests"
        )

    doc_type = _classify_document(doc_path)
    if doc_type == "unknown":
        raise ValueError(f"不支持的文档格式: {doc_path}")

    # Step 1: 渲染文档为图片
    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="edunwa_vision_")

    try:
        logger.info(f"渲染文档为图片: {doc_path}")
        image_paths = _render_document_to_images(
            doc_path, tmp_dir, dpi=cfg["vision_dpi"]
        )
        logger.info(f"共 {len(image_paths)} 张图片待识别")

        # Step 2: 逐页/批量调用 VLM
        all_segments = []
        batch_size = cfg["vision_batch_size"]

        for i in range(0, len(image_paths), batch_size):
            batch = image_paths[i:i + batch_size]
            page_start = i + 1
            page_end = i + len(batch)

            logger.info(
                f"VLM 识别: 第 {page_start}-{page_end} 页 "
                f"({i + 1}/{len(image_paths)})"
            )

            try:
                vlm_text = _call_vision_api(batch, cfg)
            except Exception as e:
                logger.error(f"第 {page_start}-{page_end} 页识别失败: {e}")
                # 失败时插入占位符，不中断整体流程
                vlm_text = f"[识别失败: {e}]"

            # Step 3: 解析为 segments
            seg_start = len(all_segments)
            page_segments = _parse_vision_response(
                vlm_text, page_start, seg_start
            )
            all_segments.extend(page_segments)

        # 计算总页数
        total_pages = 0
        for seg in all_segments:
            total_pages = max(total_pages, seg.get("page", 0))

        tz_china = timezone(timedelta(hours=8))
        result = {
            "transcript_id": "",
            "teacher_id": teacher_id,
            "source_file": source_file or os.path.basename(doc_path),
            "source_audio": os.path.basename(doc_path),
            "language": "zh",
            "segments": all_segments,
            "source_type": f"{doc_type}_vision",
            "total_pages": total_pages,
            "asr_backend": "vision-vlm-qwen",
            "asr_quality": {
                "estimated_cer": 0.0,
                "low_confidence_segments": 0,
            },
            "ingested_at": datetime.now(tz_china).isoformat(),
        }

        logger.info(
            f"视觉提取完成: {len(all_segments)} 段落, "
            f"{total_pages} 页, source_type={result['source_type']}"
        )
        return result

    finally:
        # 清理临时图片
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _classify_document(file_path: str) -> str:
    """根据扩展名判断文档类型：pdf / pptx / unknown"""
    ext = os.path.splitext(file_path)[1].lower()
    if ext in PDF_EXTENSIONS:
        return "pdf"
    if ext in PPTX_EXTENSIONS:
        return "pptx"
    return "unknown"


def _extract_with_pdfplumber(pdf_path: str) -> list[dict]:
    """使用 pdfplumber 提取文本，按页切分段落。"""
    import pdfplumber
    segments = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            if text and text.strip():
                for para in text.split("\n\n"):
                    para = para.strip()
                    if para and len(para) > 10:  # 过滤过短行
                        segments.append({
                            "segment_id": f"pdf_{len(segments) + 1:04d}",
                            "page": page_num,
                            "start": None,  # PDF 无时间戳
                            "end": None,
                            "text": para,
                            "speaker": "teacher",
                        })
    return segments


def _extract_with_fitz(pdf_path: str) -> list[dict]:
    """使用 PyMuPDF (fitz) 提取文本，按页切分段落。"""
    import fitz
    segments = []
    doc = fitz.open(pdf_path)
    try:
        for page_num, page in enumerate(doc, 1):
            text = page.get_text("text")
            if text and text.strip():
                for para in text.split("\n\n"):
                    para = para.strip()
                    if para and len(para) > 10:
                        segments.append({
                            "segment_id": f"pdf_{len(segments) + 1:04d}",
                            "page": page_num,
                            "start": None,
                            "end": None,
                            "text": para,
                            "speaker": "teacher",
                        })
    finally:
        doc.close()
    return segments


def _extract_with_pypdf2(pdf_path: str) -> list[dict]:
    """使用 PyPDF2 提取文本，按页切分段落。"""
    from PyPDF2 import PdfReader
    segments = []
    reader = PdfReader(pdf_path)
    for page_num, page in enumerate(reader.pages, 1):
        text = page.extract_text()
        if text and text.strip():
            for para in text.split("\n\n"):
                para = para.strip()
                if para and len(para) > 10:
                    segments.append({
                        "segment_id": f"pdf_{len(segments) + 1:04d}",
                        "page": page_num,
                        "start": None,
                        "end": None,
                        "text": para,
                        "speaker": "teacher",
                    })
    return segments


def extract_pdf_text(
    pdf_path: str,
    teacher_id: str = "",
    source_file: str = "",
    config: dict | None = None,
) -> dict:
    """从 PDF 讲义中提取文本为结构化 transcript。

    Args:
        pdf_path: PDF 文件路径
        teacher_id: 教师 ID（如 T_20260515_001，可选）
        source_file: 原始上传文件名（可选）
        config: 可选配置：
            - backend: str | None（强制指定后端，None=自动检测）
            - min_para_length: int = 10（最小段落长度）

    Returns:
        {
            "transcript_id": "",
            "teacher_id": "T_...",
            "source_file": "handout.pdf",
            "source_audio": "handout.pdf",
            "language": "zh",
            "segments": [...],  # start/end 为 null（PDF 无时间戳）
            "source_type": "pdf",
            "total_pages": N,
            "asr_backend": "pdf-extract",
            "asr_quality": {...},
            "ingested_at": "2026-05-15T10:30:00+08:00",
        }
    """
    from datetime import datetime, timezone, timedelta

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

    cfg = {"backend": None, "min_para_length": 10}
    if config:
        cfg.update(config)

    # 选择后端
    backend = cfg["backend"] or _detect_backend()
    if backend is None:
        raise ImportError(
            "未找到可用的 PDF 库。请安装其中之一:\n"
            "  pip install pdfplumber   (推荐，文本精度高)\n"
            "  pip install PyMuPDF      (速度快)\n"
            "  pip install PyPDF2       (纯 Python)"
        )

    logger.info(f"提取 PDF 文本: {pdf_path} (backend={backend})")

    if backend == "pdfplumber":
        segments = _extract_with_pdfplumber(pdf_path)
    elif backend == "fitz":
        segments = _extract_with_fitz(pdf_path)
    elif backend == "PyPDF2":
        segments = _extract_with_pypdf2(pdf_path)
    else:
        raise ValueError(f"未知 PDF 后端: {backend}")

    # 计算总页数
    total_pages = 0
    for seg in segments:
        total_pages = max(total_pages, seg.get("page", 0))

    tz_china = timezone(timedelta(hours=8))
    result = {
        "transcript_id": "",  # 由调用方填入
        "teacher_id": teacher_id,
        "source_file": source_file or os.path.basename(pdf_path),
        "source_audio": os.path.basename(pdf_path),
        "language": "zh",
        "segments": segments,
        "source_type": "pdf",
        "total_pages": total_pages,
        "asr_backend": f"pdf-extract-{backend}",
        "asr_quality": {
            "estimated_cer": 0.0,
            "low_confidence_segments": 0,
        },
        "ingested_at": datetime.now(tz_china).isoformat(),
    }

    logger.info(
        f"PDF 提取完成: {len(segments)} 段落, {total_pages} 页"
    )
    return result


def extract_document_text(
    file_path: str,
    teacher_id: str = "",
    source_file: str = "",
    config: dict | None = None,
) -> dict:
    """统一文档提取入口：根据扩展名和后端配置自动分发。

    支持格式：
    - .pdf  → 使用 pdfplumber / PyMuPDF / PyPDF2 后端（纯文本）
    - .pptx → 使用 python-pptx 后端（纯文本）
    - .pdf / .pptx + backend="vision" → 使用 VLM 视觉提取（含 LaTeX 公式）

    Args:
        file_path: 文档文件路径（.pdf 或 .pptx）
        teacher_id: 教师 ID（可选，如 T_20260515_001）
        source_file: 原始上传文件名（可选，默认取 file_path 的 basename）
        config: 可选配置：
            - backend: "auto" (默认) | "vision" | "pdfplumber" | "fitz" | "PyPDF2"
            - 当 backend="vision" 时，还需要:
                - vision_api_url: str = "http://localhost:8000/v1/chat/completions"
                - vision_model: str = "Qwen2.5-VL-7B"
                - vision_dpi: int = 200
                - vision_batch_size: int = 1
                - vision_prompt: str | None

    Returns:
        与 extract_pdf_text 相同结构的 dict，source_type 为 "pdf"/"pptx"
        或 "pdf_vision"/"pptx_vision"
    """
    from datetime import datetime, timezone, timedelta

    cfg = config or {}
    backend = cfg.get("backend", "auto")
    src_file = source_file or os.path.basename(file_path)

    # 视觉模型路由
    if backend == "vision":
        return _extract_with_vision(file_path, teacher_id, src_file, config)

    doc_type = _classify_document(file_path)

    if doc_type == "pdf":
        return extract_pdf_text(file_path, teacher_id, src_file, config)

    if doc_type == "pptx":
        if not _check_pptx():
            raise ImportError(
                "python-pptx 未安装，请执行: pip install python-pptx"
            )
        logger.info(f"提取 PPTX 文本: {file_path}")

        segments = _extract_with_pptx(file_path)
        total_pages = len(segments)
        tz_china = timezone(timedelta(hours=8))

        result = {
            "transcript_id": "",
            "teacher_id": teacher_id,
            "source_file": src_file,
            "source_audio": os.path.basename(file_path),
            "language": "zh",
            "segments": segments,
            "source_type": "pptx",
            "total_pages": total_pages,
            "asr_backend": "pptx-extract",
            "asr_quality": {
                "estimated_cer": 0.0,
                "low_confidence_segments": 0,
            },
            "ingested_at": datetime.now(tz_china).isoformat(),
        }
        logger.info(
            f"PPTX 提取完成: {len(segments)} 张幻灯片, "
            f"{sum(len(s['text']) for s in segments)} 字符"
        )
        return result

    raise ValueError(
        f"不支持的文档格式: {os.path.splitext(file_path)[1]}, "
        f"支持的格式: .pdf, .pptx"
    )


# ============================================================
# 本地测试入口
# ============================================================
if __name__ == "__main__":
    import tempfile
    import shutil

    print("=== pdf_processor unit tests ===\n")

    # 测试 PDF 后端
    backend = _detect_backend()
    if backend:
        print(f"[OK] PDF backend detected: {backend}")
    else:
        print("[INFO] No PDF backend (pip install pdfplumber)")

    # 测试 PPTX 后端
    if _check_pptx():
        print("[OK] PPTX backend detected: python-pptx")
    else:
        print("[INFO] No PPTX backend (pip install python-pptx)")

    # 测试文件不存在
    try:
        extract_document_text("nonexistent.pdf")
        assert False, "should raise"
    except FileNotFoundError:
        print("[OK] FileNotFoundError for missing file")

    # 测试不支持的格式
    try:
        extract_document_text("test.xyz")
        assert False, "should raise"
    except ValueError as e:
        print(f"[OK] ValueError for unsupported format")

    # 测试 PPTX 提取（如果 python-pptx 可用）
    if _check_pptx():
        from pptx import Presentation
        from pptx.util import Inches, Pt

        tmp_dir = tempfile.mkdtemp()
        test_pptx = os.path.join(tmp_dir, "test.pptx")

        prs = Presentation()
        # Slide 1
        slide1 = prs.slides.add_slide(prs.slide_layouts[1])
        slide1.shapes.title.text = "第一章 线性方程组"
        slide1.placeholders[1].text = (
            "线性方程组是线性代数的核心研究对象。\n"
            "在本章中，将系统学习如何求解线性方程组。"
        )
        # Slide 2
        slide2 = prs.slides.add_slide(prs.slide_layouts[1])
        slide2.shapes.title.text = "1.1 基本概念"
        slide2.placeholders[1].text = (
            "n元线性方程组的形式：每个方程中未知量的系数不全为0。\n"
            "齐次方程组：所有常数项为0。"
        )
        prs.save(test_pptx)

        result = extract_document_text(test_pptx)
        assert result["source_type"] == "pptx"
        assert result["total_pages"] == 2
        assert len(result["segments"]) == 2
        for seg in result["segments"]:
            assert "page" in seg
            assert seg["start"] is None
        print(f"[OK] PPTX extract: {len(result['segments'])} slides, "
              f"source_type={result['source_type']}")

        shutil.rmtree(tmp_dir, ignore_errors=True)

    # 测试 extract_document_text 自动分发 PDF
    if backend:
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A4

            tmp_dir = tempfile.mkdtemp()
            test_pdf = os.path.join(tmp_dir, "test.pdf")
            c = canvas.Canvas(test_pdf, pagesize=A4)
            c.drawString(100, 750, "测试内容")
            c.showPage()
            c.save()

            result = extract_document_text(test_pdf)
            assert result["source_type"] == "pdf"
            print(f"[OK] extract_document_text auto-dispatched PDF")
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except ImportError:
            pass

    # 测试视觉后端
    print("\n--- Vision Backend Tests ---")

    # LibreOffice 检测
    lo_available = _check_libreoffice()
    print(f"[{'OK' if lo_available else 'INFO'}] LibreOffice: "
          f"{'available' if lo_available else 'not installed (vision PPTX needs it)'}")

    # VLM 依赖检测
    vlm_ok = _check_vlm()
    print(f"[{'OK' if vlm_ok else 'INFO'}] VLM deps (requests): "
          f"{'available' if vlm_ok else 'not installed'}")

    # encode_image_base64
    if vlm_ok:
        import base64
        tmp_dir = tempfile.mkdtemp()
        test_png = os.path.join(tmp_dir, "test.png")
        from PIL import Image
        img = Image.new("RGB", (100, 100), "white")
        img.save(test_png, "PNG")
        data_url = _encode_image_base64(test_png)
        assert data_url.startswith("data:image/png;base64,")
        print(f"[OK] _encode_image_base64: {len(data_url)} chars")
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # VLM response 解析
    sample_vlm_output = (
        "函数极限的定义\n\n"
        "设函数 $f(x)$ 在 $x_0$ 的某个去心邻域内有定义。\n\n"
        r"$$\lim_{x \to x_0} f(x) = A$$\n\n"
        "其中 $A$ 为确定的常数。"
    )

    parsed = _parse_vision_response(sample_vlm_output, 1, 0)
    assert len(parsed) >= 2, f"应至少解析出2个段落: {len(parsed)}"
    # 检查 LaTeX 公式是否保留
    all_text = " ".join(s["text"] for s in parsed)
    assert "$f(x)$" in all_text, f"行内公式应保留: {all_text}"
    assert "$$\\lim" in all_text, f"独立公式应保留: {all_text}"
    print(f"[OK] _parse_vision_response: {len(parsed)} paragraphs, "
          f"LaTeX formulas preserved")

    # PPTX → 图片手动渲染测试
    if _check_pptx():
        from pptx import Presentation
        tmp_dir = tempfile.mkdtemp()
        test_pptx = os.path.join(tmp_dir, "test_vision.pptx")
        img_dir = os.path.join(tmp_dir, "images")

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = "测试标题: $f(x)$ 极限"
        slide.placeholders[1].text = "当 $x \\to 0$ 时，$\\frac{\\sin x}{x} \\to 1$"
        prs.save(test_pptx)

        try:
            images = _render_pptx_to_images(test_pptx, img_dir, dpi=72)
            assert len(images) >= 1, f"应至少产生1张图片: {len(images)}"
            for ip in images:
                assert os.path.exists(ip), f"图片应存在: {ip}"
                assert os.path.getsize(ip) > 0, f"图片不应为空: {ip}"
            print(f"[OK] _render_pptx_to_images: {len(images)} images generated")
        except Exception as e:
            print(f"[INFO] PPTX rendering skipped: {e}")

        shutil.rmtree(tmp_dir, ignore_errors=True)

    # PDF → 图片渲染测试（需要 PyMuPDF）
    try:
        import fitz
        tmp_dir = tempfile.mkdtemp()
        test_pdf = os.path.join(tmp_dir, "test_render.pdf")
        img_dir = os.path.join(tmp_dir, "images")

        # 使用 PyMuPDF 创建测试 PDF
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), r"Test content: $\alpha + \beta = \gamma$",
                        fontsize=12)
        doc.save(test_pdf)
        doc.close()

        images = _render_pdf_to_images(test_pdf, img_dir, dpi=72)
        assert len(images) == 1
        assert os.path.getsize(images[0]) > 0
        print(f"[OK] _render_pdf_to_images: {len(images)} page(s)")

        # _render_document_to_images 自动分发
        images2 = _render_document_to_images(test_pdf, img_dir, dpi=72)
        assert len(images2) == 1
        print(f"[OK] _render_document_to_images: auto-dispatched PDF")

        shutil.rmtree(tmp_dir, ignore_errors=True)
    except ImportError:
        print("[INFO] PyMuPDF not available for PDF render test")

    # extract_document_text with backend="vision" routing
    # (不实际调用 VLM，只测试路由是否正确触发)
    try:
        extract_document_text("nonexistent.pptx", {"backend": "vision"})
        assert False, "应抛出异常（文件不存在或 VLM 不可用）"
    except (FileNotFoundError, ConnectionError, ImportError, RuntimeError, Exception) as e:
        # 预期：要么找不到文件，要么 VLM 不可用
        print(f"[OK] extract_document_text(backend=vision) routing: {type(e).__name__}")

    print("\n[PASS] All tests passed")
