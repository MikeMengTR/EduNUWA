"""
M3 匹配模型（MVP）：LLM 直接语义匹配。

学生用自然语言描述想要的老师 → LLM 读候选老师的开放风格标签 + 基础指标
→ 输出按「贴合该学生需求」排序的结果 + 推荐理由。

守 H1（不是找最优老师，是贴近偏好，不同需求得不同结果）
守 H9（推荐理由的 matched_tags 必须 ⊆ 老师真实标签集）

依赖：DeepSeek（OpenAI 兼容接口，.env 提供 KEY/MODEL）。
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

_ENV_LOADED = False


def _ensure_env() -> None:
    global _ENV_LOADED
    if not _ENV_LOADED:
        repo = Path(__file__).resolve().parents[3]
        load_dotenv(repo / ".env")
        _ENV_LOADED = True


# ============================================================
# 加载候选老师
# ============================================================
def load_teachers(fixtures_dir: str | Path) -> list[dict]:
    """从 fixtures 目录加载所有 skill_profile.json，抽出匹配所需的精简视图。"""
    fixtures_dir = Path(fixtures_dir)
    teachers = []
    for prof_path in sorted(fixtures_dir.glob("*/skill_profile.json")):
        p = json.loads(prof_path.read_text(encoding="utf-8"))
        teachers.append({
            "teacher_id": p["teacher_id"],
            "teacher_name": p.get("teacher_name", p["teacher_id"]),
            "subject": p.get("attributes", {}).get("subject", ""),
            "grade": p.get("quality", {}).get("overall_grade", "NA"),
            "style_tags": [t["text"] for t in p.get("style_tags", [])],
            "base_metrics": {
                k: v.get("label", "") for k, v in p.get("base_metrics", {}).items()
            },
        })
    return teachers


# ============================================================
# LLM 调用
# ============================================================
def _call_llm(prompt: str, max_tokens: int = 3000, temperature: float = 0.3) -> str:
    _ensure_env()
    key = os.getenv("DEEPSEEK_API_KEY")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    url = "https://api.deepseek.com/v1/chat/completions"
    # 关闭思考模式：排序任务不需要推理。v4-flash 默认 thinking=enabled，开启时推理会吃掉
    # 大量 token 与时延（实测 7~22s、输出量在 1k~4.5k token 间剧烈波动，且 max_tokens 偏小
    # 时推理未完就撞顶、正文为空导致解析失败）；关闭后稳定 ~3s、只产出答案本身。
    # 参数见 https://api-docs.deepseek.com/zh-cn/guides/thinking_mode
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}],
              "max_tokens": max_tokens, "temperature": temperature,
              "thinking": {"type": "disabled"}},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"] or ""


def _extract_json(text: str):
    """从 LLM 输出里提取 JSON 数组（容忍 markdown 包裹/前后文字）。"""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text, flags=re.IGNORECASE)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 整体解析失败：最常见原因是数组被 max_tokens 截断（尾部对象不完整）。
    # 逐个抠出所有「完整的顶层对象」，截断的半截对象自然被丢弃——保住其余排序结果，
    # 而不是退回到只返回第一个对象（那会让下游把 dict 当列表遍历而崩）。
    objs = _salvage_objects(text)
    if objs:
        return objs
    dec = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in "[{":
            try:
                obj, _ = dec.raw_decode(text[i:])
                return obj
            except json.JSONDecodeError:
                continue
    raise ValueError("无法从 LLM 输出解析 JSON")


def _salvage_objects(text: str) -> list:
    """从（可能被截断的）文本里尽量多地抠出完整的顶层 JSON 对象，按出现顺序返回。"""
    dec = json.JSONDecoder()
    objs = []
    i, n = 0, len(text)
    while i < n:
        if text[i] == "{":
            try:
                obj, end = dec.raw_decode(text, i)
                if isinstance(obj, dict):
                    objs.append(obj)
                    i = end
                    continue
            except json.JSONDecodeError:
                pass
        i += 1
    return objs


def _coerce_rankings(parsed) -> list:
    """把 LLM 解析结果归一化为「排序对象列表」list[dict]。

    LLM 输出非确定性，偶尔不返回裸数组而是：
      - 把数组包进对象：{"rankings": [...]} / {"results": [...]} 等
      - 直接返回单个排序对象：{"teacher_id": ...}
      - 数组里混入字符串/空值
    若不收敛，下游 `item.get(...)` 会在字符串上崩
    （'str' object has no attribute 'get'，即 /api/v1/match 报的"匹配失败"）。
    """
    if isinstance(parsed, list):
        return [x for x in parsed if isinstance(x, dict)]
    if isinstance(parsed, dict):
        if "teacher_id" in parsed:  # 单个排序对象
            return [parsed]
        for v in parsed.values():   # 包了一层：取第一个「对象列表」字段
            if isinstance(v, list):
                items = [x for x in v if isinstance(x, dict)]
                if items:
                    return items
    return []


# ============================================================
# 阶段一：确定性召回（送 LLM 精排前，把候选压到 top-K）
# ============================================================
# 送进 LLM 精排的最大候选数（召回打分后取 top-N）。提速主要靠关闭思考模式（见 _call_llm），
# 故无需为速度牺牲候选数：该上限只为大规模（教师数 >> 15）给 prompt/输出封顶；当前 12 位
# 老师 ≤ 该值，一个候选都不丢，最大限度保留匹配能力。
RECALL_LIMIT = 15

# 学科别名：把学生口语词映射到规范学科关键词，缓解「微积分 ⊄ 高等数学」这类
# 子串匹配漏召回。漏列不致命——召回是「打分取 top-K」而非硬过滤。
_SUBJECT_ALIASES = {
    "高等数学": ["微积分", "高数", "数学分析", "导数", "积分", "极限", "微分", "数学"],
    "概率论": ["概率", "统计", "随机", "数理统计"],
    "线性代数": ["线代", "矩阵", "向量", "行列式"],
    "离散数学": ["离散"],
    "复变函数": ["复变", "复分析"],
    "机器学习": ["深度学习", "神经网络", "人工智能", "算法"],
    "数据结构": ["算法", "编程", "代码", "数据结构"],
    "大学物理": ["物理", "力学", "电磁", "热学", "光学"],
    "有机化学": ["化学", "有机", "无机"],
    "西方园林历史与艺术": ["园林", "艺术", "历史"],
}


def _bigrams(text: str) -> set:
    """中文文本的 2-gram 字符集合（去空白、转小写）。2-gram 比单字更抗虚词噪声。"""
    text = re.sub(r"\s+", "", (text or "").lower())
    if len(text) < 2:
        return {text} if text else set()
    return {text[i:i + 2] for i in range(len(text) - 1)}


def _subject_keywords(subject: str) -> list:
    """老师学科 → 召回关键词集（学科本身 + 别名表同义词，按双向包含匹配别名表）。"""
    subject = subject or ""
    kws = [subject] if subject else []
    for canon, aliases in _SUBJECT_ALIASES.items():
        if canon in subject or subject in canon:
            kws.append(canon)
            kws.extend(aliases)
            break
    return [k for k in kws if k]


def _recall_score(query_lower: str, q_bigrams: set, teacher: dict) -> float:
    """确定性召回分：学科命中（强）+ 标签字面重叠（弱）+ grade（极弱 tie-break）。"""
    score = 0.0
    # 1) 学科信号（强）：老师学科或其同义词出现在 query 里
    for kw in _subject_keywords(teacher.get("subject") or ""):
        if kw.lower() in query_lower:
            score += 3.0
            break
    # 2) 标签信号（弱）：query 与「风格标签 + 众评标签」文本的 2-gram 重叠
    tag_bigrams = set()
    for t in (teacher.get("style_tags") or []):
        tag_bigrams |= _bigrams(t if isinstance(t, str) else str(t))
    for c in (teacher.get("crowd_tags") or []):
        text = c.get("text", "") if isinstance(c, dict) else str(c)
        tag_bigrams |= _bigrams(text)
    score += min(len(q_bigrams & tag_bigrams) * 0.3, 2.0)
    # 3) grade（极弱 tie-break）：grade 指标当前不完善，仅同分微调，绝不硬过滤
    grade = (teacher.get("grade") or "").strip().upper()[:1]
    score += {"A": 0.3, "B": 0.2}.get(grade, 0.0)
    return score


def recall_candidates(query: str, teachers: list[dict], limit: int = RECALL_LIMIT) -> list:
    """阶段一确定性召回：候选 > limit 时按结构化信号打分取 top-limit；否则原样返回。

    目的：给送进 LLM 精排的候选数封顶，使 prompt 与输出长度都有上界——既消除
    「老师一多就撑爆 LLM 输出上限」的扩展性炸弹，又把延迟/成本绑定到 limit 而非
    教师总数。纯字符串运算、零 LLM、确定性可复现（稳定排序，同分保持原序）。
    """
    teachers = list(teachers)
    if len(teachers) <= limit:
        return teachers
    ql = (query or "").lower()
    qb = _bigrams(query or "")
    return sorted(teachers, key=lambda t: _recall_score(ql, qb, t), reverse=True)[:limit]


# ============================================================
# 匹配主函数
# ============================================================
def _build_prompt(query: str, teachers: list[dict]) -> str:
    lines = []
    for i, t in enumerate(teachers, 1):
        bm = "，".join(f"{k}：{v}" for k, v in t["base_metrics"].items())
        entry = (
            f"[{i}] id={t['teacher_id']} {t['teacher_name']}（{t['subject']}）\n"
            f"    风格标签：{'、'.join(t['style_tags'])}\n"
        )
        # 众评标签：来自真实学生反馈的进化闭环（style_tags_live.json），可信度随支持人数增长
        crowd = t.get("crowd_tags") or []
        if crowd:
            crowd_str = "、".join(f"{c['text']}（{c.get('support', 1)}名学生反馈）" for c in crowd)
            entry += f"    学生众评标签：{crowd_str}\n"
        entry += f"    基础指标：{bm}　质量等级：{t['grade']}"
        lines.append(entry)
    teacher_block = "\n".join(lines)
    return f"""你是教师风格匹配器。学生用自然语言描述想要的老师，你从候选老师里按「风格贴合这位学生的需求」排序。

