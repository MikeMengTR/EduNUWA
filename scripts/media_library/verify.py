# -*- coding: utf-8 -*-
"""教学插图库一致性校验：index.json ↔ images/ 文件。

校验项：ID 唯一且符合命名规范、必填字段非空、index 条目对应文件存在、
images/ 下无 index 失联的孤儿文件、记录的宽高与实际一致、GIF ≤5MB。

用法: D:\\anaconda3\\envs\\edu\\python.exe scripts\\media_library\\verify.py
"""
import json
import os
import re
import sys

from PIL import Image

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MEDIA_ROOT = os.path.join(_project_root, "data", "media_library")
IMAGES_ROOT = os.path.join(MEDIA_ROOT, "images")
INDEX_PATH = os.path.join(MEDIA_ROOT, "index.json")

REQUIRED_FIELDS = ("id", "file", "media_type", "subject", "keywords", "caption", "llm_desc")
ID_PATTERN = re.compile(r"^IMG_[a-z]+_\d{4}$")
MAX_GIF_BYTES = 5 * 1024 * 1024


def main():
    if not os.path.exists(INDEX_PATH):
        print(f"index.json 不存在: {INDEX_PATH}")
        return 1
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        index = json.load(f)
    images = index.get("images", [])
    errors = []

    seen_ids = set()
    indexed_files = set()
    for e in images:
        eid = e.get("id", "?")
        for field in REQUIRED_FIELDS:
            if not e.get(field):
                errors.append(f"{eid}: 缺少必填字段 {field}")
        if not ID_PATTERN.match(eid):
            errors.append(f"{eid}: ID 不符合 IMG_{{subject}}_{{0000}} 规范")
        if eid in seen_ids:
            errors.append(f"{eid}: ID 重复")
        seen_ids.add(eid)
        if e.get("media_type") not in ("static", "gif"):
            errors.append(f"{eid}: media_type 非法: {e.get('media_type')}")

        rel = e.get("file", "")
        indexed_files.add(rel.replace("\\", "/"))
        path = os.path.join(IMAGES_ROOT, rel)
        if not os.path.isfile(path):
            errors.append(f"{eid}: 文件不存在 {rel}")
            continue
        try:
            with Image.open(path) as img:
                w, h = img.size
            if e.get("width") and (w, h) != (e["width"], e["height"]):
                errors.append(f"{eid}: 记录尺寸 {e['width']}x{e['height']} ≠ 实际 {w}x{h}")
        except Exception as ex:
            errors.append(f"{eid}: 图片无法解析: {ex}")
        if e.get("media_type") == "gif" and os.path.getsize(path) > MAX_GIF_BYTES:
            errors.append(f"{eid}: GIF 超过 5MB")

    # 孤儿文件
    if os.path.isdir(IMAGES_ROOT):
        for root, _dirs, files in os.walk(IMAGES_ROOT):
            for fn in files:
                rel = os.path.relpath(os.path.join(root, fn), IMAGES_ROOT).replace("\\", "/")
                if rel not in indexed_files:
                    errors.append(f"孤儿文件（不在 index 中）: {rel}")

    if errors:
        print(f"校验失败，{len(errors)} 处问题：")
        for msg in errors:
            print(f"  - {msg}")
        return 1
    print(f"校验通过：{len(images)} 张图，index 与文件一一对应")
    return 0


if __name__ == "__main__":
    sys.exit(main())
