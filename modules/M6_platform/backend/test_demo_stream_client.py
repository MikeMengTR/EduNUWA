# -*- coding: utf-8 -*-
"""/demo/stream 的命令行验收客户端：打印每个 SSE 帧的到达时刻与摘要。

用法: python test_demo_stream_client.py <token> [teacher_id] [question]
"""
import json
import sys
import time

import requests


def main():
    token = sys.argv[1]
    teacher_id = sys.argv[2] if len(sys.argv) > 2 else "T_20260604_001"
    question = sys.argv[3] if len(sys.argv) > 3 else "什么是正态分布"

    url = f"http://localhost:5000/api/v1/chat/{teacher_id}/demo/stream"
    t0 = time.time()
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"question": question},
        stream=True, timeout=300,
    )
    print(f"HTTP {resp.status_code} content-type={resp.headers.get('content-type')}")
    if resp.status_code != 200 or "text/event-stream" not in resp.headers.get("content-type", ""):
        print(resp.text[:500])
        return 1

    event_type = None
    n_events = 0
    first_event_t = None
    first_speak_t = None
    for raw in resp.iter_lines(decode_unicode=True):
        if raw is None:
            continue
        line = raw.strip("\r")
        if line.startswith(":"):
            print(f"[{time.time()-t0:6.2f}s] (ping)")
            continue
        if line.startswith("event:"):
            event_type = line[6:].strip()
            continue
        if line.startswith("data:"):
            payload = json.loads(line[5:].strip())
            el = time.time() - t0
            if event_type == "event":
                n_events += 1
                if first_event_t is None:
                    first_event_t = el
                if payload.get("type") == "speak" and first_speak_t is None:
                    first_speak_t = el
                brief = payload.get("text") or payload.get("content") or payload.get("latex") or ""
                print(f"[{el:6.2f}s] event #{payload.get('seq')} {payload.get('type')}"
                      f"{':' + payload.get('action', '') if payload.get('type') == 'board' else ''}"
                      f" | {str(brief)[:40]}")
            else:
                print(f"[{el:6.2f}s] {event_type}: {json.dumps(payload, ensure_ascii=False)[:160]}")
            event_type = None

    print(f"\n--- 共 {n_events} 个事件; 首事件 {first_event_t and round(first_event_t, 2)}s;"
          f" 首句 speak {first_speak_t and round(first_speak_t, 2)}s; 总耗时 {time.time()-t0:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
