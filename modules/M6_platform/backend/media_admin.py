# -*- coding: utf-8 -*-
"""教师端教学插图管理：上传 + 一句话 LLM 扩写元数据 + 入库 + 启停/删除。

与只读的 media_library.py 分工：
  - media_library.py：检索 / prompt 注入 / catalog（讲课链路只读，零重依赖，红线不动）
  - media_admin.py（本模块）：写侧——把教师上传的「裸原图」补上 keywords/llm_desc/caption
    三字段后写进同一个 data/media_library/index.json，让它立刻可被检索调用。

设计要点：
  - 当前阶段「全部进全局共享库」（产品决策：上线前再做按 teacher_id 隔离）。已在每条
    entry 写 uploaded_by=teacher_id，到时按它过滤即可，零数据迁移。
  - 「未被解析的原图」难在没有元数据 → 检索是中文子串匹配，没 keywords 永远 score=0。
    本模块用已配的 DeepSeek 文本模型把教师写的一句话扩写成三字段，教师确认/微调后入库。
  - ID 必须 ^IMG_[a-z]+_[0-9]{4}$，故 subject 只能是小写 ascii（中文学科名会破坏 ID），
    前端用固定的「中文标签→ascii key」映射，后端用 SUBJECTS 兜底校验。
  - index.json 写入加进程内锁 + 原子 os.replace；media_library 按 mtime 自动刷新缓存。
"""
import base64
import hashlib
import io
import json
import os
import re
import secrets
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from PIL import Image
from flask import request, Response, stream_with_context

from auth import require_role, ok, err
from teachers import list_all_teachers

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

MEDIA_ROOT = os.path.join(_project_root, "data", "media_library")
IMAGES_ROOT = os.path.join(MEDIA_ROOT, "images")
INDEX_PATH = os.path.join(MEDIA_ROOT, "index.json")

MAX_EDGE = 1280
MAX_GIF_BYTES = 5 * 1024 * 1024
EXT_MEDIA_TYPE = {".png": "static", ".jpg": "static", ".jpeg": "static",
                  ".webp": "static", ".gif": "gif"}

# subject 必须是小写 ascii（受 ID 正则约束）。label 给前端展示，key 进 ID。
SUBJECTS = {
    "math": "数学", "physics": "物理", "chemistry": "化学", "biology": "生物",
    "chinese": "语文", "english": "英语", "history": "历史", "geography": "地理",
    "politics": "政治", "other": "其他",
}

_index_lock = threading.Lock()

# ---- DeepSeek 一句话 → 三字段扩写 ----------------------------------------

_ANNOTATE_SYS = (
    "你是教学图库的元数据助手。给你一张教学插图（可能附一句话描述），"
    "你要判断它的学科、并产出能让它被准确检索、被讲课 AI 正确引用的元数据。"
    "只输出 JSON，不要任何多余文字。"
)


def _subject_options_str():
    """供 prompt 用的学科候选串，从 SUBJECTS 动态生成，与校验同源。"""
    return "、".join(f"{k}({v})" for k, v in SUBJECTS.items())


def _annotate_prompt(brief, subject_hint):
    hint = (f"\n（教师初步归类为「{SUBJECTS.get(subject_hint, subject_hint)}」，仅供参考，以内容为准）"
            if subject_hint else "")
    brief_line = f"\n教师对这张教学插图的描述：{brief}" if brief.strip() else ""
    return f"""请为下面这张教学插图产出检索元数据。{brief_line}{hint}

请输出 JSON，字段如下：
- subject：从这些学科里选**最贴切的一个**，只输出英文 key：{_subject_options_str()}。跨多个学科或拿不准就填 other。
- topic：这张图的核心知识点，2-6 个字的中文短语（如「导数」「正态分布」）。
- keywords：5-10 个中文检索关键词数组，目的是判断**「学生问什么时该调出这张图」**，不是罗列图里有什么。**子串精确匹配**（须原样出现在问题里才命中），所以：
  ① 用**原子短词**（2-5 字单一概念，把「轨迹抛物线」拆成「抛物线」「轨迹」）；
  ② **只放这张图真正用来讲解的核心概念**；图里只是顺带出现、并非本图主旨的概念不要放，否则学生单独讲那个概念时会被误调出——例如「生物神经元与人工神经元对比图」应放「人工神经元」「神经网络」「神经元对比」，而**不要放裸的「生物神经元」**（会在纯生物课讲神经元时误命中）；
  ③ **务必覆盖学生提问会用的各种说法**：中文全称、简称、英文缩写、常见别名都要列（如多层感知机要同时放「多层感知机」「MLP」「感知机」「前馈神经网络」；正态分布放「正态分布」「高斯分布」），否则学生用缩写或别名提问就漏掉；但每个词仍要对「该不该用本图」有判别力，不放「图」「运动」「物体」这类泛词。
- llm_desc：给讲课 AI 看的判据，写清**适合在讲什么、做什么时展示**（多概念/对比图必要时点明不适合单独讲某个概念的场景），而非单纯描述画面（不超过 70 字）。
- caption：一句话图注，给学生看，简洁友好（不超过 30 字）。
只输出 JSON 对象。"""


