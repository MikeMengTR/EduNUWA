# -*- coding: utf-8 -*-
"""media_library 检索与 prompt 注入的单元测试。

覆盖：关键词命中打分与排序、零命中返回空、top_k 截断、build_catalog 的
URL 定稿、无候选时 _build_demo_prompt 与改造前逐字节一致（回归红线）。

运行: D:\\anaconda3\\envs\\edu\\python.exe modules\\M6_platform\\backend\\test_media_library.py
（不依赖后端运行；用临时 index 文件，不碰真实图库）
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import media_library
from media_library import retrieve_candidates, build_catalog, build_image_prompt_block


FAKE_INDEX = {
    "version": 1,
    "images": [
        {"id": "IMG_math_0001", "file": "math/IMG_math_0001.png", "media_type": "static",
         "subject": "math", "topic": "导数",
         "keywords": ["切线", "割线", "导数", "斜率"],
         "caption": "切线示意", "llm_desc": "切线与割线", "status": "active"},
        {"id": "IMG_math_0004", "file": "math/IMG_math_0004.png", "media_type": "static",
         "subject": "math", "topic": "正态分布",
         "keywords": ["正态分布", "标准差", "均值"],
         "caption": "正态曲线", "llm_desc": "三条正态密度曲线", "status": "active"},
        {"id": "IMG_physics_0001", "file": "physics/IMG_physics_0001.gif", "media_type": "gif",
         "subject": "physics", "topic": "机械波",
         "keywords": ["波", "横波", "波长", "传播"],
         "caption": "横波动图", "llm_desc": "横波传播动图", "status": "active"},
        {"id": "IMG_math_0099", "file": "math/IMG_math_0099.png", "media_type": "static",
         "subject": "math", "topic": "导数",
         "keywords": ["导数"],
         "caption": "已禁用", "llm_desc": "已禁用", "status": "disabled"},
    ],
}


def setup_fake_index():
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(FAKE_INDEX, tmp, ensure_ascii=False)
    tmp.close()
    media_library.INDEX_PATH = tmp.name
    media_library._cache["mtime"] = None  # 失效缓存
    return tmp.name


def main():
    failures = []
    path = setup_fake_index()

    def check(name, cond, detail=""):
        print(f"[{'PASS' if cond else 'FAIL'}] {name}{(' — ' + detail) if (detail and not cond) else ''}")
        if not cond:
            failures.append(name)

    try:
        # 1. 命中与排序：问题含"导数/切线"应首推切线图
        r = retrieve_candidates("导数的几何意义是什么？切线斜率怎么理解")
        check("导数问题命中切线图", bool(r) and r[0]["id"] == "IMG_math_0001",
              f"got={[e['id'] for e in r]}")

        # 2. disabled 条目不出现
        check("disabled 条目被过滤", all(e["id"] != "IMG_math_0099" for e in r))

        # 3. 零命中返回空列表
        check("无关问题零候选", retrieve_candidates("二战的历史背景是什么") == [])

        # 4. 空 query
        check("空 query 返回空", retrieve_candidates("") == [])

        # 5. topic 命中加权：问"正态分布"应首推正态图
        r2 = retrieve_candidates("正态分布里标准差起什么作用")
        check("正态分布问题命中正态图", bool(r2) and r2[0]["id"] == "IMG_math_0004",
              f"got={[e['id'] for e in r2]}")

        # 6. top_k 截断
        r3 = retrieve_candidates("导数 切线 正态分布 标准差 波 横波", top_k=2)
        check("top_k=2 截断", len(r3) == 2, f"got={len(r3)}")

        # 7. build_catalog：URL 服务端定稿
        cat = build_catalog(r2[:1])
        check("catalog URL 定稿",
              cat.get("IMG_math_0004", {}).get("src") == "/api/v1/media/math/IMG_math_0004.png",
              f"got={cat}")

        # 8. 无候选时 prompt 块为空串（回归红线：prompt 与改造前逐字节一致）
        check("无候选 prompt 块为空串", build_image_prompt_block([]) == "")
        from pipeline import _build_demo_prompt
        p_no_image = _build_demo_prompt("SYS", "Q", "", build_image_prompt_block([]))
        p_default = _build_demo_prompt("SYS", "Q", "")
        check("无候选 prompt 与默认逐字节一致", p_no_image == p_default)
        check("无候选 prompt 不含插图规则", "插图规则" not in p_default)

        # 9. 有候选时规则块含 ID 清单与防幻觉措辞
        block = build_image_prompt_block(r2[:2])
        check("候选块包含 ID", "IMG_math_0004" in block)
        check("候选块包含防幻觉规则", "禁止编造" in block)
        p_with = _build_demo_prompt("SYS", "Q", "", block)
        check("注入后 prompt 含插图规则", "【插图规则·重要】" in p_with)
    finally:
        os.unlink(path)

    if failures:
        print(f"\n{len(failures)} 项失败: {failures}")
        return 1
    print("\n全部通过 OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
