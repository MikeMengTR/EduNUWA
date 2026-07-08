"""M2 蒸馏集成 — 通过 Web 平台一键蒸馏教师 Skill"""
import json
import os
from datetime import datetime, timezone
from flask import request
from openai import OpenAI
from auth import require_auth, require_role, ok, err
from teachers import (get_teacher_dir, load_teacher_card, load_skill_profile,
                       load_skill_md, save_teacher_card)

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

def _gather_transcripts(teacher_id):
    """收集教师的所有 transcript，合并为带 segment 编号的语料文本。

    每行 `seg_id: text`——风格标签的 evidence 需要引用真实 seg 编号（H5 抗操纵）。
    返回 (corpus, files, valid_seg_ids)。
    """
    transcripts_dir = os.path.join(get_teacher_dir(teacher_id), "transcripts")
    if not os.path.exists(transcripts_dir):
        return "", [], set()

    lines = []
    valid_ids = set()
    files = sorted([f for f in os.listdir(transcripts_dir)
                    if f.endswith(".json") and not f.startswith("_")])
    for idx, f in enumerate(files):
        with open(os.path.join(transcripts_dir, f), "r", encoding="utf-8") as fp:
            data = json.load(fp)
            prefix = "" if len(files) == 1 else f"f{idx}_"
            for i, seg in enumerate(data.get("segments", [])):
                text = seg.get("text", "").strip()
                if not text:
                    continue
                sid = prefix + seg.get("segment_id", f"seg_{i+1:04d}")
                valid_ids.add(sid)
                lines.append(f"{sid}: {text}")

    corpus = "\n".join(lines)
    # 截断到 ~8000 字以免超出 token 限制
    if len(corpus) > 8000:
        corpus = corpus[:8000]
    return corpus, files, valid_ids

def _run_distillation(teacher_id, card, corpus, file_list):
    """调用 DeepSeek API 蒸馏教学风格"""
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    name = card.get("display_name", card.get("real_name", "教师"))
    subject = card.get("subject", "未分类")

    prompt = f"""你是一位教学风格分析专家。请分析以下教师的教学转写文本，提取该教师的教学风格。
教师：{name}，学科：{subject}

你有 {len(file_list)} 份转写文件（共约 {len(corpus)} 字）。

请从以下 7 个维度分析，输出严格的 Markdown 格式：

# TeacherSkill: {name}

## Skill Purpose
本 Skill 用于将{name}的讲解思维迁移到新的教学任务中。核心迁移目标是什么？

## Teaching Philosophy
提炼 3-5 条核心理念，每条附从转写中的引证。

## Explanation Pattern
描述该教师讲解新概念的典型递进序列（Step 1 → Step N），引用转写中的典型句式。

## Blackboard Policy
推测该教师会写什么、不写什么、何时写。

## Speech Policy
提取口头禅、句式偏好、互动模式、人称习惯。

## Output Contract
定义下游 Agent 应输出的事件类型（speak/board/formula/table/pause/quiz）及触发条件。

## Fingerprint
用 JSON 输出风格指纹（pace/detail/abstraction/interactivity/humor/rigor，0-1 之间）：

```json
{{"pace":0.0,"detail":0.0,"abstraction":0.0,"interactivity":0.0,"humor":0.0,"rigor":0.0}}
```

## Style Tags
提炼 5-8 个开放风格标签——学生会用来形容这位老师的简短形容词短语（如「设问自答」「爱用生活类比」「板书极简」）。
每个标签必须附 evidence：支撑它的 1-2 个转写 seg 编号（必须是转写中真实出现的编号，无证据的标签不要写）。
dimension 从 pace/detail/abstraction/interactivity/humor/rigor 中选或填 null。
用 JSON 数组输出：

```json
[{{"text":"设问自答","dimension":"interactivity","confidence":0.8,"evidence":["seg_0002"]}}]
```

---
以下是教师的教学转写文本（每段带编号）：

{corpus}
"""
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "你是一位教学风格分析专家，擅长从教学转写中提炼教师的教学模式和风格特征。请严格按照要求的 Markdown 格式输出。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=4096,
    )
    return response.choices[0].message.content

def _parse_fingerprint(skill_md):
    """从 Skill Markdown 中提取指纹 JSON（第一个 JSON 对象块）"""
    import re
    for match in re.finditer(r'```json\s*([\s\S]*?)\s*```', skill_md):
        try:
            obj = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "pace" in obj:
            return obj
    return None

_STYLE_DIMS = {"pace", "detail", "abstraction", "interactivity", "humor", "rigor"}