def _normalize_meta(data, subject_hint=""):
    """收敛成统一结构。subject 非法时回退 hint，再不行回退 other。"""
    subj = (data.get("subject") or "").strip().lower()
    if subj not in SUBJECTS:
        subj = subject_hint if subject_hint in SUBJECTS else "other"
    kws = data.get("keywords", [])
    if isinstance(kws, str):
        kws = [w for w in re.split(r"[\s,，、;；]+", kws) if w]
    return {
        "subject": subj,
        "topic": (data.get("topic") or "").strip(),
        "keywords": [str(k).strip() for k in kws if str(k).strip()],
        "llm_desc": (data.get("llm_desc") or "").strip(),
        "caption": (data.get("caption") or "").strip(),
    }


def _parse_json_loose(text):
    """从模型回复里抠出 JSON（容忍 ```json 围栏、前后多余文字）。"""
    i, j = text.find("{"), text.rfind("}")
    if i == -1 or j == -1:
        raise ValueError("模型未返回 JSON")
    return json.loads(text[i:j + 1])


def _llm_annotate(brief, subject_hint=""):
    """调 DeepSeek 把一句话扩写成元数据（含推断 subject）。"""
    from chat import get_client, DEEPSEEK_API_KEY
    if not DEEPSEEK_API_KEY:
        # 未配 key：回退成最朴素的可用元数据（至少能按 brief 命中），不阻塞功能
        kws = [w for w in re.split(r"[\s,，、;；]+", brief.strip()) if len(w) >= 2][:8]
        return {"subject": subject_hint if subject_hint in SUBJECTS else "other",
                "topic": "", "keywords": kws or [brief.strip()[:8]],
                "llm_desc": brief.strip()[:60], "caption": brief.strip()[:30]}
    client = get_client()
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "system", "content": _ANNOTATE_SYS},
                  {"role": "user", "content": _annotate_prompt(brief, subject_hint)}],
        temperature=0.3,
        max_tokens=600,
        response_format={"type": "json_object"},
    )
    return _normalize_meta(json.loads(resp.choices[0].message.content), subject_hint)

# ---- Qwen-VL 视觉模型：直接看图产元数据（阿里云 DashScope OpenAI 兼容接口）-------
# 复用 M1 已验证的链路：base_url=compatible-mode/v1、图片走 base64 data URL 的 image_url。
# 模型与地址可由环境变量覆盖（不同账号开通的 VL 模型名不同，如 qwen-vl-plus / qwen3-vl-plus）。

QWEN_VL_BASE_URL = os.environ.get("QWEN_VL_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_VL_MODEL = os.environ.get("QWEN_VL_MODEL", "qwen3-vl-plus")
_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".webp": "image/webp", ".gif": "image/gif"}


def _dashscope_key():
    return os.environ.get("DASHSCOPE_API_KEY", "").strip()


def _vision_image_bytes(raw, ext):
    """喂给 VLM 前压一道：静态图统一缩到 ≤1280 的 JPEG（省 token/延迟），GIF 原样送。"""
    if EXT_MEDIA_TYPE.get(ext) == "gif":
        return raw, "image/gif"
    try:
        with Image.open(io.BytesIO(raw)) as im:
            im = im.convert("RGB")
            im.thumbnail((1280, 1280), Image.LANCZOS)
            out = io.BytesIO()
            im.save(out, format="JPEG", quality=88)
            return out.getvalue(), "image/jpeg"
    except Exception:
        return raw, _MIME.get(ext, "image/png")


