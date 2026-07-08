"""
M1 文本规则清洗：语言层通用过滤，不依赖 LLM，无领域知识。

处理内容（与学科无关）：
1. 口语填充词删除
2. 空白/标点规范化
3. 过短片段过滤（< 4 字）

注意：ASR 同音错字修正、数学符号 → LaTeX 等依赖领域知识的任务，
已全部交由 cleaner.py 的 DeepSeek 单次 API 调用完成。
此模块只做语言层通用清洗，适用于任何学科。
"""

import re
import logging

logger = logging.getLogger(__name__)

# ============================================================
# 口语填充词（语言特征，非领域依赖，可直接删除）
# ============================================================
FILLER_WORDS_RE = re.compile(
    r"(那个|那么|就是说|的话呢|所以呢|这个呢|那个呢|然后呢|好吧|对不对|是不是|知道吧|明白吗"
    r"|就是说呢|然后就是说|那么就是说|这个就是说|那个就是说|嗯|啊|呃|嘛)",
)

# 连续空白
_MULTI_SPACE_RE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    """对单段文本执行语言层通用清洗（无领域知识）。"""
    # Step 1: 去口语填充词
    text = FILLER_WORDS_RE.sub("", text)

    # Step 2: 清理多余空白
    text = _MULTI_SPACE_RE.sub(" ", text).strip()

    return text


def clean_segments(segments: list[dict]) -> list[dict]:
    """对 transcript 的 segments 列表执行批量规则清洗。

    返回清洗后的 segments（text 字段已修正），不改变原始结构。
    过滤掉清洗后不足 4 字的无意义段。
    """
    cleaned = []
    for seg in segments:
        original = seg.get("text", "")
        cleaned_text = clean_text(original)

        if len(cleaned_text) < 4:
            logger.debug(f"跳过过短段: {seg.get('segment_id')} ({len(cleaned_text)}字)")
            continue

        cleaned_seg = dict(seg)
        cleaned_seg["text"] = cleaned_text
        cleaned.append(cleaned_seg)

    removed = len(segments) - len(cleaned)
    if removed:
        logger.info(f"规则清洗: {len(segments)} → {len(cleaned)} 段 (过滤 {removed} 段)")
    return cleaned
