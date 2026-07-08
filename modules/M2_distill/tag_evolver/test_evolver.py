# -*- coding: utf-8 -*-
"""tag_evolver 纯逻辑单测（mock LLM，不打网络）。

运行：
    & D:\\anaconda3\\envs\\edu\\python.exe modules\\M2_distill\\tag_evolver\\test_evolver.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from modules.M2_distill.tag_evolver.evolver import (
    refresh_crowd_tags, _crowd_confidence, _calibrate, extract_md_sections,
    LIVE_TAGS_MAX, PROMOTE_SUPPORT,
)
from modules.M2_distill.tag_evolver.revision import propose_skill_revision

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


def fb(i, student, rating, comment, created="2026-06-11T00:00:00+00:00", **kw):
    return {"feedback_id": f"fb{i:02d}", "student_hash": f"stu_{student}",
            "rating": rating, "comment": comment, "created_at": created,
            "context": "match", "query": kw.get("query", "想要节奏慢的老师"),
            "reason": kw.get("reason", ""), "matched_tags": kw.get("matched_tags", [])}


AUTO_TAGS = [
    {"text": "爱用生活类比", "dimension": "abstraction", "source": "auto",
     "confidence": 0.8, "evidence": ["seg_0001"], "cluster_id": None},
    {"text": "节奏舒缓", "dimension": "pace", "source": "auto",
     "confidence": 0.7, "evidence": ["seg_0002"], "cluster_id": None},
]


def make_caller(payload):
    return lambda prompt, **kw: json.dumps(payload, ensure_ascii=False)


# ---------- 1. 公式边界 ----------
check("crowd_confidence support=1", _crowd_confidence(1) == 0.55)
check("crowd_confidence support=5", _crowd_confidence(5) == 0.9 - 0.0 and _crowd_confidence(5) == 0.9)
check("crowd_confidence 上限0.9", _crowd_confidence(10) == 0.9)
check("crowd_confidence 反驳降权", _crowd_confidence(3, 2) == round(0.75 - 0.3, 2))
check("calibrate 上钳0.98", _calibrate(0.9, 10, 0) == 0.98)
check("calibrate 下钳0.1", _calibrate(0.3, 0, 10) == 0.1)
check("calibrate 常规", _calibrate(0.8, 2, 1) == 0.8)

# ---------- 2. 幻觉信号丢弃 ----------
gradient = {
    "feedback_attribution": {"fb01": "style_confirm"},
    "tag_signals": [
        {"tag_text": "爱用生活类比", "signal": "confirm", "evidence_feedback_ids": ["fb01"]},
        {"tag_text": "不存在的标签", "signal": "confirm", "evidence_feedback_ids": ["fb01"]},
        {"tag_text": "节奏舒缓", "signal": "contradict", "evidence_feedback_ids": ["fb_nonexist"]},
    ],
    "proposed_tags": [], "skill_md_suggestions": [],
}
r = refresh_crowd_tags("T_20260101_001", AUTO_TAGS, None, [],
                       [fb(1, "a", 5, "例子真的多")], llm_caller=make_caller(gradient))
check("status success", r["status"] == "success")
check("真实信号保留", "爱用生活类比" in r["calibration_delta"])
check("幻觉标签丢弃", "不存在的标签" not in r["calibration_delta"])
check("无效evidence丢弃", "节奏舒缓" not in r["calibration_delta"])
check("rejected 记录两条", len(r["gradient_report"]["rejected"]) == 2,
      str(r["gradient_report"]["rejected"]))

# ---------- 3. support 按 distinct student_hash + 晋升门槛 ----------
gradient2 = {
    "feedback_attribution": {},
    "tag_signals": [],
    "proposed_tags": [{"text": "语速偏快", "dimension": "pace", "merge_into": None,
                       "evidence_feedback_ids": ["fb01", "fb02", "fb03"], "note": ""}],
    "skill_md_suggestions": [],
}
# fb01/fb02 同一学生（去重后只剩 1 条），fb03 另一学生 → distinct=2 → 晋升
batch2 = [fb(1, "a", 3, "语速快", created="2026-06-11T00:00:00+00:00"),
          fb(2, "a", 3, "还是快", created="2026-06-11T01:00:00+00:00"),
          fb(3, "b", 4, "节奏有点赶")]
r2 = refresh_crowd_tags("T_20260101_001", AUTO_TAGS, None, [], batch2,
                        llm_caller=make_caller(gradient2))
live_texts = [t["text"] for t in r2["live_doc"]["tags"]]
check("两名学生支持 → 晋升 live", "语速偏快" in live_texts, str(live_texts))
tag = next(t for t in r2["live_doc"]["tags"] if t["text"] == "语速偏快")
check("support=2（同学生去重）", tag["support"] == 2, f"support={tag['support']}")
check("schema 必需字段齐全",
      all(k in tag for k in ("text", "source", "support", "confidence", "first_seen", "last_seen")))
check("source=crowd", tag["source"] == "crowd")

# 单人支持 → 入候补池不晋升
gradient3 = {"feedback_attribution": {}, "tag_signals": [],
             "proposed_tags": [{"text": "板书工整", "dimension": "detail", "merge_into": None,
                                "evidence_feedback_ids": ["fb01"], "note": ""}],
             "skill_md_suggestions": []}
r3 = refresh_crowd_tags("T_20260101_001", AUTO_TAGS, None, [],
                        [fb(1, "a", 5, "板书好看")], llm_caller=make_caller(gradient3))
check("单人支持不晋升", "板书工整" not in [t["text"] for t in r3["live_doc"]["tags"]])
check("入候补池", any(p["text"] == "板书工整" for p in r3["pending_pool"]))

# 候补池跨批次凑人：第二批另一学生支持同标签 → 晋升
r4 = refresh_crowd_tags("T_20260101_001", AUTO_TAGS, None, r3["pending_pool"],
                        [fb(9, "z", 5, "板书清楚")],
                        llm_caller=make_caller({"feedback_attribution": {}, "tag_signals": [],
                                                "proposed_tags": [{"text": "板书工整", "dimension": "detail",
                                                                   "merge_into": None,
                                                                   "evidence_feedback_ids": ["fb09"], "note": ""}],
                                                "skill_md_suggestions": []}))
check("跨批次凑satisfy晋升", "板书工整" in [t["text"] for t in r4["live_doc"]["tags"]])
check("晋升后移出候补池", not any(p["text"] == "板书工整" for p in r4["pending_pool"]))

# ---------- 4. merge_into 并入 auto 标签 → 校准 confirm ----------
gradient5 = {"feedback_attribution": {}, "tag_signals": [],
             "proposed_tags": [{"text": "例子接地气", "dimension": "abstraction",
                                "merge_into": "爱用生活类比",
                                "evidence_feedback_ids": ["fb01"], "note": ""}],
             "skill_md_suggestions": []}
r5 = refresh_crowd_tags("T_20260101_001", AUTO_TAGS, None, [],
                        [fb(1, "a", 5, "例子贴近生活")], llm_caller=make_caller(gradient5))
check("merge_into auto → confirm 校准", r5["calibration_delta"].get("爱用生活类比", {}).get("confirms") == 1)
check("merge 后不产生新标签", not r5["live_doc"]["tags"] and not r5["pending_pool"])

# ---------- 5. live 上限截断 ----------
big_live = {"teacher_id": "T_20260101_001", "style_embeddings_model": "bge-base-zh-v1.5",
            "updated_at": "2026-06-10T00:00:00+00:00",
            "tags": [{"text": f"标签{i}", "dimension": None, "source": "crowd", "support": 2 + i,
                      "confidence": 0.6, "cluster_id": None,
                      "first_seen": "2026-06-01T00:00:00+00:00",
                      "last_seen": "2026-06-10T00:00:00+00:00"} for i in range(LIVE_TAGS_MAX + 3)]}
r6 = refresh_crowd_tags("T_20260101_001", AUTO_TAGS, big_live, [],
                        [fb(1, "a", 5, "随便")],
                        llm_caller=make_caller({"feedback_attribution": {}, "tag_signals": [],
                                                "proposed_tags": [], "skill_md_suggestions": []}))
check("live 上限截断", len(r6["live_doc"]["tags"]) == LIVE_TAGS_MAX)
check("按 support*confidence 保留高分",
      "标签17" in [t["text"] for t in r6["live_doc"]["tags"]]
      and "标签0" not in [t["text"] for t in r6["live_doc"]["tags"]])

# ---------- 6. LLM 异常 → error，不落任何更新 ----------
def boom(prompt, **kw):
    raise RuntimeError("network down")
r7 = refresh_crowd_tags("T_20260101_001", AUTO_TAGS, None, [],
                        [fb(1, "a", 5, "x")], llm_caller=boom)
check("LLM 异常返回 error", r7["status"] == "error" and "network down" in r7["message"])

# ---------- 7. extract_md_sections / revision 段替换白名单 ----------
SKILL_MD = """# TeacherSkill: 测试老师

