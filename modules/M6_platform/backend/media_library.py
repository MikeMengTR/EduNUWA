# -*- coding: utf-8 -*-
"""教学插图库：index 读取、候选检索、prompt 注入块构造。

图库落地 data/media_library/（index.json + images/{subject}/...），由
scripts/media_library/ 下的 gen_math_figures.py / ingest.py / verify.py 维护。
本模块只读、零重依赖；检索是纯本地关键词子串匹配（毫秒级），不阻塞流式链路。

防幻觉设计（与 M3 matcher 的 H9 同思想）：LLM 只能从注入 prompt 的候选清单里
选 ID，ID→URL 的解析在服务端完成（build_catalog），候选集外的 ID 在
event_stream.DemoEventParser 处静默丢弃。无候选时 build_image_prompt_block
返回空串，prompt 与改造前逐字节一致——图库覆盖不到的主题零扰动。
"""
import json
import os
import threading

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

MEDIA_ROOT = os.path.join(_project_root, "data", "media_library")
IMAGES_ROOT = os.path.join(MEDIA_ROOT, "images")
INDEX_PATH = os.path.join(MEDIA_ROOT, "index.json")

# index.json 读多写少（写只来自入库脚本/上传），按 mtime 缓存全量条目
_cache = {"mtime": None, "images": []}
_cache_lock = threading.Lock()


def _load_index():
    """读 index.json 里 status=active 的条目（mtime 缓存）。无图库返回 []。"""
    try:
        mtime = os.path.getmtime(INDEX_PATH)
    except OSError:
        return []
    with _cache_lock:
        if _cache["mtime"] != mtime:
            try:
                with open(INDEX_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                print(f"[media_library] index.json 读取失败(忽略): {e}")
                return []
            _cache["images"] = [
                e for e in data.get("images", [])
                if e.get("status", "active") == "active" and e.get("id") and e.get("file")
            ]
            _cache["mtime"] = mtime
        return list(_cache["images"])


def retrieve_candidates(query, subject_hint="", top_k=6):
    """从图库选出与 query 最相关的条目，按分降序，无命中返回 []。

    匹配方向是"条目的 keyword 是否出现在 query 文本里"，中文子串匹配即可，
    不需要分词：score = Σ len(命中keyword) + 2*len(命中topic) + 学科弱加成。
    长词命中权重自然更高；score 为 0 的条目不入候选。
    """
    query = (query or "").strip()
    if not query:
        return []
    scored = []
    for entry in _load_index():
        score = 0
        for kw in entry.get("keywords", []):
            if kw and kw in query:
                score += len(kw)
        topic = entry.get("topic", "")
        if topic and topic in query:
            score += len(topic) * 2
        if score > 0:
            if subject_hint and entry.get("subject") == subject_hint:
                score += 1
            scored.append((score, entry))
    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    return [e for _, e in scored[:top_k]]


def build_catalog(candidates):
    """候选列表 → DemoEventParser 用的 {image_id: {src, media_type, caption}}。
    src（/api/v1/media/ 相对 URL）在服务端定稿，前端对图库目录结构保持无知。"""
    catalog = {}
    for e in candidates:
        catalog[e["id"]] = {
            "src": f"/api/v1/media/{e['file']}",
            "media_type": e.get("media_type", "static"),
            "caption": e.get("caption", ""),
        }
    return catalog


def build_image_prompt_block(candidates):
    """构造注入 LLM prompt 的【插图规则】段。

    demo（pipeline._build_demo_prompt）与预录课程（course._orchestrate_chapter）
    共用此函数，保证两处插图规则一致（CLAUDE.md 公式约定同款要求）。
    无候选返回空串——此时 prompt 与无图库时逐字节一致，零回归。
    """
    if not candidates:
        return ""
    lines = []
    for e in candidates:
        desc = (e.get("llm_desc") or e.get("caption") or "").strip()
        lines.append(f"  {e['id']}：{desc}")
    listing = "\n".join(lines)
    example_id = candidates[0]["id"]
    return f"""

【插图规则·重要】
- 本次讲解可用的教学插图如下（只能引用以下 ID，绝对禁止编造其它 ID）：
{listing}
- 需要展示插图时，单独输出一行，格式如：[image] {example_id} | 一句话告诉学生重点看图中的什么
- **必须先输出 [image] 行（让图先出现在黑板上），紧接着再用 [speak] 讲解这张图**；绝对不要先讲完、最后才放图，否则学生听讲时黑板还没有图。
- **用不用某张图，看它的描述是否贴合你此刻正在讲的内容，而不是「沾词」**：图里顺带出现了你提到的某个概念（比如一张对比/演进图里含「生物神经元」，而你只是在单独讲生物神经元本身）不算贴合，这种情况不要用。拿不准就不用。
- 整节课最多用 2 张；没有合适的图就不要用，禁止为了用图而硬塞。"""
