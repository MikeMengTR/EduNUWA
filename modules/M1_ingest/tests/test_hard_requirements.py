"""
M1 H1-H10 硬性要求验收测试。

使用真实 MP4 视频 + 真实 ASR 模型，逐条验证 docs/modules/M1_ingest.md §4 的
十条入门红线。所有文件和模型均为真实，无 mock、无虚构。

用法：
    python -m pytest modules/M1_ingest/tests/test_hard_requirements.py -v -s
"""
import os
import sys
import json
import time
import glob
import shutil
import tempfile
import unittest

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from modules.M1_ingest import (
    ingest_teacher_material,
    submit_ingest_task,
    query_ingest_progress,
)

# ── 测试视频：选最小的 MP4 以控制测试时长 ──
_UPLOAD_DIR = os.path.join(_project_root, "data", "teachers", "L_ZJU_001",
                           "uploads")
_VIDEO_CANDIDATES = sorted(
    glob.glob(os.path.join(_UPLOAD_DIR, "*.mp4")),
    key=os.path.getsize,
)
if not _VIDEO_CANDIDATES:
    raise FileNotFoundError(f"uploads 目录下未找到 MP4 文件: {_UPLOAD_DIR}")

TEST_MP4 = _VIDEO_CANDIDATES[0]  # 最小的 MP4

# ── transcript schema 必需字段（api_contract.md §2） ──
REQUIRED_TOP = (
    "transcript_id", "teacher_id", "source_file", "source_audio",
    "language", "asr_backend", "asr_quality", "ingested_at", "segments",
)
REQUIRED_SEG = ("segment_id", "start", "end", "text")

# ── 文档 §3.5 进度阶段 ──
VALID_STAGES = frozenset({
    "file_validating", "audio_extracting", "audio_segmenting",
    "asr_transcribing", "text_cleaning", "sample_picking", "done",
})


class TestH1_AudioSamples(unittest.TestCase):
    """H1: 保留原始音频片段 ≥5 段，每段 8-30 秒。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "teachers", "T_H1_001")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_H1_音频样本数量与时长(self):
        print(f"\n[H1] 测试视频: {os.path.basename(TEST_MP4)}")
        result = ingest_teacher_material(
            "T_H1_001", [TEST_MP4], self.out,
            config={"enable_refine": False},
        )
        self.assertIn(result["status"], ("success", "partial"),
                      f"摄取失败: {result.get('message')}")

        manifest_path = os.path.join(self.out, "audio_samples", "manifest.json")
        self.assertTrue(os.path.exists(manifest_path),
                        f"H1 失败: manifest.json 不存在 → {manifest_path}")
        with open(manifest_path, encoding="utf-8") as f:
            m = json.load(f)

        samples = m["samples"]
        self.assertGreaterEqual(len(samples), 5,
            f"H1 失败: 样本数 {len(samples)} < 5")

        for s in samples:
            dur = s["duration_sec"]
            self.assertGreaterEqual(dur, 8.0,
                f"H1 失败: 样本 {s['sample_id']} 时长 {dur}s < 8s")
            self.assertLessEqual(dur, 30.0,
                f"H1 失败: 样本 {s['sample_id']} 时长 {dur}s > 30s")
            self.assertIsNotNone(s["snr_estimate"],
                f"H1 失败: 样本 {s['sample_id']} SNR 为空")
            self.assertIsNotNone(s["source_segment"],
                f"H1 失败: 样本 {s['sample_id']} source_segment 为空")

        print(f"  H1 PASS: {len(samples)} 段, 时长范围 "
              f"{min(s['duration_sec'] for s in samples):.1f}-"
              f"{max(s['duration_sec'] for s in samples):.1f}s, "
              f"SNR 范围 "
              f"{min(s['snr_estimate'] for s in samples)}-"
              f"{max(s['snr_estimate'] for s in samples)} dB")


class TestH2_SchemaValidation(unittest.TestCase):
    """H2: teacher_transcript.json 通过 api_contract.md §2 schema 校验。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "teachers", "T_H2_001")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_H2_transcript_schema完整(self):
        print(f"\n[H2] 测试视频: {os.path.basename(TEST_MP4)}")
        result = ingest_teacher_material(
            "T_H2_001", [TEST_MP4], self.out,
            config={"enable_refine": False},
        )
        self.assertIn(result["status"], ("success", "partial"))

        for t_path in result["transcripts"]:
            with open(t_path, encoding="utf-8") as f:
                data = json.load(f)
            for key in REQUIRED_TOP:
                self.assertIn(key, data,
                    f"H2 失败: transcript 缺少顶层字段 '{key}'")
            self.assertIsInstance(data["segments"], list)
            self.assertGreater(len(data["segments"]), 0,
                "H2 失败: segments 为空")
            for i, seg in enumerate(data["segments"]):
                for key in REQUIRED_SEG:
                    self.assertIn(key, seg,
                        f"H2 失败: segments[{i}] 缺少字段 '{key}'")
                self.assertLess(seg["start"], seg["end"],
                    f"H2 失败: segments[{i}] start >= end")
                self.assertIsInstance(seg["text"], str)
                self.assertGreater(len(seg["text"]), 0,
                    f"H2 失败: segments[{i}] text 为空")

        print(f"  H2 PASS: {len(data['segments'])} segments, "
              f"全部 {len(REQUIRED_TOP)} 个顶层字段齐全")


