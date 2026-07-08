"""M3 推荐事件落盘 — 进化闭环的起点。

每次 /api/v1/match 生成一条不可变的 match 记录（写一次后只读，因此无需加锁），
反馈提交时凭 match_id 回查做快照 enrich + 防伪造校验。

存储：data/match_log/{YYYYMM}/{match_id}.json
match_id 格式 M_{YYYYMMDD}_{hex12}，按 id 内的年月定位目录，O(1) 查找。
"""
import json
import os
import re
import secrets
from datetime import datetime, timezone

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA_DIR = os.path.join(_project_root, "data")
MATCH_LOG_DIR = os.path.join(DATA_DIR, "match_log")

_MATCH_ID_RE = re.compile(r"^M_(\d{8})_[0-9a-f]{12}$")


def generate_match_id():
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"M_{ts}_{secrets.token_hex(6)}"


def _record_path(match_id):
    m = _MATCH_ID_RE.match(match_id or "")
    if not m:
        return None
    return os.path.join(MATCH_LOG_DIR, m.group(1)[:6], f"{match_id}.json")


def create_match_record(user_id, query, candidates, rankings):
    """落盘一条 match 事件，返回 match_id。candidates/rankings 直接快照存储。"""
    match_id = generate_match_id()
    path = _record_path(match_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    record = {
        "match_id": match_id,
        "user_id": user_id,
        "query": query,
        "candidates": candidates,
        "rankings": rankings,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return match_id


def load_match_record(match_id):
    """按 match_id 读记录；id 非法或文件不存在返回 None。"""
    path = _record_path(match_id)
    if not path or not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
