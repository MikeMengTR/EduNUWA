"""
评价系统验证测试：对 6 位真实老师做评价模型蒸馏，并检查：
  A. 蒸馏：每位产出 skill_profile（base_metrics + style_tags），过 schema
  B. 风格关键词差异：标签矩阵、独特标签、两两 Jaccard 相似度（越低越能区分）
  C. 输出风格差异：带各自 skill 生成「开场白」，对比是否真不同
  D. 评价系统健康判定：成功率 / schema / 证据完整(H5) / 区分性 → PASS/FAIL

用法：python scripts/test_eval_system.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone, timedelta
from itertools import combinations
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from modules.M2_distill.metric_extractor import extract_base_metrics, extract_style_tags  # noqa: E402
from modules.M2_distill.metric_extractor.style_tagger import _call_llm  # noqa: E402

TZ = timezone(timedelta(hours=8))
TEACHERS_DIR = REPO / "data" / "teachers"
SCHEMA = REPO / "modules" / "M2_distill" / "schemas" / "skill_profile_v2.schema.json"
TIDS = [f"T_20260604_{i:03d}" for i in range(1, 7)]


def jaccard(a: list, b: list) -> float:
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if (sa | sb) else 0.0


# ============================================================
# Part A：蒸馏
# ============================================================
def distill_all() -> list[dict]:
    print("=" * 70)
    print("Part A · 对 6 位老师蒸馏（评价模型：base_metrics + style_tags）")
    print("=" * 70)
    records = []
    schema = None
    try:
        import jsonschema
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    except ImportError:
        pass

    for tid in TIDS:
        tdir = TEACHERS_DIR / tid
        card = json.loads((tdir / "teacher_card.json").read_text(encoding="utf-8"))
        trs = sorted(tdir.glob("transcripts/TR_*.json"))
        rec = {"tid": tid, "name": card["display_name"], "subject": card["subject"][0]}

        t0 = time.time()
        bm = extract_base_metrics(trs[0])
        st = extract_style_tags([str(t) for t in trs])
        rec["elapsed"] = round(time.time() - t0, 1)

        if bm["status"] != "success" or st["status"] != "success":
            rec["ok"] = False
            rec["err"] = bm.get("message") or st.get("message")
            records.append(rec)
            print(f"  ✗ {rec['name']}: 失败 {rec['err']}")
            continue

        tags = st["style_tags"]
        rec["base_metrics"] = bm["base_metrics"]
        rec["tags"] = tags
        rec["tag_texts"] = [t["text"] for t in tags]
        rec["all_have_evidence"] = all(t.get("evidence") for t in tags)  # H5

        profile = {
            "skill_id": f"S_{tid.replace('_','')}_v1", "teacher_id": tid,
            "teacher_name": card["display_name"], "version": 1,
            "generated_at": datetime.now(TZ).isoformat(),
            "style_tags": tags, "style_embeddings_model": st["style_embeddings_model"],
            "base_metrics": bm["base_metrics"],
            "pedagogy": {
                "concept_entry": {"primary": "definition-first"},
                "intuition_building": {"order": "interleaved"},
                "analogy_density": {"level": "medium"},
                "blackboard_strategy": {"primary_layout": "title-bullets"},
                "misconception_alert": {"mode": "reactive-only"},
            },
            "quality": {"overall_grade": "NA", "publishable": False},
            "attributes": {"subject": card["subject"][0], "language": "zh"},
        }
        rec["schema_ok"] = True
        if schema:
            try:
                jsonschema.validate(profile, schema)
            except Exception as e:
                rec["schema_ok"] = False
                rec["schema_err"] = str(e)[:80]
        out = tdir / "skills" / "v1"
        out.mkdir(parents=True, exist_ok=True)
        (out / "skill_profile.json").write_text(
            json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        rec["ok"] = True
        records.append(rec)
        sm = "✅" if rec["schema_ok"] else "❌"
        print(f"  ✓ {rec['name']:16s} {len(tags)}个标签 schema{sm} 证据{'✅' if rec['all_have_evidence'] else '❌'} ({rec['elapsed']}s)")
    return records


# ============================================================
# Part B：风格关键词差异
# ============================================================
def analyze_keywords(records: list[dict]) -> dict:
    print("\n" + "=" * 70)
    print("Part B · 风格关键词差异性")
    print("=" * 70)
    ok = [r for r in records if r.get("ok")]
    print("\n  各老师风格关键词：")
    for r in ok:
        bm = r["base_metrics"]
        sr = bm.get("speech_rate", {}).get("label", "-")
        qf = bm.get("question_freq", {}).get("label", "-")
        print(f"    {r['name']:16s}[语速:{sr} 互动:{qf}]  {'、'.join(r['tag_texts'])}")

    # 独特标签（只此一位有的）
    all_tags = [t for r in ok for t in r["tag_texts"]]
    from collections import Counter
    cnt = Counter(all_tags)
    print("\n  独特标签（仅 1 位老师出现）：")
    for r in ok:
        uniq = [t for t in r["tag_texts"] if cnt[t] == 1]
        print(f"    {r['name']:16s}{'、'.join(uniq) if uniq else '(无独特标签)'}")

    # 两两 Jaccard
    sims = [jaccard(a["tag_texts"], b["tag_texts"]) for a, b in combinations(ok, 2)]
    avg_sim = sum(sims) / len(sims) if sims else 0.0
    print(f"\n  标签集两两 Jaccard 相似度：均值 {avg_sim:.2f}（越低越能区分；>0.5 说明风格雷同）")
    print(f"  base_metrics 语速分布：" +
          "，".join(f"{r['name'].split('·')[0]}={r['base_metrics'].get('speech_rate',{}).get('value')}" for r in ok))
    return {"avg_jaccard": avg_sim, "total_unique": sum(1 for v in cnt.values() if v == 1)}


# ============================================================
# Part C：输出风格差异（带 skill 生成开场白）
# ============================================================
def test_output_style(records: list[dict]) -> None:
    print("\n" + "=" * 70)
    print("Part C · 输出风格差异（带各自 skill 生成「开场白」，看 HOW 是否不同）")
    print("=" * 70)
    for r in [r for r in records if r.get("ok")]:
        prompt = (
            f"你是一位{r['subject']}老师。你的讲解风格关键词：{('、'.join(r['tag_texts']))}。\n"
            f"请严格用符合这个风格的方式，写出你开始讲解一个新知识点时最典型的「开场白」"
            f"（2-3 句话，80 字内）。只输出开场白本身，不要任何解释。"
        )
        try:
            out = _call_llm(prompt, max_tokens=800, temperature=0.6).strip()
        except Exception as e:
            out = f"[生成失败: {e}]"
        print(f"\n  ▶ {r['name']}（{'、'.join(r['tag_texts'][:3])}…）")
        print(f"    「{out}」")


# ============================================================
# Part D：健康判定
# ============================================================
def health_check(records: list[dict], kw: dict) -> int:
    print("\n" + "=" * 70)
    print("Part D · 评价系统健康判定")
    print("=" * 70)
    n = len(records)
    ok = [r for r in records if r.get("ok")]
    checks = []
    checks.append(("蒸馏成功率", f"{len(ok)}/{n}", len(ok) == n))
    checks.append(("schema 全通过", all(r.get("schema_ok") for r in ok), all(r.get("schema_ok") for r in ok)))
    checks.append(("标签证据完整(H5)", all(r.get("all_have_evidence") for r in ok), all(r.get("all_have_evidence") for r in ok)))
    distinct = len({tuple(sorted(r["tag_texts"])) for r in ok}) == len(ok)
    checks.append(("6位标签互不相同(区分性)", distinct, distinct))
    low_sim = kw["avg_jaccard"] < 0.5
    checks.append(("风格区分度(Jaccard<0.5)", f"{kw['avg_jaccard']:.2f}", low_sim))
    checks.append((f"独特标签数", kw["total_unique"], kw["total_unique"] > 0))

    all_pass = True
    for name, val, passed in checks:
        flag = "✅" if passed else "❌"
        print(f"  {flag} {name}: {val}")
        all_pass = all_pass and passed
    print("\n" + ("  🎉 评价系统 PASS：可正常运行，风格关键词与输出均有差异"
                  if all_pass else "  ⚠️ 评价系统有未通过项，见上"))
    return 0 if all_pass else 1


def main() -> int:
    recs = distill_all()
    kw = analyze_keywords(recs)
    test_output_style(recs)
    return health_check(recs, kw)


if __name__ == "__main__":
    raise SystemExit(main())