重要原则：
- 贴合度 = 贴近学生偏好，**不是**「老师越好分越高」。不同需求应得到不同排序。
- 推荐理由必须基于老师的真实风格标签，不要编造老师没有的标签。
- 「风格标签」来自授课转写蒸馏，「学生众评标签」来自真实学生反馈（支持人数越多越可信），两类都可作为匹配依据。

【学生需求】
{query}

【候选老师】
{teacher_block}

请按贴合度从高到低排序，返回 JSON 数组（只返回 JSON，不要解释文字、不要 markdown）。
reason 必须精炼，**不超过 18 个汉字**、点明最关键的贴合点；matched_tags **最多 2 个**：
[
  {{"teacher_id": "...", "semantic_fit": 0.0到1.0, "reason": "精炼一句(≤18字)", "matched_tags": ["命中标签"]}}
]"""


# 结果缓存：相同 query + 相同候选集在 TTL 内直接命中，省掉重复 LLM 调用（对反复
# 测试同一句、或多人输入相同描述尤其有效）。教师 profile 在 TTL 内被改不会刷新缓存，
# 10 分钟可接受。进化闭环的 match_id 仍由路由层每次新建，不受此缓存影响。
_MATCH_CACHE: dict = {}
_MATCH_CACHE_TTL = 600
_MATCH_CACHE_MAX = 256
_MATCH_CACHE_LOCK = threading.Lock()


def _cache_key(query: str, teachers: list[dict]):
    return ((query or "").strip().lower(),
            tuple(sorted(t.get("teacher_id", "") for t in teachers)))


def match_teachers(query: str, teachers: list[dict], top_k: int | None = None) -> dict:
    """
    对学生需求做语义匹配排序。

    Returns:
      {"status":"success", "query":..., "results":[{teacher_id, teacher_name, semantic_fit, reason, matched_tags}, ...]}
      失败: {"status":"error", "message":...}
    """
    if not teachers:
        return {"status": "error", "message": "no candidate teachers"}
    # 召回封顶：候选超过 RECALL_LIMIT 时取最相关的 top-N 送精排（大规模才生效，当前不丢候选）。
    teachers = recall_candidates(query, teachers)

    key = _cache_key(query, teachers)
    now = time.time()
    with _MATCH_CACHE_LOCK:
        hit = _MATCH_CACHE.get(key)
        if hit and hit[0] > now:
            return hit[1]

    try:
        # 关闭思考后输出只有答案本身（~数百 token），无推理消耗、无 runaway，故 max_tokens
        # 给足即可、绝不会饿死或截断；仍随候选数轻微伸缩留足余量。
        budget = min(4000, max(2000, 256 * len(teachers)))
        raw = _call_llm(_build_prompt(query, teachers), max_tokens=budget, temperature=0.2)
        ranked = _coerce_rankings(_extract_json(raw))
    except Exception as e:
        return {"status": "error", "message": f"{type(e).__name__}: {e}"}

    by_id = {t["teacher_id"]: t for t in teachers}
    results = []
    for item in ranked:
        tid = item.get("teacher_id")
        t = by_id.get(tid)
        if not t:
            continue
        # H9 防幻觉：matched_tags 必须 ⊆ 老师真实标签（蒸馏标签 ∪ 学生众评标签）
        real_tags = set(t["style_tags"]) | {c["text"] for c in (t.get("crowd_tags") or [])}
        llm_tags = [x for x in (item.get("matched_tags") or []) if isinstance(x, str)]
        valid_tags = [x for x in llm_tags if x in real_tags]
        results.append({
            "teacher_id": tid,
            "teacher_name": t["teacher_name"],
            "subject": t["subject"],
            "semantic_fit": item.get("semantic_fit"),
            "reason": item.get("reason", ""),
            "matched_tags": valid_tags,
            "hallucinated_tags": [x for x in llm_tags if x not in real_tags],
        })
    if top_k:
        results = results[:top_k]
    result = {"status": "success", "query": query, "results": results}

    with _MATCH_CACHE_LOCK:
        if len(_MATCH_CACHE) >= _MATCH_CACHE_MAX:
            for k in [k for k, (exp, _) in _MATCH_CACHE.items() if exp <= now]:
                _MATCH_CACHE.pop(k, None)
            if len(_MATCH_CACHE) >= _MATCH_CACHE_MAX:
                _MATCH_CACHE.clear()
        _MATCH_CACHE[key] = (now + _MATCH_CACHE_TTL, result)
    return result