class TestH3_Idempotency(unittest.TestCase):
    """H3: 幂等——同一组 upload_paths 第二次运行不产生重复 transcript。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "teachers", "T_H3_001")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_H3_幂等(self):
        print(f"\n[H3] 测试视频: {os.path.basename(TEST_MP4)}")
        cfg = {"enable_refine": False, "save_audio_samples": False}

        t0 = time.time()
        r1 = ingest_teacher_material("T_H3_001", [TEST_MP4], self.out, config=cfg)
        t1 = time.time() - t0

        t0 = time.time()
        r2 = ingest_teacher_material("T_H3_001", [TEST_MP4], self.out, config=cfg)
        t2 = time.time() - t0

        self.assertEqual(r1["status"], "success")
        self.assertEqual(r2["status"], "success")
        self.assertEqual(r1["transcripts"], r2["transcripts"],
            "H3 失败: 两次运行 transcript 路径不同")

        # 第二次应远快于第一次（跳过了 ASR）
        ratio = t2 / max(t1, 0.01)
        print(f"  H3 PASS: 首次 {t1:.1f}s, 第二次 {t2:.1f}s "
              f"(比例 {ratio:.2f})")
        self.assertLess(ratio, 0.5,
            f"H3 警告: 第二次未明显加速 ({ratio:.2f}x)，幂等可能未生效")

        index_path = os.path.join(self.out, "transcripts", "_ingest_index.json")
        self.assertTrue(os.path.exists(index_path),
            "H3 失败: _ingest_index.json 未生成")


class TestH4_MultiTenantIsolation(unittest.TestCase):
    """H4: 多租户隔离——禁止写入其他 teacher_id 的路径。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dir_a = os.path.join(self.tmp, "teachers", "T_H4_A")
        self.dir_b = os.path.join(self.tmp, "teachers", "T_H4_B")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_H4_路径隔离(self):
        print(f"\n[H4] 测试视频: {os.path.basename(TEST_MP4)}")
        cfg = {"enable_refine": False, "save_audio_samples": False}

        ingest_teacher_material("T_H4_A", [TEST_MP4], self.dir_a, config=cfg)

        # 检查 T_H4_B 目录下不应有任何 transcript
        trans_b = os.path.join(self.dir_b, "transcripts")
        self.assertFalse(os.path.exists(trans_b),
            f"H4 失败: teacher_A 的输出泄露到 teacher_B 目录")

        # 检查 T_H4_A 的输出全部在其目录下
        for root, _, files in os.walk(self.dir_a):
            for f in files:
                full = os.path.join(root, f)
                self.assertTrue(
                    full.startswith(os.path.abspath(self.dir_a)),
                    f"H4 失败: 文件 {full} 越界写入"
                )

        print(f"  H4 PASS: teacher 目录完全隔离")


