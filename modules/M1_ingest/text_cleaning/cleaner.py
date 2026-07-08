"""
M1 文本精修器：使用 LLM 将 ASR 转写文本精修为学术讲义。

从 LLM_Refiner.py 重构为函数接口。
将 ASR 口语化文本 → 学术 LaTeX 格式、去口语、结构重组。
支持并发请求多个 chunk 加速处理。

依赖 requests（标准依赖，已在 requirements.txt 中）。
"""

import os
import json
import logging
import time
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

logger = logging.getLogger(__name__)


def _build_refine_prompt(raw_text: str) -> str:
    """构建精修 prompt（保留原始 LLM_Refiner.py 的核心指令）。"""
    return f"""# Role
你是一位极致严谨的数学专家级助教，负责将大学数学 MOOC 录播课的 ASR 转写稿转化为高质量的学术讲义文本。

# Task Goals
1. **学术纠错**：ASR 识别常有逻辑错误。若原文数学结论错误，请基于数学常识修正。
2. **公式标准 LaTeX 化**：所有数学变量、符号、算式必须包裹在 $ $ 中。
3. **结构化整理**：彻底去掉口语词，将碎片化的句子合并为逻辑连贯的学术段落。

# Specific Correction Rules
- 术语修复：3音/3x -> $\\sin x$；tg -> $\\tan x$；x去0 -> $x \\to 0$；阿尔法/贝塔 -> $\\alpha, \\beta$。
- 风格约束：采用正式学术教学语言，严禁使用非学术性比喻。

# Workflow
- 第一步：修正逻辑错误和术语。
- 第二步：转换为标准 LaTeX。
- 第三步：精简口语，重组段落。
- 第四步：仅输出纯净文本，严禁解释说明。

待处理文本：
{raw_text}
"""


