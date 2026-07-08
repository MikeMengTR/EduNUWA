"""
M1 test_error_handling: 验证 H8 —— 所有错误场景返回 dict，不抛栈。
"""
import os
import sys
import tempfile
import unittest

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from modules.M1_ingest import ingest_teacher_material


class TestErrorHandling(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "teachers", "T_ERR_001")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_空upload_paths返回error(self):
        result = ingest_teacher_material("T_ERR_001", [], self.out)
        self.assertEqual(result["status"], "error")
        self.assertIn("message", result)

    def test_文件不存在返回error(self):
        result = ingest_teacher_material(
            "T_ERR_001", ["nonexistent.wav"], self.out,
            config={"save_audio_samples": False, "enable_refine": False},
        )
        self.assertIn(result["status"], ("error", "partial"))
        self.assertGreater(len(result.get("warnings", [])), 0)

    def test_不支持的文件类型返回error(self):
        txt = os.path.join(self.tmp, "notes.txt")
        with open(txt, "w") as f:
            f.write("hello")
        result = ingest_teacher_material(
            "T_ERR_001", [txt], self.out,
        )
        self.assertIn(result["status"], ("error", "partial"))

    def test_返回值始终是dict(self):
        for args in [
            ("T_ERR_001", [], self.out),
            ("T_ERR_001", ["nonexistent.wav"], self.out),
        ]:
            result = ingest_teacher_material(*args)
            self.assertIsInstance(result, dict)
            self.assertIn("status", result)
            self.assertIn("transcripts", result)
            self.assertIn("audio_samples", result)
            self.assertIn("warnings", result)


if __name__ == "__main__":
    unittest.main()