def _vl_prompt(subject_hint, brief):
    hint = (f"\n教师初步归类为「{SUBJECTS.get(subject_hint, subject_hint)}」（仅供参考，以图为准）。"
            if subject_hint else "")
    extra = f"\n教师补充说明（可参考，但以图为准）：{brief}" if brief.strip() else ""
    return f"""请仔细观察这张教学插图里画的内容，产出能让它被准确检索、被讲课 AI 正确引用的元数据。{hint}{extra}

只输出一个 JSON 对象，字段：
- subject：从这些学科里选**最贴切的一个**，只输出英文 key：{_subject_options_str()}。跨多个学科或拿不准就填 other。
- topic：图的核心知识点，2-6 个字的中文短语（如「导数」「泊松分布」）。
- keywords：5-10 个中文检索关键词数组，目的是判断**「学生问什么时该调出这张图」**，不是罗列图里有什么。**子串精确匹配**（须原样出现在问题里才命中），所以：①用**原子短词**（2-5 字单一概念，把「轨迹抛物线」拆成「抛物线」「轨迹」）；②**只放这张图真正用来讲解的核心概念**；图里只是顺带出现、并非本图主旨的概念不要放，否则学生单独讲那个概念时会被误调出——例如「生物神经元与人工神经元对比图」应放「人工神经元」「神经网络」「神经元对比」，而**不要放裸的「生物神经元」**（会在纯生物课讲神经元时误命中）；③**务必覆盖学生提问会用的各种说法**：中文全称、简称、英文缩写、常见别名都要列（如多层感知机要同时放「多层感知机」「MLP」「感知机」「前馈神经网络」；正态分布放「正态分布」「高斯分布」），否则学生用缩写或别名问就漏掉；但每个词仍要对「该不该用本图」有判别力，不放「图」「运动」「物体」这类泛词。
- llm_desc：给讲课 AI 看的判据，写清**适合在讲什么、做什么时展示**（多概念/对比图必要时点明不适合单独讲某个概念的场景），而非单纯描述画面（≤70 字）。
- caption：一句话图注，给学生看，简洁友好（≤30 字）。
只输出 JSON，不要任何多余文字。"""


def _vl_annotate(raw, ext, subject_hint="", brief=""):
    """让 Qwen-VL 看图产出元数据（含推断 subject）。需配 DASHSCOPE_API_KEY。"""
    from openai import OpenAI
    key = _dashscope_key()
    if not key:
        raise RuntimeError("未配置 DASHSCOPE_API_KEY")
    img_bytes, mime = _vision_image_bytes(raw, ext)
    data_url = f"data:{mime};base64," + base64.b64encode(img_bytes).decode()
    client = OpenAI(api_key=key, base_url=QWEN_VL_BASE_URL)
    resp = client.chat.completions.create(
        model=QWEN_VL_MODEL,
        messages=[
            {"role": "system", "content": _ANNOTATE_SYS},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": _vl_prompt(subject_hint, brief)},  # 文本放最后（Qwen-VL 推荐顺序）
            ]},
        ],
        temperature=0.2,
        max_tokens=700,
    )
    return _normalize_meta(_parse_json_loose(resp.choices[0].message.content), subject_hint)

# ---- 从 PPT 取图 + 视觉判断是否适合做教学插图 ------------------------------

_PPT_MIN_EDGE = 200      # 长宽都 < 200px 基本是图标/装饰，本地先滤掉，省 VLM 调用
_PPT_MAX_IMAGES = 100    # 单个 PPT 最多判定这么多张，超出截断并提示
_PPT_IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp")


