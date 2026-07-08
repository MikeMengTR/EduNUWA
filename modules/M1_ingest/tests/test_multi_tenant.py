"""
M1 test_multi_tenant: 验证 H4 —— 多租户隔离，不跨 teacher 目录读写。
"""
import os
import sys
import shutil
import tempfile
import unittest

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from modules.M1_ingest import (
    ingest_teacher_material,
    generate_transcript_id,
    generate_upload_id,
    setup_teacher_dirs,
    teacher_id_to_compact,
)
from modules.M1_ingest.ingest_orchestrator.orchestrator import (
    teacher_id_from_compact,
)


_FIXTURE_WAV = os.path.join(os.path.dirname(__file__), "fixtures", "short_lecture.wav")


def _copy_speech_wav(dst: str):
    shutil.copy2(_FIXTURE_WAV, dst)


class TestIDFormat(unittest.TestCase):

    def test_transcript_id格式(self):
        tid = generate_transcript_id("T_20260515_001", 1)
        self.assertEqual(tid, "TR_T20260515001_001")

    def test_transcript_id包含正确teacher(self):
        tid = generate_transcript_id("T_20260515_001", 5)
        self.assertIn("T20260515001", tid)
        self.assertNotIn("T20260515002", tid)

    def test_teacher_id_compact往返(self):
        original = "T_20260515_001"
        compact = teacher_id_to_compact(original)
        restored = teacher_id_from_compact(compact)
        self.assertEqual(original, restored)

    def test_upload_id格式(self):
        self.assertTrue(generate_upload_id().startswith("UP_"))

    def test_transcript_id不会跨teacher混淆(self):
        tid_a = generate_transcript_id("T_20260515_001", 1)
        tid_b = generate_transcript_id("T_20260515_002", 1)
        self.assertNotEqual(tid_a, tid_b)


class TestMultiTenantIsolation(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dir_a = os.path.join(self.tmp, "teachers", "T_ISO_A")
        self.dir_b = os.path.join(self.tmp, "teachers", "T_ISO_B")
        self.wav_a = os.path.join(self.tmp, "a.wav")
        self.wav_b = os.path.join(self.tmp, "b.wav")
        _copy_speech_wav(self.wav_a)
        _copy_speech_wav(self.wav_b)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_teacher_A输出不进入teacher_B目录(self):
        ingest_teacher_material(
            "T_ISO_A", [self.wav_a], self.dir_a,
            config={"save_audio_samples": False, "enable_refine": False},
        )
        trans_b = os.path.join(self.dir_b, "transcripts")
        self.assertFalse(os.path.exists(trans_b))

    def test_双teacher互不干扰(self):
        r_a = ingest_teacher_material(
            "T_ISO_A", [self.wav_a], self.dir_a,
            config={"save_audio_samples": False, "enable_refine": False},
        )
        r_b = ingest_teacher_material(
            "T_ISO_B", [self.wav_b], self.dir_b,
            config={"save_audio_samples": False, "enable_refine": False},
        )
        self.assertTrue(set(r_a["transcripts"]).isdisjoint(r_b["transcripts"]))

    def test_teacher_dir正确嵌套(self):
        dirs = setup_teacher_dirs("T_NEST_001", "UP_test",
                                  base_dir=os.path.join(self.tmp, "data"))
        for key, path in dirs.items():
            if key == "root":
                continue
            self.assertTrue(path.startswith(dirs["root"]))


if __name__ == "__main__":
    unittest.main()
