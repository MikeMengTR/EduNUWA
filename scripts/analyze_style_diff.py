"""
风格差异测试：对比 6 位完整蒸馏出的 TeacherSkill.md + skill_profile.json，
检查他们的讲解风格是否真有差异。

维度：
  1. style_tags 风格关键词（Jaccard 相似度 + 独特标签）
  2. pedagogy 5 维 enum 分布（教学法是否拉开）
  3. base_metrics（语速/互动）
  4. Teaching Philosophy / Speech Policy 文本摘录（人工可读对比）
"""
from __future__ import annotations

import json
import re
import sys
from itertools import combinations
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEACHERS_DIR = REPO / "data" / "teachers"
TIDS = [f"T_20260604_{i:03d}" for i in range(1, 7)]


def jaccard(a, b):
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if (sa | sb) else 0.0


def extract_section(md: str, header: str) -> str:
    """抽取 md 中某个 ## 段的正文。"""
    m = re.search(rf"##\s*{re.escape(header)}\s*\n(.+?)(?=\n##\s|\Z)", md, flags=re.S)
    return m.group(1).strip() if m else ""


def load_all() -> list[dict]:
    out = []
    for tid in TIDS:
        d = TEACHERS_DIR / tid / "skills" / "v2_full"
        prof = json.loads((d / "skill_profile.json").read_text(encoding="utf-8"))
        md = (d / "TeacherSkill.md").read_text(encoding="utf-8")
        ped = prof.get("pedagogy", {})
        out.append({
            "tid": tid,
            "name": prof.get("teacher_name", tid),
            "subject": prof.get("attributes", {}).get("subject", ""),
            "tags": [t["text"] for t in prof.get("style_tags", [])],
            "speech_rate": prof.get("base_metrics", {}).get("speech_rate", {}).get("label", "-"),
            "question_freq": prof.get("base_metrics", {}).get("question_freq", {}).get("label", "-"),
            "pedagogy": {
                "concept_entry": ped.get("concept_entry", {}).get("primary", "-"),
                "intuition": ped.get("intuition_building", {}).get("order", "-"),
                "analogy": ped.get("analogy_density", {}).get("level", "-"),
                "blackboard": ped.get("blackboard_strategy", {}).get("primary_layout", "-"),
                "misconception": ped.get("misconception_alert", {}).get("mode", "-"),
            },
            "philosophy": extract_section(md, "Teaching Philosophy"),
            "speech": extract_section(md, "Speech Policy"),
        })
    return out


def main() -> int:
    data = load_all()

    print("=" * 74)
    print("风格差异测试 · 6 位完整蒸馏老师")
    print("=" * 74)

    # 1. style_tags
    print("\n【1】风格关键词（style_tags）")
    for r in data:
        print(f"  {r['name']:18s} {'、'.join(r['tags'])}")
    sims = [jaccard(a["tags"], b["tags"]) for a, b in combinations(data, 2)]
    avg = sum(sims) / len(sims) if sims else 0
    print(f"  → 两两 Jaccard 均值 {avg:.2f}（<0.5 表区分良好）")

    # 2. pedagogy
    print("\n【2】教学法 pedagogy 5 维（驱动 AI 讲课的策略）")
    print(f"  {'老师':16s}{'概念引入':16s}{'直觉顺序':14s}{'类比':8s}{'板书':18s}{'易错提醒'}")
    for r in data:
        p = r["pedagogy"]
        print(f"  {r['name'][:7]:16s}{p['concept_entry']:16s}{p['intuition']:14s}{p['analogy']:8s}{p['blackboard']:18s}{p['misconception']}")
    # pedagogy 维度的取值多样性
    for dim in ["concept_entry", "intuition", "analogy", "blackboard", "misconception"]:
        vals = {r["pedagogy"][dim] for r in data}
        print(f"    {dim}: {len(vals)} 种取值 {sorted(vals)}")

    # 3. base_metrics
    print("\n【3】基础指标")
    for r in data:
        print(f"  {r['name']:18s} 语速:{r['speech_rate']:6s} 互动:{r['question_freq']}")

    # 4. Teaching Philosophy 首条 + Speech Policy 口头禅（文本对比）
    print("\n【4】Teaching Philosophy（教学信念，各取首条）")
    for r in data:
        first = r["philosophy"].split("\n")[0][:60] if r["philosophy"] else "(无)"
        print(f"  {r['name']:18s} {first}")

    # 健康判定
    print("\n" + "=" * 74)
    distinct_tags = len({tuple(sorted(r["tags"])) for r in data}) == len(data)
    distinct_ped = len({tuple(r["pedagogy"].values()) for r in data}) == len(data)
    ped_diversity = sum(len({r["pedagogy"][d] for r in data}) for d in
                        ["concept_entry", "intuition", "analogy", "blackboard", "misconception"])
    print(f"  风格关键词互不相同: {'✅' if distinct_tags else '❌'}")
    print(f"  教学法组合互不相同: {'✅' if distinct_ped else '❌'}")
    print(f"  style_tags Jaccard: {avg:.2f} {'✅' if avg < 0.5 else '❌'}")
    print(f"  pedagogy 总取值多样性: {ped_diversity}/25（越高越拉得开）")
    ok = distinct_tags and avg < 0.5
    print("\n  " + ("🎉 风格差异显著：6 位老师讲解风格各不相同" if ok else "⚠️ 风格区分度不足"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
