# -*- coding: utf-8 -*-
"""虚拟课堂流式教学演示 E2E 验收（Playwright）。

前置：后端 5000 + 前端 vite 3000 已启动；存在学生账号 stream_test/test1234。
验收点：
  1. 提问后 push 模式 iframe 秒级出现（meta 帧到达即装载）
  2. 黑板逐条上屏（事件增量推入，而非一次性全量）
  3. M5 状态从「老师正在思考…」转入「讲解中…」（首句 TTS 播放）
  4. 占位气泡被 summary 替换
  5. 流中连发第二问：旧流被 abort、新课正常开始

运行: D:\\anaconda3\\envs\\edu\\python.exe modules\\M6_platform\\test_e2e_stream.py
"""
import sys
import time

from playwright.sync_api import sync_playwright

BASE = "http://localhost:3000"
TEACHER = "T_20260604_001"
USER, PWD = "stream_test", "test1234"

PASS, FAIL = [], []
T0 = [time.time()]  # 供网络监听打点（list 便于重置）


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


def get_frame(page):
    """拿到当前前台的 /runtime/ push 模式 frame。"""
    for f in page.frames:
        if "push=1" in f.url:
            return f
    return None


def main():
    with sync_playwright() as p:
        # channel="msedge"：用系统 Edge，免下载 playwright 自带 chromium
        # --no-proxy-server：绕过系统代理（如 Clash），否则 localhost 请求可能
        # 被代理劫持，SSE 长连接出现 30s 延迟 / Failed to fetch
        browser = p.chromium.launch(channel="msedge", args=[
            "--autoplay-policy=no-user-gesture-required", "--mute-audio",
            "--no-proxy-server"])
        page = browser.new_page()
        console_lines = []
        page.on("console", lambda m: console_lines.append(m.text))
        page.on("pageerror", lambda e: print(f"  [pageerror] {e}"))
        page.on("response", lambda r: "/demo" in r.url
                and print(f"  [resp t+{time.time()-T0[0]:.1f}s] {r.status} {r.url[:90]}"))
        page.on("request", lambda r: "/demo" in r.url
                and print(f"  [req  t+{time.time()-T0[0]:.1f}s] {r.method} {r.url[:90]}"))

        # ---- 登录 ----
        page.goto(f"{BASE}/login")
        page.fill('input[placeholder="请输入用户名"]', USER)
        page.fill('input[placeholder="请输入密码"]', PWD)
        page.click('button[type="submit"]')
        page.wait_for_url("**/student**", timeout=15000)
        print("登录成功")

        # ---- 进入虚拟课堂，发起流式演示 ----
        page.goto(f"{BASE}/classroom/{TEACHER}")
        page.wait_for_selector(".vcx__input", timeout=15000)
        page.fill(".vcx__input", "什么是条件概率")
        t0 = time.time()
        T0[0] = t0
        page.press(".vcx__input", "Enter")

        # 1. push iframe 秒级出现
        page.wait_for_selector('iframe[src*="push=1"]', timeout=20000)
        t_iframe = time.time() - t0
        check("push iframe 秒级装载", t_iframe < 8, f"({t_iframe:.1f}s)")

        # 占位气泡先出现
        try:
            page.wait_for_selector('.vcx__bubble--demo', timeout=10000)
            placeholder = page.locator('.vcx__bubble--demo').last.inner_text()
            check("占位气泡出现", "备课" in placeholder or "讲解" in placeholder,
                  f"({placeholder[:20]}...)")
        except Exception as e:
            check("占位气泡出现", False, str(e))

        # 2. 黑板逐条上屏：记录板书条数随时间增长
        frame = None
        for _ in range(40):
            frame = get_frame(page)
            if frame:
                break
            page.wait_for_timeout(500)
        check("找到 push 模式 frame", frame is not None)

        growth = []
        first_board_t = None
        for _ in range(300):  # 最多观察 150s（GPU 冷启动时首句 TTS 可达 50s+）
            try:
                n = frame.locator(".board-item-wrapper").count()
            except Exception:
                n = 0
            if n and first_board_t is None:
                first_board_t = time.time() - t0
            if not growth or n != growth[-1][1]:
                growth.append((round(time.time() - t0, 1), n))
            status = ""
            try:
                status = frame.locator(".control-status").inner_text()
            except Exception:
                pass
            if status == "讲解结束":
                break
            page.wait_for_timeout(500)
            # 板书已涨到 >=4 条且出现过 >=3 个不同计数，足以证明增量
            if len([g for g in growth if g[1] > 0]) >= 3 and growth[-1][1] >= 4:
                break

        incremental = len([g for g in growth if g[1] > 0]) >= 2
        check("首条板书快速上屏", first_board_t is not None and first_board_t < 15,
              f"({first_board_t and round(first_board_t, 1)}s)")
        check("黑板逐条增量上屏", incremental, f"增长轨迹={growth}")

        # 3. 状态进入「讲解中…」（首句音频开始播放）
        speaking = False
        for _ in range(120):
            try:
                st = frame.locator(".control-status").inner_text()
                if st in ("讲解中…", "讲解结束"):
                    speaking = True
                    break
            except Exception:
                pass
            page.wait_for_timeout(500)
        t_speak = time.time() - t0
        check("首句开口（讲解中…）", speaking, f"({t_speak:.1f}s)")

        # 4. summary 替换占位气泡
        summary_ok = False
        summary_text = ""
        for _ in range(90):
            summary_text = page.locator('.vcx__bubble--demo').last.inner_text()
            if "备课" not in summary_text and len(summary_text) > 20:
                summary_ok = True
                break
            page.wait_for_timeout(1000)
        check("summary 替换占位气泡", summary_ok, f"({summary_text[:30]}...)")

        # 5. 连发第二问：旧流 abort、新 session 开始
        old_frame_url = frame.url
        page.fill(".vcx__input", "什么是全概率公式")
        page.press(".vcx__input", "Enter")
        new_session_ok = False
        # 75s 窗口：容忍本机代理环境下偶发的 30s TCP 连接重试 + meta 超时降级（12s+16s）
        # 降级（非流式）时新 frame 不带 push=1，按 /runtime/ 匹配
        for _ in range(150):
            f2 = next((f for f in page.frames if "/runtime/" in f.url), None)
            if f2 and f2.url != old_frame_url:
                new_session_ok = True
                break
            page.wait_for_timeout(500)
        check("连问切换新会话", new_session_ok,
              "" if new_session_ok else f"帧列表={[f.url[:90] for f in page.frames]}")
        if not new_session_ok:
            print("  最近 console:", [c[:120] for c in console_lines[-8:]])
        if new_session_ok:
            f2 = get_frame(page)
            board_ok = False
            for _ in range(80):
                try:
                    if f2.locator(".board-item-wrapper").count() > 0:
                        board_ok = True
                        break
                except Exception:
                    pass
                page.wait_for_timeout(500)
            check("新会话黑板正常上屏", board_ok)

        browser.close()

    print(f"\n===== 通过 {len(PASS)} / 失败 {len(FAIL)} =====")
    if FAIL:
        print("失败项:", FAIL)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
