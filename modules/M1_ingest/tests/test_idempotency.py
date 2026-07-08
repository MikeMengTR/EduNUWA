"""
M1 test_idempotency: 验证 H3 —— 同一文件重复处理无副作用，真实 ASR。
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


_FIXTURE_WAV = os.path.join(os.path.dirname(__file__), "fixtures", "short_lecture.wav")


def _copy_speech_wav(dst: str):
    shutil.copy2(_FIXTURE_WAV, dst)


class TestIdempotency(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.wav = os.path.join(self.tmp, "lecture.wav")
        _copy_speech_wav(self.wav)
        self.out = os.path.join(self.tmp, "teachers", "T_IDEM_001")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_第二次运行结果一致(self):
        cfg = {"save_audio_samples": False, "enable_refine": False}
        r1 = ingest_teacher_material("T_IDEM_001", [self.wav], self.out, config=cfg)
        r2 = ingest_teacher_material("T_IDEM_001", [self.wav], self.out, config=cfg)
        self.assertEqual(r1["status"], "success")
        self.assertEqual(r2["status"], "success")
        self.assertEqual(r1["transcripts"], r2["transcripts"])

    def test_force_reprocess覆盖幂等(self):
        cfg = {"save_audio_samples": False, "enable_refine": False}
        ingest_teacher_material("T_IDEM_001", [self.wav], self.out, config=cfg)
        r = ingest_teacher_material("T_IDEM_001", [self.wav], self.out,
                                    config={**cfg, "force_reprocess": True})
        self.assertEqual(r["status"], "success")

    def test_ingest_index文件存在(self):
        ingest_teacher_material(
            "T_IDEM_001", [self.wav], self.out,
            config={"save_audio_samples": False, "enable_refine": False},
        )
        index_path = os.path.join(self.out, "transcripts", "_ingest_index.json")
        self.assertTrue(os.path.exists(index_path))
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)
        self.assertIn("teacher_id", index)
        self.assertGreater(len(index["entries"]), 0)

    def test_文件内容变更后重处理(self):
        cfg = {"save_audio_samples": False, "enable_refine": False}
        ingest_teacher_material("T_IDEM_001", [self.wav], self.out, config=cfg)
        with open(self.wav, "ab") as f:
            f.write(b"\x00" * 16000)  # 追加 1 秒静音，改变文件指纹
        r = ingest_teacher_material("T_IDEM_001", [self.wav], self.out, config=cfg)
        self.assertEqual(r["status"], "success")
        with open(os.path.join(self.out, "transcripts", "_ingest_index.json"),
                  encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)["entries"]), 2)


if __name__ == "__main__":
    unittest.main()