## Skill Purpose
迁移目标。

## Teaching Philosophy
信念一：直觉先行。

## Explanation Pattern
Step 1 → Step 2。

## Speech Policy
口头禅：大家注意。

## Output Contract
speak/board/formula。
"""
secs = extract_md_sections(SKILL_MD, ["Teaching Philosophy", "Speech Policy"])
check("段落抽取", "直觉先行" in secs.get("Teaching Philosophy", "")
      and "大家注意" in secs.get("Speech Policy", ""))

rev_payload = {
    "revised_sections": [
        {"section": "Speech Policy", "new_content": "## Speech Policy\n口头禅：大家注意。开头放慢节奏。"},
        {"section": "Output Contract", "new_content": "## Output Contract\n已被篡改"},
    ],
    "change_summary": [
        {"section": "Speech Policy", "before_excerpt": "口头禅", "after_excerpt": "放慢节奏",
         "why": "3 名学生反映语速快", "supported_by_n_students": 3},
        {"section": "Output Contract", "before_excerpt": "x", "after_excerpt": "y", "why": "z"},
    ],
    "unchanged_rationale": "其余段无反馈证据",
}
profile = {"style_tags": list(AUTO_TAGS), "version": 2}
calib = {"节奏舒缓": {"confirms": 0, "contradicts": 3, "original_confidence": 0.7}}
rr = propose_skill_revision("T_20260101_001", SKILL_MD, profile, None, calib,
                            [{"rating": 3, "comment": "语速快", "query": ""}],
                            llm_caller=make_caller(rev_payload))
check("revision success", rr["status"] == "success")
check("白名单段替换生效", "开头放慢节奏" in rr["revised_md"])
check("禁改段拒绝", "已被篡改" not in rr["revised_md"])
check("Output Contract 原文保留", "speak/board/formula" in rr["revised_md"])
check("change_summary 过滤禁改段", all("Output Contract" not in c["section"] for c in rr["change_summary"]))
calibrated = next(t for t in rr["revised_style_tags"] if t["text"] == "节奏舒缓")
check("revised_style_tags 校准落地", calibrated["confidence"] == _calibrate(0.7, 0, 3))
check("evidence 原样保留", calibrated["evidence"] == ["seg_0002"])

print()
if FAIL:
    print(f"FAILED: {len(FAIL)} — {FAIL}")
    sys.exit(1)
print(f"ALL {PASS} CHECKS PASSED")
