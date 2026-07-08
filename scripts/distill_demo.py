"""
评价模型全真闭环 demo：真转写 → 自动评价 → 组装 skill_profile → 参与匹配。

对示例老师真实转写：
  1. base_metrics（纯计算，真）
  2. style_tags（LLM 提炼，真，带 seg 证据）
  3. 组装完整 skill_profile（pedagogy 为风格推断占位；grade=NA 因未跑探针）
  4. schema 校验 + 落盘到 mock_teachers
  5. 加载全部老师（含真蒸馏的示例老师）跑一个匹配 query，看真标签的匹配效果

跑法：python scripts/distill_demo.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.M2_distill.metric_extractor import extract_base_metrics, extract_style_tags  # noqa: E402
from modules.M3_catalog.matching_engine.matcher import load_teachers, match_teachers  # noqa: E402

TZ = timezone(timedelta(hours=8))
TRANSCRIPT = REPO / "data/teachers/T_legacy_001/transcripts/TR_Tlegacy001_001.json"
FIXTURES = REPO / "modules/M3_catalog/tests/fixtures/mock_teachers"
SCHEMA = REPO / "modules/M2_distill/schemas/skill_profile_v2.schema.json"


def distill(transcript_path: Path) -> dict:
    print(f"【真转写】{transcript_path.name}")
    bm = extract_base_metrics(transcript_path)
    assert bm["status"] == "success", bm
    print(f"  base_metrics（真计算）: " +
          "，".join(f"{k}={v['value']}{v['unit']}({v['label']})" for k, v in bm["base_metrics"].items()))

    print("  调 LLM 提炼 style_tags ...")
    st = extract_style_tags(transcript_path)
    assert st["status"] == "success", st
    print(f"  style_tags（真提炼，{len(st['style_tags'])} 个）: " +
          "、".join(t["text"] for t in st["style_tags"]))
    if st["warnings"]:
        print(f"  warnings: {st['warnings']}")

    # 组装完整 skill_profile。pedagogy 为风格推断占位（与提炼标签一致）；
    # grade=NA、省略 stability —— 因为蒸馏阶段未跑探针（正是 schema 的设计）。
    profile = {
        "skill_id": "S_Tlegacy001_v1",
        "teacher_id": "T_20260102_001",  # demo 用合规 id
        "teacher_name": "示例老师(真转写蒸馏)",
        "version": 1,
        "generated_at": datetime.now(TZ).isoformat(),
        "style_tags": st["style_tags"],
        "style_embeddings_model": st["style_embeddings_model"],
        "base_metrics": bm["base_metrics"],
        "pedagogy": {
            "concept_entry": {"primary": "problem-driven"},
            "intuition_building": {"order": "intuition-first", "before_formal": True},
            "analogy_density": {"level": "medium"},
            "blackboard_strategy": {"primary_layout": "title-bullets"},
            "misconception_alert": {"mode": "proactive-explicit"},
        },
        "quality": {"overall_grade": "NA", "publishable": False},  # 未跑探针
        "attributes": {"subject": "高等数学", "language": "zh"},
        "derived_from": "distill_demo (真 base_metrics + 真 style_tags + 占位 pedagogy)",
    }

    # schema 校验
    try:
        import jsonschema
        jsonschema.validate(profile, json.loads(SCHEMA.read_text(encoding="utf-8")))
        print("  schema 校验: 通过 ✅（grade=NA, 无 stability — 符合无探针设计）")
    except ImportError:
        print("  schema 校验: 跳过（jsonschema 未装）")

    # 落盘
    out = FIXTURES / profile["teacher_id"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "skill_profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  落盘: {out / 'skill_profile.json'}")
    return profile


def main() -> int:
    print("=" * 70)
    print("第 1 步：评价模型对真转写产出 skill_profile")
    print("=" * 70)
    distill(TRANSCRIPT)

    print("\n" + "=" * 70)
    print("第 2 步：把真蒸馏的示例老师放进候选池，跑匹配验证真标签能用")
    print("=" * 70)
    teachers = load_teachers(FIXTURES)
    print(f"候选池 {len(teachers)} 个老师（含真转写蒸馏的示例老师）")
    query = "我喜欢老师多设问、引导我思考，最好讲之前先抛个问题"
    print(f"\n【需求】{query}")
    res = match_teachers(query, teachers)
    if res["status"] != "success":
        print(f"匹配失败: {res['message']}")
        return 1
    for rank, r in enumerate(res["results"][:4], 1):
        fit = r.get("semantic_fit")
        fit_s = f"{fit:.2f}" if isinstance(fit, (int, float)) else str(fit)
        flag = " ← 真转写蒸馏" if r["teacher_id"] == "T_20260102_001" else ""
        print(f"  {rank}. {r['teacher_name']}  贴合度={fit_s}{flag}")
        print(f"     {r['reason']}")
        if r["matched_tags"]:
            print(f"     命中: {'、'.join(r['matched_tags'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