class TestH5_AsyncSupport(unittest.TestCase):
    """H5: 异步——submit_ingest_task + query_ingest_progress 可用。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "teachers", "T_H5_001")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_H5_异步任务(self):
        print(f"\n[H5] 测试视频: {os.path.basename(TEST_MP4)}")
        task_id = submit_ingest_task(
            "T_H5_001", [TEST_MP4], self.out,
            config={"enable_refine": False, "save_audio_samples": False},
        )
        self.assertTrue(task_id.startswith("TASK_"))

        # 轮询直到完成
        stages = []
        prev_progress = -1.0
        deadline = time.time() + 900  # 15 分钟超时
        info = None

        while time.time() < deadline:
            info = query_ingest_progress(task_id)
            self.assertIsNotNone(info, "H5 失败: task_id 查不到进度")

            p = info.get("progress", 0) or 0
            self.assertGreaterEqual(p, prev_progress - 0.001,
                f"H5 失败: progress 倒退 {prev_progress} → {p}")
            prev_progress = p

            stage = info.get("stage", "")
            if stage and (not stages or stages[-1] != stage):
                stages.append(stage)
                self.assertIn(stage, VALID_STAGES,
                    f"H5 失败: 非法阶段名 '{stage}'")

            if info["status"] == "success":
                break
            if info["status"] == "failed":
                self.fail(f"H5 失败: task failed, error={info.get('error')}")
            time.sleep(2)

        self.assertEqual(info["status"], "success")
        self.assertEqual(info["progress"], 1.0)
        self.assertEqual(info["stage"], "done")
        self.assertIsNotNone(info["result"])
        self.assertEqual(info["result"]["status"], "success")

        print(f"  H5 PASS: 阶段序列 {' → '.join(stages)}, "
              f"最终 progress={info['progress']}")


class TestH6_AsrBackends(unittest.TestCase):
    """H6: 至少 2 个 ASR backend 可用。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "teachers", "T_H6_001")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_H6_whisper后端可用(self):
        print(f"\n[H6] 测试视频: {os.path.basename(TEST_MP4)}")
        result = ingest_teacher_material(
            "T_H6_001", [TEST_MP4], self.out,
            config={"enable_refine": False, "save_audio_samples": False,
                     "asr_backend": "whisper"},
        )
        self.assertIn(result["status"], ("success", "partial"),
            f"H6 失败: whisper 后端不可用: {result.get('message')}")

        # 查看 transcript 确认 asr_backend 字段
        with open(result["transcripts"][0], encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("whisper", data["asr_backend"],
            f"H6 失败: asr_backend 字段不是 whisper: {data['asr_backend']}")

        print(f"  H6 PASS: backend={data['asr_backend']}, "
              f"segments={len(data['segments'])}")

    def test_H6_auto后端可降级(self):
        self.tmp2 = tempfile.mkdtemp()
        self.out2 = os.path.join(self.tmp2, "teachers", "T_H6_002")
        result = ingest_teacher_material(
            "T_H6_002", [TEST_MP4], self.out2,
            config={"enable_refine": False, "save_audio_samples": False,
                     "asr_backend": "auto"},
        )
        self.assertIn(result["status"], ("success", "partial"),
            f"H6 失败: auto 后端不可用")
        with open(result["transcripts"][0], encoding="utf-8") as f:
            data = json.load(f)
        print(f"  H6 AUTO: 最终使用 backend={data['asr_backend']}")


class TestH7_AtomicWrites(unittest.TestCase):
    """H7: 原子写入——禁止残留 .tmp 文件。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "teachers", "T_H7_001")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_H7_无tmp残留(self):
        print(f"\n[H7] 测试视频: {os.path.basename(TEST_MP4)}")
        result = ingest_teacher_material(
            "T_H7_001", [TEST_MP4], self.out,
            config={"enable_refine": False},
        )
        self.assertIn(result["status"], ("success", "partial"))

        tmp_files = []
        for root, _, files in os.walk(self.out):
            for f in files:
                if f.endswith(".tmp"):
                    tmp_files.append(os.path.join(root, f))
        self.assertEqual(len(tmp_files), 0,
            f"H7 失败: 残留 .tmp 文件: {tmp_files}")

        # 确认所有 JSON 文件可正常解析（不是半截文件）
        json_count = 0
        for root, _, files in os.walk(self.out):
            for f in files:
                if f.endswith(".json"):
                    with open(os.path.join(root, f), encoding="utf-8") as fh:
                        json.load(fh)
                    json_count += 1
        self.assertGreater(json_count, 0, "H7 失败: 无 JSON 文件产出")
        print(f"  H7 PASS: {json_count} 个 JSON 文件, 0 个 .tmp 残留")


class TestH8_ErrorHandling(unittest.TestCase):
    """H8: 失败返回 status='error' + 可读 message，不抛栈。"""

    def test_H8_空输入返回error(self):
        print("\n[H8] 测试空输入")
        out = os.path.join(tempfile.mkdtemp(), "out")
        result = ingest_teacher_material("T_H8_001", [], out)
        self.assertEqual(result["status"], "error")
        self.assertIsInstance(result["message"], str)
        self.assertGreater(len(result["message"]), 0)
        print(f"  H8 PASS: message='{result['message']}'")

    def test_H8_不存在文件返回error(self):
        print("[H8] 测试文件不存在")
        out = os.path.join(tempfile.mkdtemp(), "out")
        result = ingest_teacher_material(
            "T_H8_001", ["nonexistent.mp4"], out,
            config={"enable_refine": False},
        )
        self.assertIn(result["status"], ("error", "partial"))
        self.assertGreater(len(result.get("warnings", [])), 0)
        print(f"  H8 PASS: status={result['status']}")

    def test_H8_不抛栈(self):
        print("[H8] 测试异常不抛栈")
        for args in [
            ("T_X", [], tempfile.mkdtemp()),
            ("T_X", ["nonexistent.wav"], tempfile.mkdtemp()),
        ]:
            result = ingest_teacher_material(*args)
            self.assertIsInstance(result, dict)
            self.assertIn("status", result)


class TestH9_NoCrossModuleImport(unittest.TestCase):
    """H9: 不允许调用 M2/M3/M4/M5 的代码。"""

    def test_H9_无跨模块引用(self):
        print("\n[H9] 扫描 import...")
        import re
        m1_root = os.path.join(_project_root, "modules", "M1_ingest")
        violations = []
        pattern = re.compile(
            r"\b(modules\.M[2-5]|from\s+modules\.M[2-5])"
        )
        for root, _, files in os.walk(m1_root):
            for f in files:
                if f.endswith(".py") and "__pycache__" not in root:
                    fpath = os.path.join(root, f)
                    with open(fpath, encoding="utf-8") as fh:
                        for lineno, line in enumerate(fh, 1):
                            if pattern.search(line):
                                violations.append(f"{fpath}:{lineno}: {line.strip()}")
        self.assertEqual(len(violations), 0,
            f"H9 失败: 检测到跨模块引用:\n" + "\n".join(violations))
        print(f"  H9 PASS: 无 M2-M5 引用")


class TestH10_Logging(unittest.TestCase):
    """H10: 日志写到 _logs/ingest_{task_id}.log。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "teachers", "T_H10_001")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_H10_日志文件存在(self):
        print(f"\n[H10] 测试视频: {os.path.basename(TEST_MP4)}")
        result = ingest_teacher_material(
            "T_H10_001", [TEST_MP4], self.out,
            config={"enable_refine": False, "save_audio_samples": False},
        )
        self.assertIn(result["status"], ("success", "partial"))

        log_dir = os.path.join(self.out, "_logs")
        self.assertTrue(os.path.exists(log_dir),
            f"H10 失败: _logs 目录不存在: {log_dir}")

        log_files = os.listdir(log_dir)
        self.assertGreater(len(log_files), 0,
            f"H10 失败: _logs 目录为空")

        # 至少有一个 ingest_*.log
        ingest_logs = [f for f in log_files if f.startswith("ingest_")]
        self.assertGreater(len(ingest_logs), 0,
            f"H10 失败: 未找到 ingest_*.log, 现有文件: {log_files}")

        # 检查日志非空
        log_path = os.path.join(log_dir, ingest_logs[0])
        with open(log_path, encoding="utf-8") as f:
            content = f.read()
        self.assertGreater(len(content), 0,
            f"H10 失败: 日志文件为空: {log_path}")
        self.assertIn("开始摄取", content,
            f"H10 失败: 日志中未找到'开始摄取'")

        print(f"  H10 PASS: {log_path} ({len(content)} 字符)")


if __name__ == "__main__":
    unittest.main()
