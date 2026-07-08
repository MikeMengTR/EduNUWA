"""
测试：迁移后的真实课程数据，文本量是否够提炼出「完整的一套 skill」。

对每个测试老师：用其【全部转写】跑评价模型，组装 skill_profile，看：
  - style_tags 数量与质量（文本量最敏感的部分）
  - base_metrics（纯计算）
  - 组装出的 skill_profile 是否过 schema
  - 与文本量的关系：5000 字 vs 24000 字 标签丰富度差多少

用法：python scripts/test_skill_completeness.py [T_20260604_006 T_20260604_001 ...]
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from modules.M2_distill.metric_extractor import extract_base_metrics, extract_style_tags  # noqa: E402

TZ = timezone(timedelta(hours=8))
TEACHERS_DIR = REPO / "data" / "teachers"
SCHEMA = REPO / "modules" / "M2_distill" / "schemas" / "skill_profile_v2.schema.json"

DEFAULT = ["T_20260604_006", "T_20260604_001"]  # 线代(最少字) / 概率论(最多字)


def test_one(tid: str) -> None:
    tdir = TEACHERS_DIR / tid
    card = json.loads((tdir / "teacher_card.json").read_text(encoding="utf-8"))
    trs = sorted(tdir.glob("transcripts/TR_*.json"))
    total_chars = 0
    for tr in trs:
        d = json.loads(tr.read_text(encoding="utf-8"))
        total_chars += sum(len(s.get("text", "")) for s in d.get("segments", []))

    print(f"\n{'='*64}\n■ {card['display_name']}  ({tid})")
    print(f"  语料：{len(trs)} 份转写，约 {total_chars} 字")
    print(f"{'='*64}")

    # base_metrics（用第一份，纯计算）
    bm = extract_base_metrics(trs[0])
    bm_data = bm.get("base_metrics", {}) if bm.get("status") == "success" else {}
    print("  [base_metrics] " + "，".join(
        f"{k}={v['value']}{v['unit']}({v['label']})" for k, v in bm_data.items()))

    # style_tags（用全部转写合并，这才是「构建一套 skill」该用的全量语料）
    print(f"  [style_tagger] 用全部 {len(trs)} 份转写提炼中（调 LLM）...")
    st = extract_style_tags([str(t) for t in trs])
    if st["status"] != "success":
        print(f"    失败: {st['message']}")
        return
    tags = st["style_tags"]
    print(f"  [style_tags] 提炼出 {len(tags)} 个标签：")
    for t in tags:
        dim = t["dimension"] or "-"
        print(f"    · {t['text']:12s} [{dim}] conf={t['confidence']} 证据={t['evidence']}")
    if st["warnings"]:
        print(f"  warnings: {st['warnings']}")

    # 组装完整 skill_profile + schema 校验
    compact = tid.replace("_", "")
    profile = {
        "skill_id": f"S_{compact}_v1", "teacher_id": tid,
        "teacher_name": card["display_name"], "version": 1,
        "generated_at": datetime.now(TZ).isoformat(),
        "style_tags": tags, "style_embeddings_model": st["style_embeddings_model"],
        "base_metrics": bm_data,
        "pedagogy": {  # 占位（待探针/declared 注释补）
            "concept_entry": {"primary": "definition-first"},
            "intuition_building": {"order": "interleaved"},
            "analogy_density": {"level": "medium"},
            "blackboard_strategy": {"primary_layout": "title-bullets"},
            "misconception_alert": {"mode": "reactive-only"},
        },
        "quality": {"overall_grade": "NA", "publishable": False},
        "attributes": {"subject": card["subject"][0], "language": "zh"},
    }
    try:
        import jsonschema
        jsonschema.validate(profile, json.loads(SCHEMA.read_text(encoding="utf-8")))
        print(f"  [skill_profile] 组装完成，schema 校验 ✅  "
              f"(style_tags={len(tags)}, base_metrics={len(bm_data)}, pedagogy=占位, grade=NA)")
    except ImportError:
        print("  [skill_profile] 组装完成（jsonschema 未装，跳过校验）")
    # 落盘到 skills/v1
    out = tdir / "skills" / "v1"
    out.mkdir(parents=True, exist_ok=True)
    (out / "skill_profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  落盘: {out / 'skill_profile.json'}")


def main() -> int:
    tids = sys.argv[1:] or DEFAULT
    for tid in tids:
        test_one(tid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
