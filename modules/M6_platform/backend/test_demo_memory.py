# -*- coding: utf-8 -*-
"""demo 模式对话记忆验收：

  1. 新学生首问 → 开场语不得编造"刚才我们聊了…"
  2. 第二问"那泊松分布会用于什么" → 衔接语应真实引用第一问（二项分布）
  3. 第三问"我们刚刚聊了什么" → 应简要回顾，而非编排新课
  4. conversations.json 中产生 demo 历史条目

运行: D:\\anaconda3\\envs\\edu\\python.exe modules\\M6_platform\\backend\\test_demo_memory.py
"""
import json
import secrets
import sys
import time

import requests

BASE = "http://localhost:5000/api/v1"
TEACHER = "T_20260604_001"
NO_PROXY = {"http": None, "https": None}  # 本机 Clash 代理会劫持 localhost


def stream_demo(token, question):
    """调流式 demo，返回 (events, summary)。"""
    r = requests.post(f"{BASE}/chat/{TEACHER}/demo/stream",
                      headers={"Authorization": f"Bearer {token}"},
                      json={"question": question}, stream=True, timeout=180, proxies=NO_PROXY)
    assert r.status_code == 200, r.text[:200]
    events, summary = [], ""
    etype = None
    for line in r.iter_lines(decode_unicode=True):
        if not line:
            continue
        if line.startswith("event:"):
            etype = line[6:].strip()
        elif line.startswith("data:"):
            d = json.loads(line[5:])
            if etype == "event":
                events.append(d)
            elif etype == "summary":
                summary = d.get("text", "")
            etype = None
    return events, summary


def speak_text(events):
    return " ".join(e.get("text", "") for e in events if e.get("type") == "speak")


def main():
    user = f"mem_{secrets.token_hex(3)}"
    requests.post(f"{BASE}/auth/register",
                  json={"username": user, "password": "t12345", "role": "student"}, proxies=NO_PROXY)
    token = requests.post(f"{BASE}/auth/login",
                          json={"username": user, "password": "t12345"},
                          proxies=NO_PROXY).json()["data"]["token"]
    print(f"新学生: {user}")
    results = []

    # ---- 1. 首问：不得编造前情 ----
    ev1, sum1 = stream_demo(token, "什么是二项分布")
    fabricated = any(k in sum1 for k in ("刚才我们", "上节课", "上次我们", "之前我们聊"))
    results.append(("首问不编造衔接", not fabricated, sum1[:60]))
    print(f"[{'PASS' if not fabricated else 'FAIL'}] 首问开场语: {sum1[:80]}")

    # ---- 2. 第二问：应真实衔接二项分布 ----
    ev2, sum2 = stream_demo(token, "那泊松分布会用于什么")
    text2 = sum2 + speak_text(ev2)
    linked = "二项" in text2
    results.append(("第二问衔接二项分布", linked, sum2[:60]))
    print(f"[{'PASS' if linked else 'FAIL'}] 第二问开场语: {sum2[:80]}")

    # ---- 3. meta 问题：应回顾而非新课 ----
    ev3, sum3 = stream_demo(token, "我们刚刚聊了什么")
    text3 = speak_text(ev3)
    mentions = ("二项" in text3 or "泊松" in text3)
    # 回顾应明显短于正课（正课通常 12+ 事件），且不该出现「第1讲」式新课结构
    short = len(ev3) <= 8
    ok3 = mentions and short
    results.append(("meta 问题回顾对话", ok3, f"events={len(ev3)} 提及前文={mentions}"))
    print(f"[{'PASS' if ok3 else 'FAIL'}] meta 问题: events={len(ev3)}, 提及前文={mentions}")
    print(f"  回顾内容: {text3[:160]}")

    # ---- 4. 历史落盘 ----
    hist = requests.get(f"{BASE}/chat/{TEACHER}/history",
                        headers={"Authorization": f"Bearer {token}"}, proxies=NO_PROXY).json()["data"]
    demo_entries = [m for m in hist if m.get("kind") == "demo"]
    ok4 = len(hist) >= 6 and len(demo_entries) >= 3
    results.append(("历史落盘", ok4, f"共{len(hist)}条/demo {len(demo_entries)}条"))
    print(f"[{'PASS' if ok4 else 'FAIL'}] 历史落盘: 共 {len(hist)} 条, demo 条目 {len(demo_entries)}")

    failed = [n for n, ok, _ in results if not ok]
    print(f"\n===== 通过 {len(results)-len(failed)} / 失败 {len(failed)} =====")
    if failed:
        print("失败项:", failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
