"""
M4 Orchestrator Pipeline — 自动事件生成 + 监控模式。

收到学生请求 → 自动执行 M4 流程 → 产出 teaching_events.json
支持文件监控模式（自动检测新请求）。
"""
from __future__ import annotations
import sys
import os
import json
import time
import traceback
import threading
from pathlib import Path
from datetime import datetime, timezone

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_MODULE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
_MODULES_DIR = _MODULE_DIR.parent
sys.path.insert(0, str(_MODULES_DIR))

from M4_orchestrator.latency_config import LatencyConfig, DEFAULT_LATENCY_CONFIG
from M4_orchestrator.emitter.teaching_events import generate_teaching_events_v2_stream
from M4_orchestrator.session_manager.state_store import load_or_create_session, update_session

SEP = "=" * 62


class OrchestratorPipeline:
    """M4 自动管道：收到学生请求 → 流式事件生成 → 产出 teaching_events.json。

    用法:
        pipeline = OrchestratorPipeline()
        pipeline.run(session_id="SES_xxx", user_question="什么是过拟合?")

        或监控模式:
        pipeline.watch("data/requests/")
    """

    def __init__(self, latency_config: LatencyConfig | None = None):
        self.config = latency_config or DEFAULT_LATENCY_CONFIG

    def run(
        self,
        session_id: str,
        user_question: str,
        teacher_skill_path: str | None = None,
        mode: str = "ondemand",
        output_dir: str | None = None,
    ) -> dict:
        """执行 M4 流程：规划 → 检索 → 生成 → 更新 session。

        Args:
            session_id: Session ID
            user_question: 学生提问
            teacher_skill_path: 教师技能文件路径
            mode: follow / ondemand
            output_dir: 输出目录（默认 data/sessions/{sid}/）

        Returns:
            dict with status, events_path, turn, events_count
        """
        t0 = time.time()

        if output_dir is None:
            output_dir = f"data/sessions/{session_id}"
        os.makedirs(f"{output_dir}/events", exist_ok=True)

        print(f"\n{SEP}")
        print(f"  M4 Orchestrator — 自动执行")
        print(f"{SEP}")
        print(f"  Session: {session_id}")
        print(f"  Question: {user_question[:60]}...")
        print(f"  Mode: {mode}")

        # 1. 加载 session 状态
        state = load_or_create_session(session_id)
        turn = state.get("turn", 0) + 1

        # 2. 规划（模拟：基于问题确定 topic）
        plan = {
            "topic": user_question[:20],
            "depth": "intro",
            "max_events": 30,
            "user_question": user_question,
        }

        # 3. 生成事件（模拟：从模板构建事件列表）
        events = self._generate_events_from_question(user_question)

        # 4. 写入 events 文件
        events_data = {
            "event_file_id": f"teaching_events_{session_id}_t{turn}",
            "question_id": f"q_{session_id}_{turn:03d}",
            "session_id": session_id,
            "turn": turn,
            "question": user_question,
            "topic": plan["topic"],
            "generated_by": "m4_orchestrator_v1",
            "events": events,
        }

        events_path = f"{output_dir}/events/turn_{turn}.json"
        with open(events_path, "w", encoding="utf-8") as f:
            json.dump(events_data, f, ensure_ascii=False, indent=2)

        # 5. 更新 session 状态
        update_session(session_id, plan, events_path)

        elapsed = time.time() - t0

        print(f"\n  ✅ M4 完成（{elapsed:.1f}s）")
        print(f"  Events: {len(events)} 个")
        print(f"  输出: {events_path}\n")

        return {
            "status": "success",
            "session_id": session_id,
            "turn": turn,
            "events_path": events_path,
            "events_count": len(events),
            "elapsed_sec": round(elapsed, 2),
        }

    def _generate_events_from_question(self, question: str) -> list[dict]:
        """模拟事件生成（实际 M4 中用 LLM 替换此方法）。

        根据问题关键词生成示范教学事件。
        """
        # 简单关键词 → 事件模板映射
        templates = {
            "函数": self._event_template("函数的基本概念"),
            "过拟合": self._event_template("过拟合与泛化"),
            "导数": self._event_template("导数的定义"),
            "物理": self._event_template("质点运动学"),
        }

        matched = None
        for keyword, template in templates.items():
            if keyword in question:
                matched = template
                break

        if not matched:
            matched = self._event_template(question[:15])

        return matched

    def _event_template(self, topic: str) -> list[dict]:
        """生成示范教学事件。"""
        return [
            {"event_id": "evt_0001", "type": "board", "seq": 1,
             "action": "write_title", "content": topic},
            {"event_id": "evt_0002", "type": "speak", "seq": 2,
             "text": f"今天我们来讲一下{topic}。这是一个非常重要的概念。"},
            {"event_id": "evt_0003", "type": "speak", "seq": 3,
             "text": "我们先来看一个生活中的例子，帮助大家建立直觉。"},
            {"event_id": "evt_0004", "type": "pause", "seq": 4,
             "duration_sec": 2.0},
            {"event_id": "evt_0005", "type": "speak", "seq": 5,
             "text": "从这个例子可以看出，理解这个概念的关键在于把握它的本质。"},
            {"event_id": "evt_0006", "type": "quiz", "seq": 6,
             "question": "以下哪个最能描述这个概念的核心理念？",
             "options": ["定义", "应用", "历史", "误用"], "blocking": True},
            {"event_id": "evt_0007", "type": "speak", "seq": 7,
             "text": "好，今天的课就到这里，下节课我们继续深入。"},
        ]

    def watch(self, watch_dir: str = "data/requests", poll_interval: float = 3.0):
        """文件监控模式：监听新学生请求并自动处理。

        请求文件格式: {session_id}_request.json
          {"user_question": "...", "teacher_skill": "...", "mode": "follow|ondemand"}
        """
        print(f"\n{SEP}")
        print(f"  M4 Watch Mode — 监控: {watch_dir}")
        print(f"  Poll 间隔: {poll_interval}s")
        print(f"{SEP}\n")

        os.makedirs(watch_dir, exist_ok=True)
        seen = set()

        while True:
            for req_file in sorted(Path(watch_dir).glob("*_request.json")):
                fpath = str(req_file)
                if fpath in seen:
                    continue
                seen.add(fpath)
                print(f"\n>>> 检测到新请求: {req_file.name}")

                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        req = json.load(f)

                    session_id = req.get("session_id", req_file.stem.replace("_request", ""))
                    self.run(
                        session_id=session_id,
                        user_question=req.get("user_question", ""),
                        teacher_skill_path=req.get("teacher_skill"),
                        mode=req.get("mode", "ondemand"),
                    )

                    # 处理完后重命名避免重复
                    processed = fpath.replace("_request.json", "_done.json")
                    os.rename(fpath, processed)

                except Exception as e:
                    print(f"  [ERROR] {e}")
                    traceback.print_exc()

            time.sleep(poll_interval)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="M4 Orchestrator — Agent 编排")
    sub = parser.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="单次运行")
    p_run.add_argument("--session-id", required=True, help="Session ID")
    p_run.add_argument("--question", required=True, help="学生提问")
    p_run.add_argument("--mode", default="ondemand", choices=["follow", "ondemand"])
    p_run.add_argument("--skill", help="教师技能文件路径")

    p_watch = sub.add_parser("watch", help="监控模式")
    p_watch.add_argument("--dir", default="data/requests", help="监控目录")
    p_watch.add_argument("--poll", type=float, default=3.0, help="轮询间隔(秒)")

    args = parser.parse_args()
    pipeline = OrchestratorPipeline()

    if args.cmd == "run":
        result = pipeline.run(
            session_id=args.session_id,
            user_question=args.question,
            teacher_skill_path=args.skill,
            mode=args.mode,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    elif args.cmd == "watch":
        pipeline.watch(watch_dir=args.dir, poll_interval=args.poll)
        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
