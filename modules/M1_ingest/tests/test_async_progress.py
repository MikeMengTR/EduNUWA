"""
M1 test_async_progress: 验证 §3.5 异步任务接口，真实 ASR 在后台线程中运行。
"""
import os
import sys
import time
import shutil
import tempfile
import unittest

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from modules.M1_ingest import submit_ingest_task, query_ingest_progress
from modules.M1_ingest.ingest_orchestrator.task_runner import (
    cancel_ingest_task, list_tasks,
)
from modules.M1_ingest.ingest_orchestrator.progress_tracker import (
    STATUS_SUCCESS, STATUS_FAILED, STATUS_CANCELLED,
)

VALID_STAGES = frozenset({
    "file_validating", "audio_extracting", "audio_segmenting",
    "asr_transcribing", "text_cleaning", "sample_picking", "done",
})


_FIXTURE_WAV = os.path.join(os.path.dirname(__file__), "fixtures", "short_lecture.wav")


def _copy_speech_wav(dst: str):
    shutil.copy2(_FIXTURE_WAV, dst)


class TestAsyncProgress(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.wav = os.path.join(self.tmp, "lecture.wav")
        _copy_speech_wav(self.wav)
        self.out = os.path.join(self.tmp, "teachers", "T_ASYNC_001")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _poll_until_done(self, task_id: str, timeout: float = 60.0):
        stages_seen = []
        prev_progress = -1.0
        deadline = time.time() + timeout

        while time.time() < deadline:
            info = query_ingest_progress(task_id)
            self.assertIsNotNone(info, f"task {task_id} 不应返回 None")

            p = info.get("progress", 0) or 0
            self.assertGreaterEqual(p, prev_progress - 0.001,
                                    f"progress 从 {prev_progress} 降到 {p}")
            prev_progress = p

            stage = info.get("stage", "")
            if stage and (not stages_seen or stages_seen[-1] != stage):
                stages_seen.append(stage)

            if info["status"] in (STATUS_SUCCESS, STATUS_FAILED):
                return info, stages_seen

            time.sleep(0.5)

        self.fail(f"任务 {timeout}s 内未完成: last={info}")

    def test_submit返回合法task_id(self):
        task_id = submit_ingest_task(
            "T_ASYNC_001", [self.wav], self.out,
            config={"save_audio_samples": False, "enable_refine": False},
        )
        self.assertTrue(task_id.startswith("TASK_"))

    def test_异步任务成功完成(self):
        task_id = submit_ingest_task(
            "T_ASYNC_001", [self.wav], self.out,
            config={"save_audio_samples": False, "enable_refine": False},
        )
        info, _ = self._poll_until_done(task_id)
        self.assertEqual(info["status"], STATUS_SUCCESS)
        self.assertEqual(info["progress"], 1.0)
        self.assertEqual(info["stage"], "done")
        self.assertIsNotNone(info["result"])

    def test_所有阶段名在合法列表内(self):
        task_id = submit_ingest_task(
            "T_ASYNC_001", [self.wav], self.out,
            config={"save_audio_samples": False, "enable_refine": False},
        )
        _, stages = self._poll_until_done(task_id)
        for s in stages:
            self.assertIn(s, VALID_STAGES, f"非法阶段: {s}")

    def test_取消任务(self):
        task_id = submit_ingest_task("T_ASYNC_002", [], os.path.join(
            self.tmp, "teachers", "T_ASYNC_002"))
        self.assertTrue(cancel_ingest_task(task_id))
        self.assertEqual(query_ingest_progress(task_id)["status"],
                         STATUS_CANCELLED)

    def test_不存在的task_id返回None(self):
        self.assertIsNone(query_ingest_progress("TASK_nonexistent"))

    def test_list_tasks包含已提交任务(self):
        task_id = submit_ingest_task(
            "T_ASYNC_001", [self.wav], self.out,
            config={"save_audio_samples": False, "enable_refine": False},
        )
        self._poll_until_done(task_id)
        self.assertIn(task_id, [t["task_id"] for t in list_tasks()])


if __name__ == "__main__":
    unittest.main()
