# -*- coding: utf-8 -*-
"""教学插图黑板渲染 浏览器级验收（Playwright）。

前置：后端 5000 已启动（M5 前端 dist 已构建，含 image 渲染组件）。
做法：构造一个含 image 事件的测试 session events.json，直接加载
/runtime/?stream=1 播放，断言黑板出现 <figure.board-image>、图片真实
加载成功（naturalWidth > 0）、caption 文本正确。不依赖 M6 前端(3000)。

运行: D:\\anaconda3\\envs\\edu\\python.exe modules\\M6_platform\\test_image_browser.py
"""
import json
import secrets
import shutil
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://localhost:5000"
NO_PROXY = {"http": None, "https": None}
TEACHER = "T_20260604_001"

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


def main():
    # ---- 登录拿 token（events.json 走 /api/v1/audio 需鉴权） ----
    user = f"img_ui_{secrets.token_hex(3)}"
    requests.post(f"{BASE}/api/v1/auth/register",
                  json={"username": user, "password": "test1234", "role": "student"},
                  proxies=NO_PROXY, timeout=30)
    r = requests.post(f"{BASE}/api/v1/auth/login",
                      json={"username": user, "password": "test1234"},
                      proxies=NO_PROXY, timeout=30).json()
    token = r["data"]["token"]

    # ---- 构造测试 session：image 排 seq=1，不等 TTS 即上屏 ----
    sid = f"SES_{time.strftime('%Y%m%d%H%M%S')}_uitest"
    sdir = ROOT / "data" / "sessions" / sid
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "events.json").write_text(json.dumps({
        "session_id": sid, "teacher_id": TEACHER, "voice_id": "",
        "events": [
            {"seq": 1, "type": "image", "image_id": "IMG_math_0001",
             "src": "/api/v1/media/math/IMG_math_0001.png",
             "media_type": "static", "caption": "切线示意图（UI测试）"},
            {"seq": 2, "type": "board", "action": "write_title", "content": "导数的几何意义"},
        ],
    }, ensure_ascii=False), encoding="utf-8")

    url = (f"{BASE}/runtime/?stream=1&events=/api/v1/audio/{sid}/events.json"
           f"&teacherId={TEACHER}&token={token}&teacherName=UI%E6%B5%8B%E8%AF%95")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", args=[
                "--autoplay-policy=no-user-gesture-required", "--mute-audio",
                "--no-proxy-server"])
            page = browser.new_page()
            page.on("pageerror", lambda e: print(f"  [pageerror] {e}"))
            page.goto(url)

            page.wait_for_selector("figure.board-image img", timeout=30000)
            check("黑板出现 board-image", True)

            loaded = False
            for _ in range(40):
                loaded = page.eval_on_selector(
                    "figure.board-image img",
                    "img => img.complete && img.naturalWidth > 0")
                if loaded:
                    break
                page.wait_for_timeout(250)
            check("图片真实加载（naturalWidth>0）", loaded)

            cap = page.locator(".board-image-caption").inner_text()
            check("caption 渲染正确", cap == "切线示意图（UI测试）", f"({cap})")

            # image dwell 3s 后推进到下一事件：板书标题也应上屏
            board_ok = False
            for _ in range(40):
                if page.locator(".board-title").count() > 0:
                    board_ok = True
                    break
                page.wait_for_timeout(250)
            check("image 后续事件正常推进（标题上屏）", board_ok)

            browser.close()
    finally:
        shutil.rmtree(sdir, ignore_errors=True)

    print(f"\n===== 通过 {len(PASS)} / 失败 {len(FAIL)} =====")
    if FAIL:
        print("失败项:", FAIL)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