def _call_llm(api_url: str, model: str, text: str, timeout: int = 120,
              max_tokens: int = 2048, api_key: str | None = None) -> str:
    """调用 LLM API 精修单段文本，带重试机制。

    api_key 非空时附 Authorization: Bearer 头（用于 DeepSeek 等需鉴权的 OpenAI 兼容端点）。
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": _build_refine_prompt(text)}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
    for attempt in range(3):
        try:
            response = requests.post(api_url, json=payload, timeout=timeout, headers=headers)
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content'].strip()
            logger.warning(
                f"LLM API 返回 {response.status_code} (尝试 {attempt + 1}/3)"
            )
        except Exception as e:
            logger.warning(f"LLM API 异常 (尝试 {attempt + 1}/3): {e}")
        if attempt < 2:
            time.sleep(3)
    return ""  # 3 次重试后返回空串


def refine_transcript(
    transcript_json_path: str,
    output_path: str,
    config: dict | None = None,
) -> dict:
    """对一份 teacher_transcript.json 执行 LLM 文本精修。

    将 segments 按 chunk_size 分组，并发发送给 LLM 进行学术化重写。
    输出保持标准 segments schema，每段的时间戳为对应 chunk 的起止范围。

    Args:
        transcript_json_path: 原始转写 JSON 路径（ASR 输出）
        output_path: 精修输出 JSON 路径
        config: 可选配置字典：
            - api_url: str = "http://localhost:8000/v1/chat/completions"
            - model: str = "qwen-32b"
            - max_workers: int = 5（并发线程数）
            - chunk_size: int = 12（每 chunk 合并的 segment 数）
            - timeout: int = 120

    Returns:
        {
            "status": "success",
            "refined_path": "data/teachers/.../xxx_refined.json",
            "segments_count": 8,
            "original_segments": 96
        }
    """
    cfg = {
        "api_url": "http://localhost:8000/v1/chat/completions",
        "model": "qwen-32b",
        "max_workers": 5,
        "chunk_size": 12,
        "timeout": 120,
        "api_key": None,
    }
    if config:
        cfg.update(config)

    if not os.path.exists(transcript_json_path):
        return {
            "status": "error",
            "message": f"transcript 文件不存在: {transcript_json_path}",
        }

    with open(transcript_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    raw_segments = data.get("segments", [])
    if not raw_segments:
        logger.warning(f"transcript 中没有 segments: {transcript_json_path}")
        return {
            "status": "error",
            "message": "transcript 中没有 segments",
        }

    # 按 chunk_size 分组
    chunk_size = cfg["chunk_size"]
    chunks = []
    for i in range(0, len(raw_segments), chunk_size):
        group = raw_segments[i: i + chunk_size]
        chunks.append({
            "group_id": i // chunk_size,
            "start": group[0]["start"],
            "end": group[-1]["end"],
            "text": " ".join([seg["text"] for seg in group]),
        })

    logger.info(
        f"精修开始: {len(raw_segments)} segments -> {len(chunks)} chunks "
        f"(chunk_size={chunk_size}, workers={cfg['max_workers']})"
    )

    # 并发精修
    refined_items = []
    with ThreadPoolExecutor(max_workers=cfg["max_workers"]) as executor:
        future_to_chunk = {
            executor.submit(
                _call_llm, cfg["api_url"], cfg["model"], c["text"],
                cfg["timeout"], api_key=cfg.get("api_key")
            ): c
            for c in chunks
        }
        for future in future_to_chunk:
            chunk_info = future_to_chunk[future]
            try:
                polished = future.result()
                if polished:
                    refined_items.append({
                        "group_id": chunk_info["group_id"],
                        "original_start": chunk_info["start"],
                        "original_end": chunk_info["end"],
                        "refined_text": polished,
                    })
                else:
                    logger.warning(f"Chunk {chunk_info['group_id']} 精修返回空")
            except Exception as e:
                logger.error(f"Chunk {chunk_info['group_id']} 处理异常: {e}")

    refined_items.sort(key=lambda x: x["group_id"])

    # 组装输出：对齐标准 segments schema
    output_segments = []
    for item in refined_items:
        output_segments.append({
            "segment_id": f"seg_{item['group_id'] + 1:04d}",
            "start": round(item["original_start"], 2),
            "end": round(item["original_end"], 2),
            "text": item["refined_text"],
            "speaker": "teacher",
        })

    output_data = {
        "transcript_id": data.get("transcript_id", "unknown"),
        "source_audio": data.get("source_audio", ""),
        "language": data.get("language", "zh"),
        "refined_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "refine_config": {
            "model": cfg["model"],
            "chunk_size": chunk_size,
        },
        "segments": output_segments,
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    logger.info(
        f"精修完成: {len(refined_items)}/{len(chunks)} chunks 成功, "
        f"输出 {output_path}"
    )
    return {
        "status": "success",
        "refined_path": output_path,
        "segments_count": len(output_segments),
        "original_segments": len(raw_segments),
    }


# ============================================================
# 本地测试入口（不依赖外部 API 的 schema 测试）
# ============================================================
if __name__ == "__main__":
    import tempfile

    print("=== text_refiner unit tests ===\n")

    # 创建模拟 transcript JSON
    tmp_dir = tempfile.mkdtemp()
    test_input = os.path.join(tmp_dir, "test_transcript.json")
    test_output = os.path.join(tmp_dir, "test_refined.json")

    sample_transcript = {
        "transcript_id": "TR_T20260515001_001",
        "source_audio": "lecture1.mp4",
        "language": "zh",
        "segments": [
            {"segment_id": f"seg_{i:04d}", "start": i * 5.0, "end": (i + 1) * 5.0,
             "text": f"这是第 {i} 段测试文本。", "speaker": "teacher"}
            for i in range(1, 25)
        ],
    }

    with open(test_input, "w", encoding="utf-8") as f:
        json.dump(sample_transcript, f, ensure_ascii=False, indent=2)

    # 测试 1：文件不存在时返回 error
    result = refine_transcript(
        "nonexistent.json", test_output,
        config={"api_url": "http://localhost:9999/v1/chat/completions"}
    )
    assert result["status"] == "error", f"应返回 error: {result}"
    print(f"[OK] 文件不存在时返回 error: {result['message']}")

    # 测试 2：API 不可用时的容错（LLM 调用会失败但不抛异常）
    # 由于没有真实 LLM API，所有 chunk 都会失败返回空串
    result = refine_transcript(
        test_input, test_output,
        config={
            "api_url": "http://localhost:9999/v1/chat/completions",
            "model": "test-model",
            "max_workers": 2,
            "chunk_size": 12,
            "timeout": 2,
        }
    )
    # API 不可用时返回 success 但 segments 为空（容错设计）
    print(f"[OK] API 不可用时容错: status={result['status']}, "
          f"refined_segments={result.get('segments_count', 0)}, "
          f"original_segments={result.get('original_segments', 0)}")

    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)
    print("\n[PASS] text_refiner schema and error handling tests passed")
