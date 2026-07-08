# -*- coding: utf-8 -*-
"""沙箱验证 skill 修订流程：run_revision（真 LLM）→ confirm_revision → H12 校验。

直接进程内调 evolution.py 的编排函数（绕过 HTTP 鉴权），
作用对象是 T_20990101_999 沙箱副本，跑完由调用方清理。
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Projects\EduNUWA\modules\M6_platform\backend")
sys.path.insert(0, r"D:\Projects\EduNUWA")

from dotenv import load_dotenv
load_dotenv(r"D:\Projects\EduNUWA\.env")

import evolution

TID = "T_20990101_999"
ROOT = Path(r"D:\Projects\EduNUWA\data")
skills_dir = ROOT / "teachers" / TID / "skills"

before_versions = sorted(os.listdir(skills_dir))
before_mtimes = {v: os.path.getmtime(skills_dir / v) for v in before_versions}
print("修订前版本目录:", before_versions)

# --- 生成修订提案（真 LLM） ---
r = evolution.run_revision(TID)
print("run_revision:", r["status"], r.get("message", ""))
assert r["status"] == "success", r
print("允许修订的段:", r["applied_sections"])
for c in r["change_summary"]:
    print(f"  [{c.get('section')}] {c.get('why', '')}")
    if c.get("before_excerpt"):
        print(f"    - {c['before_excerpt'][:80]}")
    if c.get("after_excerpt"):
        print(f"    + {c['after_excerpt'][:80]}")

pending_path = ROOT / "teachers" / TID / "evolution" / "pending_revision.json"
assert pending_path.exists(), "pending_revision.json 未落盘"
pending = json.loads(pending_path.read_text(encoding="utf-8"))
banned = {"Skill Purpose", "Output Contract", "Blackboard Policy", "Trigger"}
assert not any(any(b.lower() in str(c.get("section", "")).lower() for b in banned)
               for c in pending["change_summary"]), "change_summary 含禁改段！"
print("ok  pending 落盘且只涉及白名单段")

# --- 教师确认 → 落地新版本 ---
r2 = evolution.confirm_revision(TID)
print("confirm_revision:", r2["status"], "→ v" + str(r2.get("version")))
assert r2["status"] == "success", r2

after_versions = sorted(os.listdir(skills_dir))
new_dirs = set(after_versions) - set(before_versions)
assert len(new_dirs) == 1, f"应新增恰好一个版本目录: {new_dirs}"
new_v = new_dirs.pop()
print("新版本目录:", new_v)

# H12: 旧版本目录未被修改
for v in before_versions:
    assert os.path.getmtime(skills_dir / v) == before_mtimes[v], f"旧版本 {v} 被改动！"
print("ok  H12 旧版本目录未动")

new_profile = json.loads((skills_dir / new_v / "skill_profile.json").read_text(encoding="utf-8"))
assert new_profile["version"] == int(new_v[1:]), "version 字段与目录不一致"
assert new_profile.get("derived_from", "").endswith("+feedback")
assert new_profile.get("style_tags"), "新 profile 缺 style_tags"
assert all(t.get("source") in ("auto", "self") for t in new_profile["style_tags"]), \
    "crowd 标签混入 profile（违反 H14）！"
print("ok  新 profile: version=%s derived_from=%s style_tags=%d 条（无 crowd 混入）" % (
    new_profile["version"], new_profile["derived_from"], len(new_profile["style_tags"])))

new_md = (skills_dir / new_v / "TeacherSkill.md").read_text(encoding="utf-8")
assert "## Output Contract" in new_md or "Output Contract" in new_md, "七段结构被破坏"
print("ok  新 TeacherSkill.md 保留七段结构")

# confirm 后状态复位
calib = json.loads((ROOT / "teachers" / TID / "evolution" / "calibration.json").read_text(encoding="utf-8"))
assert calib["tags"] == {}, "calibration 未清零"
assert not pending_path.exists(), "pending 未删除"
print("ok  calibration 清零、pending 已删除")

print()
print("REVISION SANDBOX: ALL PASSED")