def _extract_pptx_images(pptx_bytes):
    """.pptx 本质是 zip，取 ppt/media 下的位图：按内容去重 + 滤掉过小装饰图，
    统一规整为 PNG（透明底合成白底；GIF 保留动图）。返回 [(name, ext, raw)]。"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(pptx_bytes))
    except Exception as e:
        raise ValueError(f"无法打开 PPT（需 .pptx）：{e}")
    out, seen, idx = [], set(), 0
    for n in zf.namelist():
        if not n.lower().startswith("ppt/media/"):
            continue
        if os.path.splitext(n)[1].lower() not in _PPT_IMG_EXT:
            continue  # 跳过 emf/wmf 矢量、音视频等
        raw = zf.read(n)
        h = hashlib.md5(raw).hexdigest()
        if h in seen:
            continue  # PPT 里重复用的图（如每页 logo）只留一份
        seen.add(h)
        try:
            with Image.open(io.BytesIO(raw)) as im:
                w, hgt = im.size
                if max(w, hgt) < _PPT_MIN_EDGE:
                    continue  # 太小 → 图标/装饰
                if im.format == "GIF" and getattr(im, "is_animated", False):
                    keep_raw, keep_ext = raw, ".gif"   # 动图原样保留
                else:
                    src = im.convert("RGBA")
                    bg = Image.new("RGBA", src.size, (255, 255, 255, 255))
                    bg.alpha_composite(src)            # 透明底合成白底，避免黑板上看不清
                    buf = io.BytesIO()
                    bg.convert("RGB").save(buf, format="PNG")
                    keep_raw, keep_ext = buf.getvalue(), ".png"
        except Exception:
            continue  # PIL 打不开（矢量/损坏）→ 跳过
        idx += 1
        out.append((f"PPT图_{idx}{keep_ext}", keep_ext, keep_raw))
    return out


def _thumb_b64(raw, ext):
    """给前端「查看被舍弃图」用的小预览：dropped 图不入库、只为看一眼，
    静态图压到 ≤512 的 JPEG 省带宽；GIF 原样（动图）。返回 (b64, mime)。"""
    if EXT_MEDIA_TYPE.get(ext) == "gif":
        return base64.b64encode(raw).decode(), "image/gif"
    try:
        with Image.open(io.BytesIO(raw)) as im:
            im = im.convert("RGB")
            im.thumbnail((512, 512), Image.LANCZOS)
            out = io.BytesIO()
            im.save(out, format="JPEG", quality=80)
            return base64.b64encode(out.getvalue()).decode(), "image/jpeg"
    except Exception:
        return base64.b64encode(raw).decode(), _MIME.get(ext, "image/png")


def _vl_judge_prompt():
    return f"""这是从 PPT 里提取的一张图。请**从严**判断它是否适合作为「教学示例插图」入库（拿不准、信息量低一律判不适合），再视情况产出元数据。

适合（suitable=true）：承载明确知识内容的图，须**至少具备一项**：坐标轴/数据曲线/图表；带文字或符号标注的结构图、原理图、流程图；明确的几何关系；受力/电场线/磁感线等带方向的物理示意；标注了变量的推导或过程图。判据：去掉它，对应知识点的讲解会缺一块。
不适合（suitable=false，遇到以下一律判不适合）：
  · **抽象光效**：放射状光束、光晕、星芒、发光渐变、能量扩散等艺术化效果——**即使形似某物理现象，只要没有标注/坐标/结构，也判不适合**；
  · 背景纹理、色块、渐变、装饰图案、花边、分隔线、纯箭头/图标/按钮；
  · logo/校徽、人物头像/合影、风景或情境配图、页眉页脚；
  · 纯文字截图（标题页、目录、学习目标、纯公式文字）、二维码；
  · **过于简陋、缺乏标注、近似简笔或图标的草图**——即使画的是某个模型，但简单到没有教学信息量也判不适合。

只输出一个 JSON 对象：
- suitable：true 或 false
- reason：一句话判断理由
- 若 suitable=false，只需给出 suitable 和 reason 即可。
- 若 suitable=true，再给出以下字段：
  - subject：从这些里选最贴切的一个英文 key：{_subject_options_str()}（跨学科/拿不准填 other）
  - topic：核心知识点，2-6 字中文短语
  - keywords：5-10 个中文检索关键词数组，目的是「学生问什么时该调出这张图」。用原子短词；覆盖该概念的中文全称/简称/英文缩写/别名（如多层感知机→「多层感知机」「MLP」「感知机」）；不放「图」「运动」「物体」这类泛词
  - llm_desc：适合在讲什么、做什么时展示（≤70 字）
  - caption：给学生看的一句话图注（≤30 字）
