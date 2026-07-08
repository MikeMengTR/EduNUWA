"""
M2 基础指标提炼：从 teacher_transcript.json 计算客观可测的基础指标。

纯计算，无 LLM —— 这是评价模型里最确定、最快的部分。
产出 base_metrics（数字 + label + polarity），对齐 skill_profile_v2.schema.json。

只放「能用代码算出带单位的数」的指标；主观风格（幽默/讲故事式…）一律走 style_tags。

CLI:
    python modules/M2_distill/metric_extractor/base_metrics.py \
        data/teachers/T_legacy_001/transcripts/TR_Tlegacy001_001.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_BANDS_PATH = Path(__file__).resolve().parent / "rubric" / "base_metrics_bands.json"

# 设问判定：句末问号，或含疑问标志词
_QUESTION_WORDS = ("吗", "呢", "为什么", "怎么", "是不是", "会不会", "难道", "对不对", "好不好")
_SENTENCE_SPLIT = re.compile(r"[。！？!?\n]")
# 计字数：保留中文字符 + 英文字母数字，去标点空白
_WORD_CHARS = re.compile(r"[一-鿿 A-Za-z0-9]".replace(" ", ""))


def _load_bands() -> dict:
    return json.loads(_BANDS_PATH.read_text(encoding="utf-8"))


def _band_lookup(bands_for_metric: list[dict], value: float) -> tuple[str, str]:
    """按 max 升序匹配区间，返回 (label, polarity)。"""
    for band in bands_for_metric:
        upper = band["max"]
        if upper is None or value < upper:
            return band["label"], band["polarity"]
    last = bands_for_metric[-1]
    return last["label"], last["polarity"]


def _count_chars(text: str) -> int:
    """去标点空白后的有效字数（中文字符 + 英文字母数字）。"""
    return len(_WORD_CHARS.findall(text))


def _count_questions(text: str) -> int:
    """统计设问句数：以问号结尾，或含疑问标志词的句子。"""
    n = 0
    for sent in _SENTENCE_SPLIT.split(text):
        s = sent.strip()
        if not s:
            continue
        # 该句在原文里是否紧跟问号？切分会丢标点，故用疑问词 + 兜底全文问号计数
        if any(w in s for w in _QUESTION_WORDS):
            n += 1
    # 直接以问号结尾的句子（疑问词没覆盖到的）
    n += len(re.findall(r"[？?]", text))
    # 去重高估：取两种信号的较大值更稳，这里用 max 思路——
    # 简化为：问号数 与 疑问词句数 取较大者
    qmark = len(re.findall(r"[？?]", text))
    qword = sum(1 for sent in _SENTENCE_SPLIT.split(text)
                if sent.strip() and any(w in sent for w in _QUESTION_WORDS))
    return max(qmark, qword)


def extract_base_metrics(transcript_path: str | Path, config: dict | None = None) -> dict:
    """
    从单份转写计算 base_metrics。

    Returns:
      成功:
        {
          "status": "success",
          "base_metrics": {
            "speech_rate":   {"value": 165, "unit": "字/分",     "label": "偏慢",   "polarity": "slow"},
            "question_freq": {"value": 4.2, "unit": "次/10分钟", "label": "时常提问","polarity": "mid"}
          },
          "warnings": [],
          "_debug": {...}
        }
      失败: {"status": "error", "message": "..."}
    """
    config = config or {}
    transcript_path = Path(transcript_path)
    if not transcript_path.exists():
        return {"status": "error", "message": f"transcript not found: {transcript_path}"}

    data = json.loads(transcript_path.read_text(encoding="utf-8"))
    segments = data.get("segments", [])
    if not segments:
        return {"status": "error", "message": "transcript has no segments"}

    bands = _load_bands()
    warnings: list[str] = []

    # ---- 字数 ----
    total_chars = sum(_count_chars(seg.get("text", "")) for seg in segments)
    total_questions = sum(_count_questions(seg.get("text", "")) for seg in segments)

    # ---- 有效语音时长（秒）：优先 segment 时间戳之和，回退 duration_sec ----
    has_ts = all(("start" in s and "end" in s) for s in segments)
    if has_ts:
        duration_sec = sum(s["end"] - s["start"] for s in segments)
    elif data.get("duration_sec"):
        duration_sec = float(data["duration_sec"])
        warnings.append("used_duration_sec_fallback")
    else:
        return {"status": "error", "message": "no timestamps and no duration_sec; cannot compute rate"}

    if duration_sec <= 0:
        return {"status": "error", "message": "non-positive duration"}

    minutes = duration_sec / 60.0
    base_metrics: dict = {}

    # ---- speech_rate（字/分）----
    speech_rate = round(total_chars / minutes, 1)
    label, polarity = _band_lookup(bands["speech_rate"], speech_rate)
    base_metrics["speech_rate"] = {
        "value": speech_rate, "unit": "字/分", "label": label, "polarity": polarity,
    }

    # ---- question_freq（次/10分钟）----
    question_freq = round(total_questions / minutes * 10.0, 1)
    label, polarity = _band_lookup(bands["question_freq"], question_freq)
    base_metrics["question_freq"] = {
        "value": question_freq, "unit": "次/10分钟", "label": label, "polarity": polarity,
    }

    return {
        "status": "success",
        "base_metrics": base_metrics,
        "warnings": warnings,
        "_debug": {
            "total_chars": total_chars,
            "total_questions": total_questions,
            "duration_sec": round(duration_sec, 1),
            "segments": len(segments),
        },
    }


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else \
        "data/teachers/T_legacy_001/transcripts/TR_Tlegacy001_001.json"
    result = extract_base_metrics(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
