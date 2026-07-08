# -*- coding: utf-8 -*-
"""教学插图入库：staging 目录（manifest.json + 图片）→ data/media_library/。

处理流程：
  1. PIL 打开校验（损坏图拒收）
  2. 静态图最长边 >1280 等比缩到 1280；GIF 不重采样（PIL 处理动图易丢帧），
     只做 ≤5MB 体积门槛（太大首屏加载慢会打乱讲课节奏）
  3. 按学科分配 ID（IMG_{subject}_{序号:04d}），拷贝到 images/{subject}/
  4. 原子写 index.json（temp + os.replace）；以 origin（subject+原文件名）判重，
     重复运行幂等跳过

用法: D:\\anaconda3\\envs\\edu\\python.exe scripts\\media_library\\ingest.py [staging_dir]
      staging_dir 默认 scripts/media_library/generated
"""
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone

from PIL import Image

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_script_dir))

MEDIA_ROOT = os.path.join(_project_root, "data", "media_library")
IMAGES_ROOT = os.path.join(MEDIA_ROOT, "images")
INDEX_PATH = os.path.join(MEDIA_ROOT, "index.json")

MAX_EDGE = 1280
MAX_GIF_BYTES = 5 * 1024 * 1024
REQUIRED_FIELDS = ("file", "media_type", "subject", "keywords", "caption", "llm_desc")


def load_index():
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"version": 1, "images": []}


def save_index(index):
    os.makedirs(MEDIA_ROOT, exist_ok=True)
    tmp = INDEX_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    os.replace(tmp, INDEX_PATH)


def next_seq(index, subject):
    pat = re.compile(rf"^IMG_{re.escape(subject)}_(\d{{4}})$")
    seqs = [int(m.group(1)) for e in index["images"] if (m := pat.match(e.get("id", "")))]
    return max(seqs, default=0) + 1


def ingest_item(index, staging_dir, item):
    for field in REQUIRED_FIELDS:
        if not item.get(field):
            return None, f"缺少必填字段 {field}"
    src_path = os.path.join(staging_dir, item["file"])
    if not os.path.isfile(src_path):
        return None, f"文件不存在: {src_path}"

    subject = item["subject"]
    origin = f"{subject}/{os.path.basename(item['file'])}"
    for e in index["images"]:
        if e.get("origin") == origin:
            return None, "skip"  # 已入库，幂等跳过

    ext = os.path.splitext(item["file"])[1].lower()
    is_gif = item["media_type"] == "gif"
    try:
        with Image.open(src_path) as img:
            img.verify()  # 损坏检测
        with Image.open(src_path) as img:
            width, height = img.size
    except Exception as e:
        return None, f"图片无法解析: {e}"

    if is_gif:
        size = os.path.getsize(src_path)
        if size > MAX_GIF_BYTES:
            return None, f"GIF 超过 5MB 门槛（{size / 1024 / 1024:.1f}MB），请线下压缩后重试"

    image_id = f"IMG_{subject}_{next_seq(index, subject):04d}"
    rel_file = f"{subject}/{image_id}{ext}"
    dst_path = os.path.join(IMAGES_ROOT, subject, f"{image_id}{ext}")
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)

    if not is_gif and max(width, height) > MAX_EDGE:
        with Image.open(src_path) as img:
            img.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
            img.save(dst_path)
            width, height = img.size
    else:
        shutil.copyfile(src_path, dst_path)

    entry = {
        "id": image_id,
        "file": rel_file,
        "media_type": item["media_type"],
        "subject": subject,
        "topic": item.get("topic", ""),
        "keywords": list(item["keywords"]),
        "caption": item["caption"],
        "llm_desc": item["llm_desc"],
        "width": width,
        "height": height,
        "source": item.get("source", "manual"),
        "license": item.get("license", ""),
        "status": item.get("status", "active"),
        "origin": origin,
        "added_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    index["images"].append(entry)
    return entry, None


def main():
    staging_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_script_dir, "generated")
    manifest_path = os.path.join(staging_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        print(f"未找到 {manifest_path}")
        return 1
    with open(manifest_path, "r", encoding="utf-8") as f:
        items = json.load(f).get("items", [])

    index = load_index()
    added, skipped, failed = 0, 0, 0
    for item in items:
        entry, err_msg = ingest_item(index, staging_dir, item)
        if entry:
            added += 1
            print(f"  [入库] {entry['id']} ← {item['file']} ({entry['width']}x{entry['height']})")
        elif err_msg == "skip":
            skipped += 1
        else:
            failed += 1
            print(f"  [拒收] {item.get('file', '?')}: {err_msg}")

    if added:
        save_index(index)
    print(f"完成：入库 {added}，跳过(已存在) {skipped}，拒收 {failed}；"
          f"图库现有 {len(index['images'])} 张 → {INDEX_PATH}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
