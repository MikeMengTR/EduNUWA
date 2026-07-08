"""
M1 test_orchestrator: 主流程集成测试，真实 ASR 不走 mock。
"""
import os
import sys
import json
import shutil
import tempfile
import unittest

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from modules.M1_ingest import ingest_teacher_material

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
_SPEECH_WAV = os.path.join(_FIXTURE_DIR, "short_lecture.wav")


def _copy_speech_wav(dst: str):
    """复制真实语音 WAV 到目标路径，供 ASR 测试使用。"""
    shutil.copy2(_SPEECH_WAV, dst)

REQUIRED_TOP_KEYS = (
    "transcript_id", "teacher_id", "source_file", "source_audio",
    "language", "asr_backend", "asr_quality", "ingested_at", "segments",
)
REQUIRED_SEG_KEYS = ("segment_id", "start", "end", "text")


def _make_wav(path: str, sec: float = 1.0):
    with wave.open(path, "w") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
        for _ in range(int(16000 * sec)):
            wf.writeframes(struct.pack("<h", 0))


class TestOrchestratorIntegration(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "teachers", "T_ORCH_001")
        self.wav = os.path.join(self.tmp, "test.wav")
        _copy_speech_wav(self.wav)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_成功处理单个WAV(self):
        result = ingest_teacher_material(
            "T_ORCH_001", [self.wav], self.out,
            config={"save_audio_samples": False, "enable_refine": False},
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["transcripts"]), 1)
        self.assertTrue(os.path.exists(result["transcripts"][0]))

    def test_返回值包含所有必要字段(self):
        result = ingest_teacher_material(
            "T_ORCH_001", [self.wav], self.out,
            config={"save_audio_samples": False, "enable_refine": False},
        )
        for key in ("status", "message", "teacher_id", "transcripts",
                     "audio_samples", "stats", "warnings"):
            self.assertIn(key, result, f"返回值缺少字段: {key}")
        for key in ("total_duration_sec", "segments_count",
                     "avg_segment_duration_sec", "estimated_cer"):
            self.assertIn(key, result["stats"], f"stats 缺少字段: {key}")

    def test_transcript文件符合schema(self):
        result = ingest_teacher_material(
            "T_ORCH_001", [self.wav], self.out,
            config={"save_audio_samples": False, "enable_refine": False},
        )
        with open(result["transcripts"][0], encoding="utf-8") as f:
            data = json.load(f)
        for key in REQUIRED_TOP_KEYS:
            self.assertIn(key, data, f"transcript 缺少: {key}")
        self.assertIsInstance(data["segments"], list)
        self.assertGreater(len(data["segments"]), 0)
        for seg in data["segments"]:
            for key in REQUIRED_SEG_KEYS:
                self.assertIn(key, seg, f"segment 缺少: {key}")
            self.assertLess(seg["start"], seg["end"])
            self.assertIsInstance(seg["text"], str)
            self.assertGreater(len(seg["text"]), 0)

    def test_音频样本manifest生成(self):
        result = ingest_teacher_material(
            "T_ORCH_001", [self.wav], self.out,
            config={"enable_refine": False},
        )
        manifest_path = os.path.join(self.out, "audio_samples", "manifest.json")
        self.assertTrue(os.path.exists(manifest_path))
        with open(manifest_path, encoding="utf-8") as f:
            m = json.load(f)
        self.assertEqual(m["teacher_id"], "T_ORCH_001")
        self.assertGreater(len(m["samples"]), 0)

    def test_force_reprocess重跑不跳过(self):
        cfg = {"save_audio_samples": False, "enable_refine": False}
        r1 = ingest_teacher_material("T_ORCH_001", [self.wav], self.out, config=cfg)
        r2 = ingest_teacher_material("T_ORCH_001", [self.wav], self.out,
                                     config={**cfg, "force_reprocess": True})
        self.assertEqual(r1["status"], "success")
        self.assertEqual(r2["status"], "success")
        self.assertTrue(os.path.exists(r2["transcripts"][0]))


if __name__ == "__main__":
    unittest.main()