def _parse_style_tags(skill_md, valid_seg_ids):
    """从 Skill Markdown 中提取开放风格标签（第一个 JSON 数组块）。

    H5 抗操纵：evidence 必须指向真实 seg 编号，无有效证据的标签丢弃。
    """
    import re
    tags_raw = None
    for match in re.finditer(r'```json\s*([\s\S]*?)\s*```', skill_md):
        try:
            obj = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(obj, list):
            tags_raw = obj
            break
    if not tags_raw:
        return []

    style_tags = []
    for item in tags_raw:
        if not isinstance(item, dict) or not item.get("text"):
            continue
        ev = [e for e in (item.get("evidence") or []) if e in valid_seg_ids]
        if not ev:
            continue
        dim = item.get("dimension")
        if dim not in _STYLE_DIMS:
            dim = None
        conf = item.get("confidence")
        if not isinstance(conf, (int, float)) or not (0.0 <= conf <= 1.0):
            conf = 0.6
        style_tags.append({
            "text": str(item["text"]).strip(),
            "dimension": dim,
            "source": "auto",
            "confidence": round(float(conf), 2),
            "evidence": ev,
            "cluster_id": None,
        })
    return style_tags

def _build_skill_profile(teacher_id, card, fingerprint, style_tags=None):
    """构建 skill_profile.json（v2：含开放风格标签，供 M3 匹配与进化闭环消费）"""
    version = 1
    skills_dir = os.path.join(get_teacher_dir(teacher_id), "skills")
    if os.path.exists(skills_dir):
        existing = [d for d in os.listdir(skills_dir) if d.startswith("v") and d[1:].isdigit()]
        if existing:
            version = max(int(d[1:]) for d in existing) + 1

    fp_dict = {}
    if fingerprint:
        dims = ["pace", "detail", "abstraction", "interactivity", "humor", "rigor"]
        for dim in dims:
            fp_dict[dim] = {"value": fingerprint.get(dim, 0.5), "confidence": 0.7, "source": ["auto"]}

    return {
        "skill_id": f"S_{teacher_id.replace('_','')}_v{version}",
        "teacher_id": teacher_id,
        "teacher_name": card.get("real_name", ""),
        "display_name": card.get("display_name", ""),
        "subject": card.get("subject", ""),
        "version": version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fingerprint": fp_dict,
        "style_tags": style_tags or [],
        "style_embeddings_model": "bge-base-zh-v1.5",
        "pedagogy": {},
        "tags": [],
        "quality": {"overall_grade": "NA"},
    }, version

def register_routes(app):
    @app.route("/api/v1/teachers/<teacher_id>/distill", methods=["POST"])
    @require_role("teacher")
    def distill_teacher(teacher_id):
        if not DEEPSEEK_API_KEY:
            return err("请先配置 DEEPSEEK_API_KEY", 5030, 503)

        card = load_teacher_card(teacher_id)
        if not card:
            return err("教师不存在", 4040, 404)
        if card.get("user_id") != request.user_id:
            return err("无权操作此教师", 4030, 403)

        # 收集转写语料
        corpus, files, valid_seg_ids = _gather_transcripts(teacher_id)
        if not corpus:
            return err("该教师没有已处理的素材，请先上传教学素材", 4040, 404)

        try:
            # 调用 DeepSeek 蒸馏
            skill_md = _run_distillation(teacher_id, card, corpus, files)

            # 提取指纹 + 开放风格标签（v2）
            fingerprint = _parse_fingerprint(skill_md)
            style_tags = _parse_style_tags(skill_md, valid_seg_ids)

            # 构建 profile
            profile, version = _build_skill_profile(teacher_id, card, fingerprint, style_tags)

            # 保存文件
            out_dir = os.path.join(get_teacher_dir(teacher_id), "skills", f"v{version}")
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, "TeacherSkill.md"), "w", encoding="utf-8") as f:
                f.write(skill_md)
            with open(os.path.join(out_dir, "skill_profile.json"), "w", encoding="utf-8") as f:
                json.dump(profile, f, ensure_ascii=False, indent=2)

            return ok({
                "version": version,
                "teacher_id": teacher_id,
                "corpus_size": len(corpus),
                "files_used": len(files),
                "fingerprint": fingerprint,
                "style_tags_count": len(style_tags),
                "skill_md_preview": skill_md[:300],
            }, "蒸馏完成")
        except Exception as e:
            return err(f"蒸馏失败: {str(e)}", 5000, 500)

    @app.route("/api/v1/teachers/<teacher_id>/distill/status", methods=["GET"])
    @require_auth
    def distill_status(teacher_id):
        """检查教师是否已有蒸馏的 Skill"""
        skill_md = load_skill_md(teacher_id)
        profile = load_skill_profile(teacher_id)
        card = load_teacher_card(teacher_id)

        # 检查是否有 transcript
        transcripts_dir = os.path.join(get_teacher_dir(teacher_id), "transcripts")
        transcript_count = 0
        if os.path.exists(transcripts_dir):
            transcript_count = len([f for f in os.listdir(transcripts_dir)
                                    if f.endswith(".json") and not f.startswith("_")])

        return ok({
            "teacher_id": teacher_id,
            "has_skill": skill_md is not None,
            "has_profile": profile is not None,
            "transcript_count": transcript_count,
            "ready_to_distill": transcript_count > 0,
            "fingerprint": profile.get("fingerprint") if profile else None,
            "quality": profile.get("quality") if profile else None,
        })
