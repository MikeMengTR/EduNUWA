# -*- coding: utf-8 -*-
"""M3 matcher 召回层（阶段一）+ LLM 输出归一化单测（mock LLM，不打网络）。

运行：
    & D:\\anaconda3\\envs\\edu\\python.exe modules\\M3_catalog\\matching_engine\\test_matcher.py
"""
import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from modules.M3_catalog.matching_engine import matcher as M

PASS = 0
FAIL = []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL.append(name)
        print(f"FAIL  {name}  {detail}")


def mk(tid, subject, tags, grade="B"):
    return {"teacher_id": tid, "teacher_name": tid, "subject": subject,
            "grade": grade, "style_tags": list(tags), "crowd_tags": [], "base_metrics": {}}


# 5 位高数老师 + 20 位其它学科 = 25 位（> RECALL_LIMIT，触发召回）
MATH = [mk(f"MATH_{i}", "高等数学", ["先直观后严格", "善用几何直观"]) for i in range(5)]
OTHERS = (
    [mk(f"PHY_{i}", "大学物理", ["实验演示", "联系生活现象"]) for i in range(7)]
    + [mk(f"CHEM_{i}", "有机化学", ["机理推导", "对比记忆"]) for i in range(7)]
    + [mk(f"HIST_{i}", "西方园林历史与艺术", ["图文对照", "正式学术口吻"]) for i in range(6)]
)
BIG = MATH + OTHERS  # 25 位


# ---------- 召回纯逻辑 ----------
def test_bypass_when_small():
    small = MATH + OTHERS[:1]  # 6 位 ≤ RECALL_LIMIT
    out = M.recall_candidates("随便什么需求", small)
    check("N<=limit 原样返回全部", len(out) == 6 and out == small)


def test_caps_to_limit():
    out = M.recall_candidates("我想速通微积分、打好数学基础", BIG)
    check("N>limit 压到 RECALL_LIMIT", len(out) == M.RECALL_LIMIT, f"got {len(out)}")


def test_subject_recall_hits():
    out = M.recall_candidates("数学基础差，想两天速通微积分", BIG)
    ids = {t["teacher_id"] for t in out}
    math_ids = {t["teacher_id"] for t in MATH}
    check("学科强相关老师全部进 top-K", math_ids <= ids,
          f"missing {math_ids - ids}")


def test_subject_alias_calc():
    # query 只说「微积分」「导数」，不含「高等数学」字面——靠别名表召回
    out = M.recall_candidates("讲导数和积分讲得清楚的老师", BIG)
    ids = {t["teacher_id"] for t in out}
    check("别名（微积分/导数→高等数学）能召回", {t["teacher_id"] for t in MATH} <= ids)


def test_deterministic():
    q = "喜欢用生活例子、节奏快的老师"
    a = [t["teacher_id"] for t in M.recall_candidates(q, BIG)]
    b = [t["teacher_id"] for t in M.recall_candidates(q, BIG)]
    check("同 query 召回结果可复现", a == b)


def test_no_crash_on_dirty_fields():
    dirty = BIG + [
        {"teacher_id": "DIRTY1", "teacher_name": "x", "subject": None,
         "grade": None, "style_tags": [123, None], "crowd_tags": ["bad"], "base_metrics": {}},
    ]
    out = M.recall_candidates("数学", dirty)
    check("脏字段不致召回崩溃", len(out) == M.RECALL_LIMIT)


# ---------- 与 match_teachers 集成（mock LLM）----------
def _fake_llm(prompt, max_tokens=3000, temperature=0.3):
    ids = re.findall(r"id=(\S+)", prompt)
    # 关键断言：送进 LLM 的候选已被召回压到 ≤ RECALL_LIMIT
    assert len(ids) <= M.RECALL_LIMIT, f"LLM 收到 {len(ids)} 个候选，超过 limit"
    return json.dumps([{"teacher_id": i, "semantic_fit": 0.5, "reason": "x",
                        "matched_tags": []} for i in ids], ensure_ascii=False)


def test_match_teachers_recalls_before_llm():
    with patch.object(M, "_call_llm", _fake_llm):
        res = M.match_teachers("速通微积分", BIG)
    ok = res.get("status") == "success" and len(res.get("results", [])) <= M.RECALL_LIMIT
    check("match_teachers 先召回后精排（候选有上界）", ok, str(res)[:160])


def test_cache_hit_skips_llm():
    M._MATCH_CACHE.clear()
    calls = {"n": 0}

    def counting_llm(prompt, max_tokens=3000, temperature=0.3):
        calls["n"] += 1
        return _fake_llm(prompt, max_tokens, temperature)

    with patch.object(M, "_call_llm", counting_llm):
        M.match_teachers("缓存测试query", BIG)
        M.match_teachers("缓存测试query", BIG)   # 同 query+候选 → 命中缓存
    check("相同查询命中缓存、第二次不调 LLM", calls["n"] == 1, f"llm called {calls['n']}x")
    M._MATCH_CACHE.clear()


# ---------- LLM 输出归一化（回归此前的崩溃修复）----------
def test_coerce_rankings_shapes():
    cases = {
        "list": ([{"teacher_id": "T1"}], 1),
        "dict-wrapped": ({"rankings": [{"teacher_id": "T1"}]}, 1),
        "single-object": ({"teacher_id": "T1"}, 1),
        "mixed-list": (["junk", {"teacher_id": "T1"}, None], 1),
        "garbage": ("not json", 0),
    }
    allok = True
    for name, (inp, n) in cases.items():
        out = M._coerce_rankings(inp)
        if not (len(out) == n and all(isinstance(x, dict) for x in out)):
            allok = False
    check("_coerce_rankings 收敛所有 LLM 输出形状", allok)


def test_extract_json_salvages_truncated_array():
    truncated = ('[{"teacher_id":"T1"},{"teacher_id":"T2"},'
                 '{"teacher_id":"T3"},{"teacher_id":"T4","sem')
    out = M._extract_json(truncated)
    ids = [o.get("teacher_id") for o in out]
    check("截断数组抢救出完整对象", ids == ["T1", "T2", "T3"], str(ids))


if __name__ == "__main__":
    for fn in [test_bypass_when_small, test_caps_to_limit, test_subject_recall_hits,
               test_subject_alias_calc, test_deterministic, test_no_crash_on_dirty_fields,
               test_match_teachers_recalls_before_llm, test_cache_hit_skips_llm,
               test_coerce_rankings_shapes, test_extract_json_salvages_truncated_array]:
        try:
            fn()
        except Exception as e:
            FAIL.append(fn.__name__)
            print(f"FAIL  {fn.__name__}  EXCEPTION {type(e).__name__}: {e}")
    print(f"\n{PASS} passed, {len(FAIL)} failed" + (f": {FAIL}" if FAIL else ""))
    sys.exit(1 if FAIL else 0)
