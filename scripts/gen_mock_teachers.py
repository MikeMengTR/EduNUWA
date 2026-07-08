"""
快速造 6 个不同风格的老师 skill_profile_v2.json 样例（demo 用）。

每个老师风格鲜明、可区分，让匹配模型能演示「不同需求→不同排序」。
全部按 skill_profile_v2.schema.json 组装并校验。

落盘：modules/M3_catalog/tests/fixtures/mock_teachers/{teacher_id}/skill_profile.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "modules" / "M3_catalog" / "tests" / "fixtures" / "mock_teachers"
SCHEMA = REPO / "modules" / "M2_distill" / "schemas" / "skill_profile_v2.schema.json"
TZ = timezone(timedelta(hours=8))
MODEL = "bge-base-zh-v1.5"

# 每个老师：风格标签（text, dimension）、语速、互动频次、教学法、grade
TEACHERS = [
    {
        "tid": "T_20260101_001", "name": "示例老师", "subject": "高等数学",
        "tags": [("设问自答", "interactivity"), ("爱用生活类比", "abstraction"),
                 ("先直觉后定义", "abstraction"), ("主动拦截易错点", "rigor")],
        "speech_rate": 233.7, "question_freq": 8.0,
        "ped": ("problem-driven", "intuition-first", "high", "title-bullets", "proactive-explicit"),
        "grade": "A-",
    },
    {
        "tid": "T_20260101_002", "name": "李博", "subject": "高等数学",
        "tags": [("干脆利落", "pace"), ("直击考点", "detail"),
                 ("重解题套路", "rigor"), ("节奏明快", "pace")],
        "speech_rate": 320.0, "question_freq": 1.5,
        "ped": ("definition-first", "formal-first", "low", "derivation-flow", "reactive-only"),
        "grade": "B+",
    },
    {
        "tid": "T_20260101_003", "name": "王逗", "subject": "大学物理",
        "tags": [("风趣幽默", "humor"), ("爱讲段子", "humor"),
                 ("活跃气氛", "humor"), ("贴近生活", "abstraction")],
        "speech_rate": 240.0, "question_freq": 4.0,
        "ped": ("phenomenon-driven", "interleaved", "high", "mind-map", "proactive-implicit"),
        "grade": "B+",
    },
    {
        "tid": "T_20260101_004", "name": "陈衡", "subject": "数学分析",
        "tags": [("推导严密", "rigor"), ("重形式定义", "abstraction"),
                 ("逻辑滴水不漏", "rigor"), ("理论先行", "abstraction")],
        "speech_rate": 150.0, "question_freq": 1.0,
        "ped": ("definition-first", "formal-first", "low", "derivation-flow", "proactive-explicit"),
        "grade": "A",
    },
    {
        "tid": "T_20260101_005", "name": "林暖", "subject": "高等数学",
        "tags": [("娓娓道来", "pace"), ("极有耐心", "pace"),
                 ("细致入微", "detail"), ("鼓励式教学", "interactivity")],
        "speech_rate": 140.0, "question_freq": 3.0,
        "ped": ("problem-driven", "intuition-first", "medium", "title-bullets", "proactive-explicit"),
        "grade": "B+",
    },
    {
        "tid": "T_20260101_006", "name": "赵问", "subject": "线性代数",
        "tags": [("苏格拉底式", "interactivity"), ("步步追问", "interactivity"),
                 ("引导思考", "interactivity"), ("从不直接给答案", "interactivity")],
        "speech_rate": 210.0, "question_freq": 12.0,
        "ped": ("problem-driven", "interleaved", "medium", "mind-map", "proactive-implicit"),
        "grade": "A-",
    },
]

_BANDS = json.loads((REPO / "modules/M2_distill/metric_extractor/rubric/base_metrics_bands.json").read_text(encoding="utf-8"))


def _band(metric: str, value: float) -> tuple[str, str]:
    for b in _BANDS[metric]:
        if b["max"] is None or value < b["max"]:
            return b["label"], b["polarity"]
    last = _BANDS[metric][-1]
    return last["label"], last["polarity"]


def build_profile(t: dict) -> dict:
    compact = t["tid"].replace("_", "")
    sr_label, sr_pol = _band("speech_rate", t["speech_rate"])
    qf_label, qf_pol = _band("question_freq", t["question_freq"])
    ce, ib, ad, bs, ma = t["ped"]
    return {
        "skill_id": f"S_{compact}_v1",
        "teacher_id": t["tid"],
        "teacher_name": t["name"],
        "version": 1,
        "generated_at": datetime.now(TZ).isoformat(),
        "style_tags": [
            {"text": txt, "dimension": dim, "source": "auto",
             "confidence": 0.8, "evidence": ["seg_0001", "seg_0005"], "cluster_id": None}
            for txt, dim in t["tags"]
        ],
        "style_embeddings_model": MODEL,
        "base_metrics": {
            "speech_rate": {"value": t["speech_rate"], "unit": "字/分", "label": sr_label, "polarity": sr_pol},
            "question_freq": {"value": t["question_freq"], "unit": "次/10分钟", "label": qf_label, "polarity": qf_pol},
        },
        "pedagogy": {
            "concept_entry": {"primary": ce},
            "intuition_building": {"order": ib, "before_formal": ib == "intuition-first"},
            "analogy_density": {"level": ad},
            "blackboard_strategy": {"primary_layout": bs},
            "misconception_alert": {"mode": ma},
        },
        "quality": {
            "stability": {
                "declared_observed_consistency": 0.85,
                "cross_probe_consistency": 0.9,
                "cross_layer_consistency": 0.82,
            },
            "overall_grade": t["grade"],
            "publishable": True,
        },
        "attributes": {"subject": t["subject"], "language": "zh"},
        "derived_from": "gen_mock_teachers (demo fixture)",
    }


def main() -> int:
    try:
        import jsonschema
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    except ImportError:
        schema = None
        print("[WARN] jsonschema 未装，跳过校验")

    OUT.mkdir(parents=True, exist_ok=True)
    for t in TEACHERS:
        prof = build_profile(t)
        if schema is not None:
            jsonschema.validate(prof, schema)
        d = OUT / t["tid"]
        d.mkdir(exist_ok=True)
        (d / "skill_profile.json").write_text(
            json.dumps(prof, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] {t['name']:4s} {t['tid']}  grade={t['grade']}  "
              f"tags={len(prof['style_tags'])}  schema={'通过' if schema else '跳过'}")
    print(f"\n共 {len(TEACHERS)} 个老师 → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
