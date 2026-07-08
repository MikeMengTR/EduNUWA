# -*- coding: utf-8 -*-
"""定向验证：两名学生的同质风格反馈 → 众评标签晋升 live → match 消费。"""
import json
import secrets
import sys
import time
from pathlib import Path

import requests

BASE = "http://localhost:5000/api/v1"
ROOT = Path(__file__).resolve().parents[1]
NO_PROXY = {"http": None, "https": None}
TID = "T_20260604_001"


def api(method, path, token=None, **kw):
    headers = kw.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.request(method, f"{BASE}{path}", headers=headers,
                            proxies=NO_PROXY, timeout=180, **kw).json()


def student():
    name = f"evo_p_{secrets.token_hex(4)}"
    api("POST", "/auth/register", json={"username": name, "password": "test1234", "role": "student"})
    return api("POST", "/auth/login", json={"username": name, "password": "test1234"})["data"]["token"]


def runs_total(token):
    return api("GET", f"/teachers/{TID}/evolution/status", token=token)["data"]["runs_total"]


s1, s2 = student(), student()
base_runs = runs_total(s1)

# 触发阈值是 5 条未处理反馈；垫底的 3 条用第三个学生发、且放在前面
# （进化器对同一学生只取最新一条，有效信号必须是 s1/s2 的最后一条）
s3 = student()
for i in range(3):
    api("POST", f"/teachers/{TID}/feedback", token=s3,
        json={"rating": 4, "comment": f"凑数评论{i}：还行"})

# 两名学生都明确描述「幽默爱讲段子」这一新风格特点（现有标签未覆盖 humor 维度）
api("POST", f"/teachers/{TID}/feedback", token=s1,
    json={"rating": 5, "comment": "老师讲课特别幽默，时不时冒出几个冷笑话，完全不会犯困"})
r = api("POST", f"/teachers/{TID}/feedback", token=s2,
        json={"rating": 5, "comment": "经常用小段子活跃气氛，课堂氛围轻松，听着很有意思"})
print("提交完成", r["code"])

# 等自动进化跑完（触发在 POST 后）
deadline = time.time() + 150
while time.time() < deadline and runs_total(s1) <= base_runs:
    time.sleep(5)
status = api("GET", f"/teachers/{TID}/evolution/status", token=s1)["data"]
print(f"runs {base_runs} -> {status['runs_total']}, err={status.get('last_error')}")

live = status.get("live_tags", [])
pending_path = ROOT / "data" / "teachers" / TID / "evolution" / "pending_tags.json"
pending = json.loads(pending_path.read_text(encoding="utf-8")) if pending_path.exists() else []
print("live 标签:", [(t["text"], t["support"]) for t in live])
print("候补池:", [(p["text"], len(p.get("student_hashes", []))) for p in pending])

ok = status["runs_total"] > base_runs and not status.get("last_error")
KEYS = ("幽默", "段子", "笑话", "轻松")
promoted = any(any(k in t["text"] for k in KEYS) for t in live)
pooled = any(any(k in p["text"] for k in KEYS) for p in pending)
print("RESULT:", "PROMOTED" if promoted else ("POOLED(候补)" if pooled else "NO_TAG"))
sys.exit(0 if (ok and (promoted or pooled)) else 1)