只输出 JSON，不要任何多余文字。"""


def _vl_judge_and_annotate(raw, ext):
    """一次视觉调用：判断是否适合做教学插图；适合则同时产出元数据。需 DASHSCOPE_API_KEY。"""
    from openai import OpenAI
    key = _dashscope_key()
    if not key:
        raise RuntimeError("未配置 DASHSCOPE_API_KEY（PPT 取图需视觉模型判断）")
    img_bytes, mime = _vision_image_bytes(raw, ext)
    data_url = f"data:{mime};base64," + base64.b64encode(img_bytes).decode()
    client = OpenAI(api_key=key, base_url=QWEN_VL_BASE_URL)
    resp = client.chat.completions.create(
        model=QWEN_VL_MODEL,
        messages=[
            {"role": "system", "content": "你判断图片是否适合做教学插图，适合则产出图库元数据。只输出 JSON。"},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": _vl_judge_prompt()},
            ]},
        ],
        temperature=0.2,
        max_tokens=800,
    )
    data = _parse_json_loose(resp.choices[0].message.content)
    if not bool(data.get("suitable")):
        return {"suitable": False, "reason": (data.get("reason") or "").strip()}
    meta = _normalize_meta(data)
    meta.update({"suitable": True, "reason": (data.get("reason") or "").strip()})
    return meta

# ---- index 读写 -----------------------------------------------------------

def _load_index():
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"version": 1, "images": []}


def _save_index(index):
    os.makedirs(MEDIA_ROOT, exist_ok=True)
    tmp = INDEX_PATH + f".{secrets.token_hex(4)}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    os.replace(tmp, INDEX_PATH)


def _next_seq(index, subject):
    pat = re.compile(rf"^IMG_{re.escape(subject)}_(\d{{4}})$")
    seqs = [int(m.group(1)) for e in index["images"] if (m := pat.match(e.get("id", "")))]
    return max(seqs, default=0) + 1


def _commit_image(raw, ext, subject, meta, teacher_id):
    """校验/缩放/分配 ID/写盘/原子追加 index。返回 (entry, error)。"""
    media_type = EXT_MEDIA_TYPE[ext]
    is_gif = media_type == "gif"
    if is_gif and len(raw) > MAX_GIF_BYTES:
        return None, f"GIF 超过 5MB（{len(raw) / 1024 / 1024:.1f}MB），请压缩后再传"
    try:
        with Image.open(io.BytesIO(raw)) as im:
            im.verify()
        with Image.open(io.BytesIO(raw)) as im:
            width, height = im.size
    except Exception as e:
        return None, f"图片无法解析: {e}"

    with _index_lock:
        index = _load_index()
        image_id = f"IMG_{subject}_{_next_seq(index, subject):04d}"
        rel_file = f"{subject}/{image_id}{ext}"
        dst = os.path.join(IMAGES_ROOT, subject, f"{image_id}{ext}")
        os.makedirs(os.path.dirname(dst), exist_ok=True)

        # GIF 不重采样（PIL 处理动图易丢帧）；静态图超长边才缩
        if not is_gif and max(width, height) > MAX_EDGE:
            with Image.open(io.BytesIO(raw)) as im:
                im.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
                im.save(dst)
                width, height = im.size
        else:
            with open(dst, "wb") as f:
                f.write(raw)

        entry = {
            "id": image_id,
            "file": rel_file,
            "media_type": media_type,
            "subject": subject,
            "topic": meta.get("topic", ""),
            "keywords": meta["keywords"],
            "caption": meta["caption"],
            "llm_desc": meta["llm_desc"],
            "width": width,
            "height": height,
            "source": "teacher_upload",
            "license": "teacher upload",
            "status": "active",
            "origin": f"teacher_upload/{teacher_id}/{secrets.token_hex(6)}",
            "uploaded_by": teacher_id,
            "added_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        index["images"].append(entry)
        _save_index(index)
    return entry, None

# ---- 路由 -----------------------------------------------------------------

def _my_teacher_id():
    card = next((t for t in list_all_teachers() if t.get("user_id") == request.user_id), None)
    return card["teacher_id"] if card else None


def _with_url(entry):
    e = dict(entry)
    e["url"] = f"/api/v1/media/{entry['file']}"
    return e


def register_routes(app):
    @app.route("/api/v1/images/subjects", methods=["GET"])
    @require_role("teacher")
    def list_image_subjects():
        return ok([{"key": k, "label": v} for k, v in SUBJECTS.items()])

    @app.route("/api/v1/images", methods=["GET"])
    @require_role("teacher")
    def list_images():
        """列出图库条目供教师管理。当前为全局共享库，返回全部（disabled 也返回，
        前端区分展示）；mine=1 只看自己上传的。"""
        index = _load_index()
        items = index.get("images", [])
        if request.args.get("mine") == "1":
            tid = _my_teacher_id()
            items = [e for e in items if e.get("uploaded_by") == tid]
        return ok([_with_url(e) for e in items])

    @app.route("/api/v1/images/annotate", methods=["POST"])
    @require_role("teacher")
    def annotate_image():
        """生成元数据供教师确认（含 AI 推断的 subject）。multipart：可选 file + 可选
        brief + 可选 subject（仅作提示，学科由 AI 判断、教师可在前端改）。视觉优先：有图且
        配了 DASHSCOPE_API_KEY → Qwen-VL 直接看图；否则/失败时退回 DeepSeek 文本扩写
        （需 brief）。返回里带 _engine 标明用了哪条。"""
        subject_hint = (request.form.get("subject") or "").strip().lower()
        if subject_hint not in SUBJECTS:
            subject_hint = ""  # 学科改由 AI 推断，传入仅作提示；缺失/非法即无提示
        brief = (request.form.get("brief") or "").strip()
        file = request.files.get("file")

        if file and file.filename and _dashscope_key():
            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in EXT_MEDIA_TYPE:
                return err(f"不支持的图片类型，支持：{', '.join(EXT_MEDIA_TYPE)}")
            raw = file.read()
            try:
                meta = _vl_annotate(raw, ext, subject_hint, brief)
                meta["_engine"] = "vision"
                return ok(meta)
            except Exception as e:
                if not brief:  # 没有文字兜底，只能把识图错误如实抛回
                    return err(f"AI 识图失败：{e}", 5030, 500)
                # 有 brief：识图失败不阻断，退回文本扩写

        if not brief:
            return err("请上传图片（已配 DASHSCOPE_API_KEY 即可直接识图），或写一句话描述")
        try:
            meta = _llm_annotate(brief, subject_hint)
            meta["_engine"] = "text"
        except Exception as e:
            return err(f"AI 扩写失败：{e}", 5030, 500)
        return ok(meta)

    @app.route("/api/v1/images/extract-ppt", methods=["POST"])
    @require_role("teacher")
    def extract_ppt():
        """上传 .pptx → 抽出内嵌图片 → 视觉模型逐张判断是否适合做教学插图，
        以 SSE 流式**逐张**推送结果（每判完一张即发一帧），前端边出边展示、实时计数。

        本路由是平台 {code,message,data} 信封的例外——流开始前的校验失败仍返回
        标准 err() JSON；流开始后改发 SSE 帧：
          meta（总数/待处理/超上限略过）→ kept|dropped × N（各带 base64 预览）→ done（汇总）。
        kept 帧带完整图 + 识图元数据供入库；dropped 帧带小缩略图 + 舍弃理由供查看。"""
        from event_stream import sse_frame

        if not _dashscope_key():
            return err("PPT 取图需要视觉模型，请先配置 DASHSCOPE_API_KEY", 5030, 503)
        if "file" not in request.files or request.files["file"].filename == "":
            return err("请选择 PPT 文件")
        f = request.files["file"]
        if not f.filename.lower().endswith(".pptx"):
            return err("目前只支持 .pptx（旧版 .ppt 请先另存为 .pptx）")

        try:
            # request 必须在 generator 外读取（generator 执行时已脱离请求上下文）
            candidates = _extract_pptx_images(f.read())
        except ValueError as e:
            return err(str(e))
        total = len(candidates)
        truncated = max(0, total - _PPT_MAX_IMAGES)
        candidates = candidates[:_PPT_MAX_IMAGES]

        def judge(c):
            name, ext, raw = c
            try:
                return (name, ext, raw, _vl_judge_and_annotate(raw, ext))
            except Exception as e:
                print(f"[ppt] 判定失败(跳过) {name}: {e}")
                return (name, ext, raw, {"suitable": False, "reason": f"识别失败：{e}"})

        def generate():
            yield sse_frame("meta", {"total": total, "to_process": len(candidates), "truncated": truncated})
            kept_n = dropped_n = 0
            if candidates:
                with ThreadPoolExecutor(max_workers=5) as pool:
                    futs = [pool.submit(judge, c) for c in candidates]
                    for fut in as_completed(futs):       # 谁先判完先发谁，前端一张张冒出来
                        name, ext, raw, r = fut.result()
                        if r.get("suitable"):
                            kept_n += 1
                            yield sse_frame("kept", {
                                "name": name,
                                "media_type": "gif" if ext == ".gif" else "static",
                                "image_b64": base64.b64encode(raw).decode(),
                                "subject": r.get("subject", "other"),
                                "topic": r.get("topic", ""),
                                "keywords": r.get("keywords", []),
                                "llm_desc": r.get("llm_desc", ""),
                                "caption": r.get("caption", ""),
                                "reason": r.get("reason", ""),
                            })
                        else:
                            dropped_n += 1
                            thumb_b64, mime = _thumb_b64(raw, ext)
                            yield sse_frame("dropped", {
                                "name": name,
                                "mime": mime,
                                "image_b64": thumb_b64,
                                "reason": r.get("reason", ""),
                            })
            yield sse_frame("done", {"kept": kept_n, "dropped": dropped_n,
                                     "total": total, "truncated": truncated})

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @app.route("/api/v1/images", methods=["POST"])
    @require_role("teacher")
    def upload_image():
        """提交图片 + 最终元数据，入全局图库。multipart：
        file + subject + topic + keywords(逗号分隔) + llm_desc + caption。"""
        teacher_id = _my_teacher_id()
        if not teacher_id:
            return err("请先创建教师卡片", 4040, 404)
        if "file" not in request.files or request.files["file"].filename == "":
            return err("请选择图片文件")

        file = request.files["file"]
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in EXT_MEDIA_TYPE:
            return err(f"不支持的图片类型，支持：{', '.join(EXT_MEDIA_TYPE)}")

        form = request.form
        subject = (form.get("subject") or "").strip()
        if subject not in SUBJECTS:
            return err("请选择学科")
        keywords = [k.strip() for k in re.split(r"[,，、;；\n]+", form.get("keywords", "")) if k.strip()]
        caption = (form.get("caption") or "").strip()
        llm_desc = (form.get("llm_desc") or "").strip()
        if not keywords:
            return err("关键词不能为空（检索全靠它）")
        if not caption or not llm_desc:
            return err("图注和给 AI 的描述都要填")

        raw = file.read()
        if not raw:
            return err("文件为空")
        meta = {"topic": (form.get("topic") or "").strip(),
                "keywords": keywords, "caption": caption, "llm_desc": llm_desc}
        entry, e = _commit_image(raw, ext, subject, meta, teacher_id)
        if e:
            return err(e)
        return ok(_with_url(entry), "已入库，讲课时即可被检索调用")

    @app.route("/api/v1/images/<image_id>", methods=["PATCH"])
    @require_role("teacher")
    def update_image(image_id):
        """启用/停用或微调元数据。停用后 status!=active，检索层不再返回。
        只能改自己上传的图；预置精选图对教师端只读。"""
        data = request.json or {}
        teacher_id = _my_teacher_id()
        with _index_lock:
            index = _load_index()
            entry = next((e for e in index["images"] if e.get("id") == image_id), None)
            if not entry:
                return err("图片不存在", 4040, 404)
            if entry.get("source") != "teacher_upload" or entry.get("uploaded_by") != teacher_id:
                return err("只能修改自己上传的图片", 4030, 403)
            if "status" in data:
                if data["status"] not in ("active", "disabled"):
                    return err("status 不合法")
                entry["status"] = data["status"]
            if "keywords" in data:
                kws = data["keywords"]
                if isinstance(kws, str):
                    kws = [k.strip() for k in re.split(r"[,，、;；\n]+", kws) if k.strip()]
                entry["keywords"] = [str(k).strip() for k in kws if str(k).strip()]
            for fld in ("topic", "caption", "llm_desc"):
                if fld in data:
                    entry[fld] = (data[fld] or "").strip()
            _save_index(index)
        return ok(_with_url(entry))

    @app.route("/api/v1/images/<image_id>", methods=["DELETE"])
    @require_role("teacher")
    def delete_image(image_id):
        """删除：从 index 移除并删文件。仅允许删教师自己上传的。"""
        teacher_id = _my_teacher_id()
        with _index_lock:
            index = _load_index()
            entry = next((e for e in index["images"] if e.get("id") == image_id), None)
            if not entry:
                return err("图片不存在", 4040, 404)
            if entry.get("source") != "teacher_upload" or entry.get("uploaded_by") != teacher_id:
                return err("只能删除自己上传的图片", 4030, 403)
            index["images"] = [e for e in index["images"] if e.get("id") != image_id]
            _save_index(index)
        try:
            fp = os.path.join(IMAGES_ROOT, entry["file"])
            if os.path.isfile(fp):
                os.remove(fp)
        except OSError:
            pass
        return ok({"id": image_id}, "已删除")
