"""
Streaming Pipeline — 收到事件文件后自动执行：流式输出 + TTS 并行合成。
满足 M4_orchestrator_streaming_latency_spec.md L1-L7 要求。

流程：
  1. 收到 teaching_events.json
  2. 立即 → 流式生成事件时间线（先出 board:write_title，L1 < 8s）
  3. 同时 → 后台启动 TTS 批量合成
  4. TTS 完成后 → 用真实音频时长重建 playback_data.json
  5. 输出最终结果
"""
from __future__ import annotations
import sys
import os
import json
import time
import threading
import traceback
from pathlib import Path
from datetime import datetime, timezone

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_MODULE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
_MODULES_DIR = _MODULE_DIR.parent
sys.path.insert(0, str(_MODULES_DIR))

from stream.latency_config import LatencyConfig, DEFAULT_LATENCY_CONFIG
from stream.streaming_orchestrator import generate_teaching_events_v2_stream, _estimate_speak_duration
from stream.playback_builder import build_streaming_playback

SEP = "=" * 62


class StreamingPipeline:
    """自动管道：收到事件文件 → 流式输出 + TTS 并行合成。

    Usage:
        pipeline = StreamingPipeline()
        result = pipeline.run("data/sessions/xxx/events/turn_1.json")

        # 或者用文件监控模式
        pipeline.watch("data/sessions/")
    """

    def __init__(self, latency_config: LatencyConfig | None = None):
        self.config = latency_config or DEFAULT_LATENCY_CONFIG
        self._tts_thread: threading.Thread | None = None
        self._tts_result: dict | None = None
        self._events_data: dict | None = None

    def run(
        self,
        events_path: str,
        output_dir: str | None = None,
        teacher_card_path: str | None = None,
        voice_id: str = "songhao_teacher",
        wait_tts: bool = True,
    ) -> dict:
        """执行完整管道：流式输出 + TTS 并行合成。

        Args:
            events_path: teaching_events.json 路径
            output_dir: 输出目录（默认 events 所在 session 目录）
            teacher_card_path: 教师卡路径
            voice_id: TTS 音色 ID
            wait_tts: 是否等待 TTS 完成再返回

        Returns:
            dict with status, playback_data, timeline_count, timing_report
        """
        t_start = time.time()

        # 解析路径
        events_path = str(events_path)
        if not os.path.exists(events_path):
            return {"status": "error", "message": f"File not found: {events_path}"}

        if output_dir is None:
            output_dir = str(Path(events_path).parent.parent)
        os.makedirs(output_dir, exist_ok=True)

        if teacher_card_path is None:
            # 自动查找教师卡
            candidates = [
                "data/teachers/T_20260515_001/teacher_card.json",
                "data/teachers/T_legacy_001/teacher_card.json",
            ]
            for c in candidates:
                if os.path.exists(c):
                    teacher_card_path = c
                    break

        # 加载 events 元数据
        with open(events_path, "r", encoding="utf-8") as f:
            self._events_data = json.load(f)

        events = self._events_data.get("events", [])
        session_id = self._events_data.get("session_id", Path(events_path).parent.parent.name)
        turn = self._events_data.get("turn", 1)

        print(f"\n{SEP}")
        print(f"  Streaming Pipeline — 自动执行")
        print(f"{SEP}")
        print(f"  Session:    {session_id}")
        print(f"  Turn:       {turn}")
        print(f"  Events:     {len(events)}")
        print(f"  Teacher:    {teacher_card_path or '(none)'}")
        print(f"  Voice:      {voice_id}")
        print(f"  Output:     {output_dir}")

        # === Phase 1: 立即流式输出事件时间线（L1 < 8s） ===
        print(f"\n  ── Phase 1: 流式输出（立即执行） ──")
        audio_output_dir = os.path.join(output_dir, "audio", f"turn_{turn}")

        streaming_result = self._run_streaming_phase(
            events_path=events_path,
            audio_output_dir=audio_output_dir,
        )

        # === Phase 2: 后台启动 TTS 合成 ===
        print(f"\n  ── Phase 2: TTS 并行合成 ──")
        self._tts_result = None
        self._tts_thread = threading.Thread(
            target=self._run_tts_phase,
            args=(events_path, audio_output_dir, voice_id),
            daemon=True,
        )
        self._tts_thread.start()
        print(f"  [TTS] 后台合成已启动（{len([e for e in events if e.get('type')=='speak'])} 段语音）")

        # 如果 wait_tts，等待 TTS 完成
        if wait_tts:
            print(f"  [等待 TTS 完成...]")
            self._tts_thread.join()
            print(f"  [TTS] 完成: {self._tts_result.get('audio_count', 0)} 段, "
                  f"{self._tts_result.get('total_duration_sec', 0):.1f}s")

        # === Phase 3: 用真实音频重建 playback_data ===
        print(f"\n  ── Phase 3: 重建 playback_data ──")
        final_result = self._rebuild_playback(
            events_path=events_path,
            output_dir=output_dir,
            teacher_card_path=teacher_card_path,
            audio_output_dir=audio_output_dir,
        )

        elapsed = time.time() - t_start
        final_result["total_elapsed_sec"] = round(elapsed, 2)

        # 输出摘要
        self._print_summary(final_result, len(events))

        return final_result

    def _run_streaming_phase(self, events_path: str, audio_output_dir: str) -> dict:
        """Phase 1: 立即流式输出事件并写入初始 playback_data。"""
        os.makedirs(audio_output_dir, exist_ok=True)

        # 收集所有流式事件
        timeline = []
        total_dur = 0.0
        event_count = 0

        print(f"  {'时间点':>8s} {'类型':8s} {'内容摘要':50s} {'标签'}")
        print(f"  {'-'*8} {'-'*8} {'-'*50} {'-'*5}")

        for chunk in generate_teaching_events_v2_stream(
            events_path=events_path,
            latency_config=self.config,
            live_demo=False,
        ):
            if chunk["chunk_type"] == "plan":
                print(f"  [计划] {chunk['data']['event_count']} 个事件")

            elif chunk["chunk_type"] == "event":
                item = chunk["data"]
                event_count += 1
                label = item.pop("_latency_label", "")
                _ = item.pop("_gap_sec", 0)

                detail = ""
                if item["type"] == "speak":
                    detail = (item.get("text", "")[:45] + "…")
                elif item["type"] == "board":
                    detail = f"{item.get('action', '')}"
                elif item["type"] == "formula":
                    detail = (item.get("latex", "")[:45] + "…")
                elif item["type"] == "table":
                    detail = item.get("title", "")
                elif item["type"] == "pause":
                    detail = f"等待 {item.get('duration_sec', 0)}s"
                elif item["type"] == "quiz":
                    detail = (item.get("question", "")[:45] + "…")

                print(f"  [{item['start_offset_sec']:6.1f}s] {item['type']:8s} {detail:50s} {label:5s}")
                timeline.append(item)

            elif chunk["chunk_type"] == "done":
                total_dur = chunk["data"]["total_duration_sec"]

        # 写入初始 playback_data（用估算时长）
        init_pb = {
            "session_id": self._events_data.get("session_id", "unknown") if self._events_data else "unknown",
            "turn": self._events_data.get("turn", 1) if self._events_data else 1,
            "timeline": timeline,
            "total_duration_sec": round(total_dur, 2),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        init_path = os.path.join(audio_output_dir, "..", "..", "playback_data_streaming.json")
        os.makedirs(os.path.dirname(init_path) or ".", exist_ok=True)

        tmp = init_path + ".tmp." + str(os.getpid())
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(init_pb, f, ensure_ascii=False, indent=2)
        os.replace(tmp, init_path)

        print(f"\n  [Phase 1] {event_count} 个事件已流式输出")
        print(f"  [Phase 1] 初始 playback_data: {init_path}")
        print(f"  [Phase 1] 估算总时长: {total_dur:.1f}s")

        return {
            "streaming_playback": init_path,
            "event_count": event_count,
            "estimated_duration": total_dur,
        }

    def _run_tts_phase(self, events_path: str, audio_output_dir: str, voice_id: str):
        """Phase 2: 后台 TTS 合成（在独立线程中运行）。"""
        try:
            from M5_runtime.tts_service.tts_engine import generate_tts_batch

            result = generate_tts_batch(
                events_path=events_path,
                output_dir=audio_output_dir,
                voice_id=voice_id,
                config={
                    "tts": {
                        "engine": "gpt_sovits",
                        "speed": 0.85,
                        "use_voice_clone": True,
                        "clone_reference_count": 3,
                        "top_p": 0.6,
                        "temperature": 0.6,
                    }
                },
            )
            self._tts_result = result
        except Exception as e:
            self._tts_result = {"status": "error", "message": str(e)}

    def _rebuild_playback(
        self,
        events_path: str,
        output_dir: str,
        teacher_card_path: str | None,
        audio_output_dir: str,
    ) -> dict:
        """Phase 3: 用真实音频时长重建 playback_data。"""
        audio_manifest = os.path.join(audio_output_dir, "audio_manifest.json")

        # 检测音频清单是否存在（不管 TTS 返回状态，以文件为准）
        has_audio = os.path.exists(audio_manifest)

        if has_audio:
            result = build_streaming_playback(
                events_path=events_path,
                output_path=os.path.join(output_dir, "playback_data.json"),
                teacher_card_path=teacher_card_path,
                audio_manifest_path=audio_manifest,
                latency_config=self.config,
            )
            result["audio_source"] = "gpt_sovits"
        else:
            # 无音频：纯文本估计
            result = build_streaming_playback(
                events_path=events_path,
                output_path=os.path.join(output_dir, "playback_data.json"),
                teacher_card_path=teacher_card_path,
                latency_config=self.config,
            )
            result["audio_source"] = "text_estimate"
            if self._tts_result:
                result["tts_error"] = self._tts_result.get("message", "unknown")

        return result

    def _print_summary(self, result: dict, total_events: int):
        """打印最终摘要。"""
        print(f"\n{SEP}")
        print(f"  管道执行完成")
        print(f"{SEP}")
        print(f"  Timeline:    {result.get('timeline_count', 0)} / {total_events} events")
        print(f"  Duration:    {result.get('latency_report', {}).get('total_duration_sec', 0):.1f}s")

        if result.get("audio_source") == "gpt_sovits":
            report = result.get("latency_report", {})
            print(f"  Audio:       GPT-SoVITS ({result.get('audio_source', '?')})")
            print(f"  ├ L1:        {report.get('l1_first_event_type', '?')}")
            print(f"  ├ L2 gaps:   {report.get('l2_gaps_applied', 0)}")
            print(f"  ├ L3 gaps:   {report.get('l3_gaps_applied', 0)}")
            print(f"  ├ L4 gaps:   {report.get('l4_gaps_applied', 0)}")
            print(f"  ├ L5 pause:  {report.get('l5_pause_default_ms', 0)}ms")
            print(f"  └ Duration:  {report.get('total_duration_sec', 0):.1f}s")
        else:
            print(f"  Audio:       text_estimate (TTS: {result.get('tts_error', 'N/A')})")

        print(f"  Elapsed:     {result.get('total_elapsed_sec', 0):.1f}s total")
        print(f"  Output:      {result.get('playback_data', 'N/A')}")
        print()

    def watch(self, watch_dir: str, poll_interval: float = 2.0):
        """文件监控模式：监听目录中新到达的 events 文件并自动处理。

        Args:
            watch_dir: 监听的目录（会递归查找 events/turn_*.json）
            poll_interval: 轮询间隔（秒）
        """
        import time as _time

        print(f"\n{SEP}")
        print(f"  File Watcher 模式 — 监控: {watch_dir}")
        print(f"  Poll 间隔: {poll_interval}s")
        print(f"{SEP}\n")

        seen = set()
        while True:
            for evt_file in sorted(Path(watch_dir).rglob("events/turn_*.json")):
                fpath = str(evt_file)
                if fpath in seen:
                    continue
                seen.add(fpath)
                print(f"\n>>> 检测到新文件: {fpath}")
                try:
                    self.run(events_path=fpath, wait_tts=True)
                except Exception as e:
                    print(f"[ERROR] 处理失败: {e}")
                    traceback.print_exc()
            _time.sleep(poll_interval)


# ===== CLI =====
def main():
    import argparse

    parser = argparse.ArgumentParser(description="Streaming Pipeline — 自动执行")
    sub = parser.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="单次运行")
    p_run.add_argument("--events", required=True, help="teaching_events.json 路径")
    p_run.add_argument("--output", help="输出目录")
    p_run.add_argument("--teacher-card", help="教师卡路径")
    p_run.add_argument("--voice-id", default="songhao_teacher", help="TTS 音色")
    p_run.add_argument("--no-tts-wait", action="store_true", help="不等待 TTS 完成")

    p_watch = sub.add_parser("watch", help="文件监控模式")
    p_watch.add_argument("--dir", default="data/sessions", help="监控目录")
    p_watch.add_argument("--poll", type=float, default=2.0, help="轮询间隔(秒)")

    args = parser.parse_args()

    pipeline = StreamingPipeline()

    if args.cmd == "run":
        result = pipeline.run(
            events_path=args.events,
            output_dir=args.output,
            teacher_card_path=args.teacher_card,
            voice_id=args.voice_id,
            wait_tts=not args.no_tts_wait,
        )
        if result["status"] == "error":
            print(f"[FAIL] {result.get('message', '')}")
            return 1
        return 0

    elif args.cmd == "watch":
        pipeline.watch(watch_dir=args.dir, poll_interval=args.poll)
        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
