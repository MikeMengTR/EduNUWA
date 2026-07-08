"""
M1 文件管理工具：ID 生成、多租户目录创建、原子写入。

ID 命名规范（对齐 EduNUWA v2 总体方案 §5.2）：
- upload_id:      UP_{YYYYMMDDHHMMSS}_{rand}
- transcript_id:  TR_{teacher_id_compact}_{seq}
- teacher_id_compact: teacher_id 去掉所有下划线
"""

import os
import json
import random
import string
from datetime import datetime, timezone


def _utc_timestamp() -> str:
    """返回 UTC 时间戳字符串，格式 YYYYMMDDHHMMSS"""
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _random_suffix(length: int = 3) -> str:
    """生成随机小写字母后缀"""
    return "".join(random.choices(string.ascii_lowercase, k=length))


def teacher_id_to_compact(teacher_id: str) -> str:
    """将 teacher_id 转换为 compact 形式（去掉所有下划线）。

    teacher_id: T_20260515_001 → T20260515001
    """
    return teacher_id.replace("_", "")


def teacher_id_from_compact(compact: str) -> str | None:
    """从 compact 形式反推 teacher_id（仅当格式为标准 T + 日期 + 序号时可靠）。

    T20260515001 → T_20260515_001
    返回 None 表示格式不匹配，调用方应查 M6 的 teacher_id ↔ compact 映射表。
    """
    import re
    m = re.match(r"^T(\d{8})(\d{3,})$", compact)
    if not m:
        return None
    return f"T_{m.group(1)}_{m.group(2)}"


def generate_upload_id() -> str:
    """生成上传任务 ID：UP_{YYYYMMDDHHMMSS}_{rand}"""
    return f"UP_{_utc_timestamp()}_{_random_suffix()}"


def generate_transcript_id(teacher_id: str, seq: int) -> str:
    """生成 transcript ID：TR_{teacher_id_compact}_{序号}

    teacher_id: T_20260515_001, seq: 1 → TR_T20260515001_001
    """
    compact = teacher_id_to_compact(teacher_id)
    return f"TR_{compact}_{seq:03d}"


def setup_teacher_dirs(teacher_id: str, upload_id: str,
                       base_dir: str = "data") -> dict[str, str]:
    """为指定教师创建多租户目录结构，返回各子目录路径。

    创建的结构：
        {base_dir}/teachers/{teacher_id}/
            uploads/{upload_id}/
            transcripts/
            audio_samples/
    """
    root = os.path.join(base_dir, "teachers", teacher_id)
    dirs = {
        "root": root,
        "uploads": os.path.join(root, "uploads", upload_id),
        "transcripts": os.path.join(root, "transcripts"),
        "audio_samples": os.path.join(root, "audio_samples"),
    }
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)
    return dirs


def atomic_write_json(path: str, data: dict, indent: int = 2) -> None:
    """原子写入 JSON：先写 .tmp 文件，完成后 rename 到目标路径，避免并发读损坏。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
    os.replace(tmp_path, path)


# ============================================================
# 本地测试入口
# ============================================================
if __name__ == "__main__":
    print("=== file_manager unit tests ===\n")

    # 测试 ID 生成
    uid = generate_upload_id()
    assert uid.startswith("UP_"), f"upload_id 格式错误: {uid}"
    print(f"[OK] upload_id: {uid}")

    tid = "T_20260515_001"
    compact = teacher_id_to_compact(tid)
    assert compact == "T20260515001", f"compact error: {compact}"
    print(f"[OK] teacher_id {tid} -> compact: {compact}")

    trid = generate_transcript_id(tid, 1)
    assert trid == "TR_T20260515001_001", f"transcript_id error: {trid}"
    print(f"[OK] transcript_id (seq=1): {trid}")
    trid2 = generate_transcript_id(tid, 42)
    assert trid2 == "TR_T20260515001_042", f"transcript_id error: {trid2}"
    print(f"[OK] transcript_id (seq=42): {trid2}")

    reversed_tid = teacher_id_from_compact("T20260515001")
    assert reversed_tid == "T_20260515_001", f"reverse parse error: {reversed_tid}"
    print(f"[OK] compact -> teacher_id: {reversed_tid}")

    test_base = "data"
    dirs = setup_teacher_dirs(tid, uid, base_dir=test_base)
    for name, path in dirs.items():
        assert os.path.isdir(path), f"directory not created: {path}"
        print(f"[OK] dir [{name}]: {path}")

    test_json_path = os.path.join(dirs["transcripts"], "_test_atomic.json")
    atomic_write_json(test_json_path, {"test": True, "id": trid})
    assert os.path.exists(test_json_path), "file not written"
    assert not os.path.exists(test_json_path + ".tmp"), "tmp file left behind"
    with open(test_json_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded["id"] == trid, "JSON content mismatch"
    print(f"[OK] atomic write verified: {test_json_path}")

    os.remove(test_json_path)
    print("\n[PASS] All file_manager tests passed")
