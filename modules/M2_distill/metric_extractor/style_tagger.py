"""
M2 开放风格标签提炼：从转写用 LLM 提炼「讲解风格」形容词标签。

这是评价模型里需要语义理解的部分（base_metrics 是纯计算，这里是 LLM）。
产出开放词汇标签（不预设维度/词表），每个标签：
  text / dimension(软归类,可null) / source=auto / confidence / evidence(seg证据) / cluster_id=null

硬约束 H5（抗操纵）：每个 auto 标签必须有 ≥1 条转写 seg 证据，
且证据 seg 必须真实存在；无证据的标签直接丢弃。

依赖：DeepSeek（OpenAI 兼容接口，.env 提供 KEY/MODEL）。

CLI:
    python modules/M2_distill/metric_extractor/style_tagger.py \
        data/teachers/T_legacy_001/transcripts/TR_Tlegacy001_001.json
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

_ALLOWED_DIMS = {"pace", "detail", "abstraction", "interactivity", "humor", "rigor"}
_ENV_LOADED = False


def _ensure_env() -> None:
    global _ENV_LOADED
    if not _ENV_LOADED:
        repo = Path(__file__).resolve().parents[3]
        load_dotenv(repo / ".env")
        _ENV_LOADED = True


def _call_llm(prompt: str, max_tokens: int = 4000, temperature: float = 0.3) -> str:
    _ensure_env()
    key = os.getenv("DEEPSEEK_API_KEY")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    r = requests.post(
        "https://api.deepseek.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}],
              "max_tokens": max_tokens, "temperature": temperature},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"] or ""


def _extract_json(text: str):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text, flags=re.IGNORECASE)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    dec = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in "[{":
            try:
                obj, _ = dec.raw_decode(text[i:])
                return obj
            except json.JSONDecodeError:
                continue
    raise ValueError("无法从 LLM 输出解析 JSON")


def _collect_segments(transcript_paths: list[str | Path]) -> list[tuple[str, str]]:
    """收集所有转写的 (seg_id, text)，跨文件保持 seg_id 唯一（加文件前缀避免冲突）。"""
    segs: list[tuple[str, str]] = []
    for idx, p in enumerate(transcript_paths):
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        prefix = "" if len(transcript_paths) == 1 else f"f{idx}_"
        for s in data.get("segments", []):
            sid = prefix + s.get("segment_id", f"seg_{len(segs)+1:04d}")
            text = s.get("text", "").strip()
            if text:
                segs.append((sid, text))
    return segs


def _build_prompt(segs: list[tuple[str, str]]) -> str:
    transcript = "\n".join(f"{sid}: {text}" for sid, text in segs)
    return f"""你是教师讲解风格分析器。下面是一位教师授课的转写（每段带编号 seg_xxxx）。
请提炼这位老师最鲜明的「讲解风格」形容词标签——也就是学生会用来形容这位老师的词。

要求：
1. 每个标签是简短的形容词短语（如「设问自答」「爱用生活类比」「娓娓道来」「主动拦截易错点」），不限词表，自由提炼。
2. 只提炼从转写里**真实观察到**的风格，不要套用通用教学常识。
3. 每个标签必须标注 evidence：支撑它的 1-2 个 seg 编号（必须是上面真实出现的编号）。
4. dimension 软归类，从这些里选或填 null：pace（节奏）/ detail（详略）/ abstraction（具象抽象）/ interactivity（互动）/ humor（幽默）/ rigor（严谨）。
5. confidence 给 0.0–1.0，表示你对该标签的把握。
6. 提炼 4–10 个标签，宁缺毋滥——没有转写证据支撑的不要写。

【转写】
{transcript}

只返回 JSON 数组，不要解释文字：
[
  {{"text": "设问自答", "dimension": "interactivity", "confidence": 0.8, "evidence": ["seg_0002"]}}
]"""


def extract_style_tags(transcript_paths, config: dict | None = None) -> dict:
    """
    从一份或多份转写提炼开放风格标签。

    Returns:
      成功:
        {
          "status": "success",
          "style_tags": [ {text, dimension, source:"auto", confidence, evidence:[...], cluster_id:null}, ... ],
          "style_embeddings_model": "bge-base-zh-v1.5",
          "warnings": [...]
        }
      失败: {"status":"error", "message":...}
    """
    config = config or {}
    if isinstance(transcript_paths, (str, Path)):
        transcript_paths = [transcript_paths]
    model = config.get("embeddings_model", "bge-base-zh-v1.5")

    segs = _collect_segments(transcript_paths)
    if not segs:
        return {"status": "error", "message": "no segments in transcript(s)"}
    valid_ids = {sid for sid, _ in segs}

    try:
        raw = _call_llm(_build_prompt(segs))
        tags_raw = _extract_json(raw)
    except Exception as e:
        return {"status": "error", "message": f"{type(e).__name__}: {e}"}

    if not isinstance(tags_raw, list):
        return {"status": "error", "message": "LLM did not return a JSON array"}

    style_tags = []
    warnings: list[str] = []
    dropped_no_evidence = 0
    for item in tags_raw:
        if not isinstance(item, dict) or not item.get("text"):
            continue
        # H5：evidence 必须存在、且 seg 真实
        ev = [e for e in (item.get("evidence") or []) if e in valid_ids]
        if not ev:
            dropped_no_evidence += 1
            continue  # 无有效证据 → 丢弃（抗操纵）
        dim = item.get("dimension")
        if dim not in _ALLOWED_DIMS:
            dim = None
        conf = item.get("confidence")
        if not isinstance(conf, (int, float)) or not (0.0 <= conf <= 1.0):
            conf = 0.6
        style_tags.append({
            "text": str(item["text"]).strip(),
            "dimension": dim,
            "source": "auto",
            "confidence": round(float(conf), 2),
            "evidence": ev,
            "cluster_id": None,
        })

    if dropped_no_evidence:
        warnings.append(f"dropped_{dropped_no_evidence}_tags_without_evidence")
    if not style_tags:
        warnings.append("zero_style_tags")  # M3 据此回退 base_metrics 排序

    return {
        "status": "success",
        "style_tags": style_tags,
        "style_embeddings_model": model,
        "warnings": warnings,
    }


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else \
        "data/teachers/T_legacy_001/transcripts/TR_Tlegacy001_001.json"
    result = extract_style_tags(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
