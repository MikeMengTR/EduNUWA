# -*- coding: utf-8 -*-
"""教学插图链路 端到端验证（需后端已在 5000 端口运行，且后端为含插图功能的新代码）。

覆盖：
  P1  /api/v1/media 文件服务：正常取图 200 + 正确 MIME + 长缓存头；
      路径穿越被拒；不支持的扩展名被拒
  P2  /demo/stream 提"导数的几何意义"：SSE 流中出现 image 事件（src 指向
      /api/v1/media/ 且可 GET 200）；事件落盘 events.json 含同一 image 事件
  P3  控制组：图库覆盖不到的主题（英语语法）不产生 image 事件，讲课正常

运行：
    & D:\\anaconda3\\envs\\edu\\python.exe scripts\\test_image_pipeline_e2e.py
注意：本机 Clash 代理会劫持 localhost，requests 必须 proxies=None。
P2/P3 各走一次真实 DeepSeek 生成（约 30~90s）。P2 中 LLM 理论上可自主选择
不配图，脚本对此重试一次；两次都不配图才判 FAIL。
"""
import json
import secrets
import sys
import time
from pathlib import Path

import requests

BASE = "http://localhost:5000/api/v1"
ROOT = Path(__file__).resolve().parents[1]
NO_PROXY = {"http": None, "https": None}
TEACHER_ID = sys.argv[1] if len(sys.argv) > 1 else "T_20260604_001"

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


def register_and_login():
    name = f"img_e2e_{secrets.token_hex(4)}"
    requests.post(f"{BASE}/auth/register", json={"username": name, "password": "test1234",
                                                 "role": "student"},
                  proxies=NO_PROXY, timeout=30)
    r = requests.post(f"{BASE}/auth/login", json={"username": name, "password": "test1234"},
                      proxies=NO_PROXY, timeout=30).json()
    assert r["code"] == 0, r
    return r["data"]["token"]


def stream_demo(token, question):
    """调 /demo/stream，返回 (session_id, events, error_frames)。"""
    resp = requests.post(
        f"{BASE}/chat/{TEACHER_ID}/demo/stream",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"question": question},
        stream=True, proxies=NO_PROXY, timeout=300,
    )
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:300]}"
    session_id, events, errors = None, [], []
    event_type = None
    for raw in resp.iter_lines(decode_unicode=True):
        if not raw or raw.startswith(":"):
            continue
        line = raw.strip("\r")
        if line.startswith("event:"):
            event_type = line[6:].strip()
        elif line.startswith("data:"):
            payload = json.loads(line[5:].strip())
            if event_type == "meta":
                session_id = payload.get("session_id")
            elif event_type == "event":
                events.append(payload)
            elif event_type == "error":
                errors.append(payload)
            event_type = None
    return session_id, events, errors


def main():
    # ---------- P1: /api/v1/media 文件服务 ----------
    print("P1: media 文件服务")
    r = requests.get(f"{BASE}/media/math/IMG_math_0001.png", proxies=NO_PROXY, timeout=30)
    check("取图 200", r.status_code == 200, f"HTTP {r.status_code}")
    check("MIME image/png", r.headers.get("Content-Type", "").startswith("image/png"),
          r.headers.get("Content-Type"))
    check("长缓存头", "max-age" in r.headers.get("Cache-Control", ""),
          r.headers.get("Cache-Control"))
    r = requests.get(f"{BASE}/media/physics/IMG_physics_0001.gif", proxies=NO_PROXY, timeout=30)
    check("取 GIF 200 + MIME", r.status_code == 200 and
          r.headers.get("Content-Type", "").startswith("image/gif"),
          f"HTTP {r.status_code} {r.headers.get('Content-Type')}")
    # 路径穿越（.. 编码绕过 URL 规范化）
    r = requests.get(f"{BASE}/media/..%2F..%2Fusers.json", proxies=NO_PROXY, timeout=30)
    check("路径穿越被拒", r.status_code != 200, f"HTTP {r.status_code}")
    r = requests.get(f"{BASE}/media/math/IMG_math_0001.txt", proxies=NO_PROXY, timeout=30)
    check("不支持的扩展名被拒", r.status_code == 400, f"HTTP {r.status_code}")

    token = register_and_login()

    # ---------- P2: demo/stream 出 image 事件 ----------
    print("P2: demo/stream 插图（真实 LLM 生成，约 30~90s）")
    image_events = []
    session_id = None
    for attempt in (1, 2):  # LLM 偶发不配图，重试一次
        t0 = time.time()
        session_id, events, errors = stream_demo(
            token, "导数的几何意义是什么？切线和割线有什么关系？")
        image_events = [e for e in events if e.get("type") == "image"]
        print(f"  尝试{attempt}: {len(events)} 事件（image×{len(image_events)}），"
              f"耗时 {time.time()-t0:.1f}s, errors={len(errors)}")
        if image_events:
            break
    check("流中出现 image 事件", bool(image_events),
          "两次生成均未配图（检查 prompt 注入/图库检索）")
    if image_events:
        img = image_events[0]
        check("image.src 指向 /api/v1/media/", str(img.get("src", "")).startswith("/api/v1/media/"),
              str(img))
        check("image 带 caption", bool(img.get("caption")), str(img))
        r = requests.get(f"http://localhost:5000{img['src']}", proxies=NO_PROXY, timeout=30)
        check("image.src 可 GET 200", r.status_code == 200, f"HTTP {r.status_code}")
        # 落盘 events.json 含同一事件
        ev_path = ROOT / "data" / "sessions" / session_id / "events.json"
        if ev_path.exists():
            persisted = json.loads(ev_path.read_text(encoding="utf-8"))
            check("events.json 落盘含 image",
                  any(e.get("type") == "image" for e in persisted.get("events", [])))
        else:
            check("events.json 落盘含 image", False, f"{ev_path} 不存在")

    # ---------- P3: 控制组（图库未覆盖主题，不应配图） ----------
    # 注意要选老师学科内的问题（学科外老师会一句话拒答），但关键词不命中图库
    print("P3: 控制组（集合运算，零候选）")
    _sid, events, _errors = stream_demo(token, "什么是集合的交集和并集？")
    check("控制组无 image 事件", all(e.get("type") != "image" for e in events),
          f"出现了 {[e for e in events if e.get('type') == 'image']}")
    check("控制组讲课正常（≥3 事件）", len(events) >= 3, f"只有 {len(events)} 事件")

    print(f"\n通过 {PASS}，失败 {len(FAIL)}{'：' + str(FAIL) if FAIL else ''}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
