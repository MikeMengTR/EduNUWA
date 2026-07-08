"""M4 Orchestrator + M5 Runtime 集成端点"""
import json
import os
import sys
import secrets
from datetime import datetime, timezone
from flask import request, Response, send_file

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from auth import require_auth, ok, err
from teachers import get_teacher_dir, load_teacher_card, load_skill_md

DATA_DIR = os.path.join(_project_root, "data")
SESSIONS_ROOT = os.path.join(DATA_DIR, "sessions")

# ---- 图库查询扩展：学生原句先过一遍轻量大模型抽成检索关键词，再去图库子串检索 ----
# 子串检索只认原句里逐字出现的词（"什么是MLP" 不含 "神经网络" 就漏图）。这里把问题归一成
# 概念关键词（含中文全称/缩写/别名），拼到原句后参与检索以扩召回。代价是讲课前多一次轻量
# LLM 调用——已做进程内缓存 + 失败/超时退回原句，绝不阻断讲课；置 False 可一键关闭。
USE_IMAGE_QUERY_EXPANSION = True
_IMG_QUERY_CACHE = {}            # question -> [keywords]（进程内缓存，免重复扩展）
_IMG_QUERY_CACHE_MAX = 512
_IMG_QUERY_PROMPT = """学生提问：{q}

请抽出用于「教学插图库」检索的中文关键词（会和图库里每张图的关键词逐一匹配）：
- 先锁定问题真正在问的 1-3 个核心概念；
- 对每个核心概念，列出它的**各种叫法**：中文全称、简称、英文缩写、同义别名（如「多层感知机」→「多层感知机」「MLP」「感知机」「前馈神经网络」；「高斯分布」→「高斯分布」「正态分布」）；
- **不要发散到「相关但不同」的概念**（解题方法、子知识点、所属学科等），那会误召回无关图；
- 原子短词，不要整句，也不要「什么/怎么/为什么/图」这类泛词。
只输出 JSON：{{"keywords": ["...", "..."]}}"""


def _expand_image_query(question):
    """把学生问题抽成图库检索关键词。失败/超时/未配 key 一律返回 []（退回原句检索）。"""
    if not USE_IMAGE_QUERY_EXPANSION:
        return []
    q = (question or "").strip()
    if not q:
        return []
    if q in _IMG_QUERY_CACHE:
        return _IMG_QUERY_CACHE[q]
    terms = []
    try:
        import re
        from openai import OpenAI
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            return []
        # max_retries=0：扩展是非必需增强，DeepSeek 慢/失败就「立刻」退回原句检索，
        # 绝不重试——否则默认重试 2 次会在每讲前白白拖十几秒、刷屏 Retrying 日志。
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com",
                        max_retries=0, timeout=4)
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你把学生的提问抽成教学图库检索用的中文关键词。只输出 JSON。"},
                {"role": "user", "content": _IMG_QUERY_PROMPT.format(q=q)},
            ],
            temperature=0,
            max_tokens=120,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        kws = data.get("keywords", [])
        if isinstance(kws, str):
            kws = re.split(r"[\s,，、;；]+", kws)
        terms = [str(k).strip() for k in kws if str(k).strip()][:12]
    except Exception as e:
        print(f"[image] 查询扩展失败(退回原句检索): {e}")
        terms = []
    if len(_IMG_QUERY_CACHE) > _IMG_QUERY_CACHE_MAX:
        _IMG_QUERY_CACHE.clear()
    _IMG_QUERY_CACHE[q] = terms
    return terms


def _image_search_query(question):
    """原句 + 扩展关键词拼成检索串（retrieve_candidates 的子串逻辑不变，只是草堆更全）。"""
    extra = _expand_image_query(question)
    return f"{question} {' '.join(extra)}" if extra else question


# 不同教师分配不同的 edge-tts 语音（每位教师都有各自的声音风格）
EDGE_VOICE_MAP = {
    "T_20260604_001": "zh-CN-YunxiNeural",    # 男声 - 稳重 (概率论)
    "T_20260604_002": "zh-CN-YunjianNeural",   # 男声 - 明亮 (高等数学)
    "T_20260604_003": "zh-CN-YunyangNeural",   # 男声 - 活力 (机器学习)
    "T_20260604_004": "zh-CN-XiaoxiaoNeural",  # 女声 - 亲切 (思政)
    "T_20260604_005": "zh-CN-XiaoyiNeural",    # 女声 - 知性 (历史)
    "T_20260604_006": "zh-CN-YunxiaNeural",    # 男声 - 深沉 (线性代数)
}

def _get_edge_voice(teacher_id: str) -> str:
    """根据教师ID返回对应的 edge-tts 语音。"""
    return EDGE_VOICE_MAP.get(teacher_id, "zh-CN-YunxiNeural")


def get_session_dir(session_id):
    return os.path.join(SESSIONS_ROOT, session_id)

def load_session_state(session_id):
    path = os.path.join(get_session_dir(session_id), "session_state.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_session_state(session_id, state):
    d = get_session_dir(session_id)
    os.makedirs(os.path.join(d, "events"), exist_ok=True)
    os.makedirs(os.path.join(d, "audio"), exist_ok=True)
    with open(os.path.join(d, "session_state.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def register_routes(app):
    # ---- M4: 创建学习会话 ----
    @app.route("/api/v1/sessions", methods=["POST"])
    @require_auth
    def create_session():
        data = request.json
        teacher_id = data.get("teacher_id", "").strip()
        mode = data.get("mode", "ondemand")  # ondemand | follow

        if not teacher_id:
            return err("请指定教师")

        card = load_teacher_card(teacher_id)
        if not card:
            return err("教师不存在", 4040, 404)

        session_id = f"SES_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(3)}"

        state = {
            "session_id": session_id,
            "student_id": request.user_id,
            "teacher_id": teacher_id,
            "teacher_name": card.get("display_name", ""),
            "mode": mode,
            "course_progress": {"current_chapter_id": None, "current_topic_id": None, "covered_topic_ids": []},
            "qa_history": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        save_session_state(session_id, state)
        return ok(state, "会话创建成功")

    # ---- M4: 发送问题，生成教学事件 ----
    @app.route("/api/v1/sessions/<session_id>/ask", methods=["POST"])
    @require_auth
    def session_ask(session_id):
        state = load_session_state(session_id)
        if not state:
            return err("会话不存在", 4040, 404)

        data = request.json
        question = data.get("question", "").strip()
        if not question:
            return err("请输入问题")

        teacher_id = state["teacher_id"]
        turn = len(state["qa_history"]) + 1

        # 找 Skill 文件路径
        skill_path = None
        skills_dir = os.path.join(get_teacher_dir(teacher_id), "skills")
        if os.path.exists(skills_dir):
            versions = sorted([d for d in os.listdir(skills_dir) if d.startswith("v")],
                            key=lambda v: int(v[1:]) if v[1:].isdigit() else 0, reverse=True)
            if versions:
                md_path = os.path.join(skills_dir, versions[0], "TeacherSkill.md")
                if os.path.exists(md_path):
                    skill_path = md_path

        try:
            from modules.M4_orchestrator.pipeline import OrchestratorPipeline
            pipeline = OrchestratorPipeline()
            result = pipeline.run(
                session_id=session_id,
                user_question=question,
                teacher_skill_path=skill_path,
                mode=state.get("mode", "ondemand"),
            )

            # 记录 QA
            state["qa_history"].append({
                "turn": turn,
                "question": question,
                "events_path": result.get("events_path", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            save_session_state(session_id, state)

            return ok({
                "turn": turn,
                "question": question,
                "session_id": session_id,
                "result": result,
            })
        except ImportError as e:
            # M4 未加载，fallback 到简单对话
            return ok({
                "turn": turn,
                "question": question,
                "session_id": session_id,
                "warning": f"M4 模块未加载: {e}，使用简单对话模式",
            })
        except Exception as e:
            return err(f"生成教学事件失败: {e}", 5000, 500)

    # ---- 获取会话状态 ----
    @app.route("/api/v1/sessions/<session_id>", methods=["GET"])
    @require_auth
    def get_session(session_id):
        state = load_session_state(session_id)
        if not state:
            return err("会话不存在", 4040, 404)
        return ok(state)

    # ---- 获取某轮 teaching_events ----
    @app.route("/api/v1/sessions/<session_id>/events/<int:turn>", methods=["GET"])
    @require_auth
    def get_session_events(session_id, turn):
        events_path = os.path.join(get_session_dir(session_id), "events", f"turn_{turn}.json")
        if not os.path.exists(events_path):
            return err("事件文件不存在", 4040, 404)
        with open(events_path, "r", encoding="utf-8") as f:
            return ok(json.load(f))

    # ---- M5: 生成 TTS（如果 M5 可用） ----
    @app.route("/api/v1/sessions/<session_id>/tts", methods=["POST"])
    @require_auth
    def generate_tts(session_id):
        state = load_session_state(session_id)
        if not state:
            return err("会话不存在", 4040, 404)

        data = request.json
        turn = data.get("turn", 1)
        events_path = os.path.join(get_session_dir(session_id), "events", f"turn_{turn}.json")
        if not os.path.exists(events_path):
            return err(f"第 {turn} 轮教学事件不存在", 4040, 404)

        audio_dir = os.path.join(get_session_dir(session_id), "audio", f"turn_{turn}")
        os.makedirs(audio_dir, exist_ok=True)

        teacher_id = state["teacher_id"]
        card = load_teacher_card(teacher_id)
        voice_id = card.get("voice_id", "default") if card else "default"

        try:
            from modules.M5_runtime.tts_service import generate_tts_batch
            result = generate_tts_batch(
                events_path=events_path,
                output_dir=audio_dir,
                voice_id=voice_id,
            )
            return ok(result)
        except ImportError:
            return ok({"warning": "M5 模块未加载，TTS 不可用"})
        except Exception as e:
            return err(f"TTS 生成失败: {e}", 5000, 500)

    # ---- M5: 构建播放数据 ----
    @app.route("/api/v1/sessions/<session_id>/playback", methods=["POST"])
    @require_auth
    def build_playback(session_id):
        state = load_session_state(session_id)
        if not state:
            return err("会话不存在", 4040, 404)

        data = request.json
        turn = data.get("turn", 1)
        events_path = os.path.join(get_session_dir(session_id), "events", f"turn_{turn}.json")
        audio_manifest_path = os.path.join(get_session_dir(session_id), "audio", f"turn_{turn}", "audio_manifest.json")
        teacher_card_path = os.path.join(get_teacher_dir(state["teacher_id"]), "teacher_card.json")

        if not os.path.exists(events_path):
            return err(f"第 {turn} 轮教学事件不存在", 4040, 404)

        try:
            from modules.M5_runtime.build_playback import build_playback_data
            result = build_playback_data(
                events_path=events_path,
                audio_manifest=audio_manifest_path if os.path.exists(audio_manifest_path) else None,
                output_dir=get_session_dir(session_id),
                teacher_card=teacher_card_path if os.path.exists(teacher_card_path) else None,
            )
            return ok(result)
        except ImportError:
            return ok({"warning": "M5 模块未加载"})
        except Exception as e:
            return err(f"构建播放数据失败: {e}", 5000, 500)

    # ---- M5: 文本转语音（GPT-SoVITS + edge-tts 双模式） ----
    @app.route("/api/v1/tts", methods=["POST"])
    @require_auth
    def text_to_speech():
        """将文本转为语音，返回 WAV 音频。优先 GPT-SoVITS，失败则用 edge-tts。"""
        data = request.json
        text = data.get("text", "").strip()
        teacher_id = data.get("teacher_id", "")
        engine = data.get("engine", "auto")  # auto | sovits | edge

        if not text:
            return err("请输入要转换的文本")

        # ---- 尝试 GPT-SoVITS（该老师专属微调音色）----
        if engine in ("auto", "sovits"):
            try:
                import voice_service, io
                import soundfile as sf

                va = voice_service.synthesize(teacher_id, text) if teacher_id else None
                if va:
                    sr, audio_np = va
                    buf = io.BytesIO()
                    sf.write(buf, audio_np, sr, format='WAV')
                    buf.seek(0)
                    return Response(buf.read(), mimetype="audio/wav",
                                  headers={"Content-Disposition": "inline; filename=speech.wav",
                                           "X-TTS-Engine": "sovits"})
                if engine == "sovits":
                    return err("该老师暂无可用专属音色", 5030, 503)
                # auto 模式：无专属音色则继续 edge-tts
            except Exception as e:
                if engine == "sovits":
                    return err(f"GPT-SoVITS TTS 失败: {e}", 5000, 500)
                # auto 模式则继续尝试 edge-tts

        # ---- Edge TTS 备选 ----
        if engine in ("auto", "edge"):
            try:
                import edge_tts, asyncio, io, tempfile, subprocess, os

                voice = _get_edge_voice(teacher_id)  # 每位教师不同声音
                speed = 1.0

                async def _run():
                    communicate = edge_tts.Communicate(text, voice, rate=f"{'+' if speed>=1 else ''}{int((speed-1)*100)}%")
                    mp3_data = b""
                    async for chunk in communicate.stream():
                        if chunk["type"] == "audio":
                            mp3_data += chunk["data"]
                    return mp3_data

                mp3_bytes = asyncio.run(_run())

                # MP3 转 WAV（使用 ffmpeg 或直接返回 MP3）
                tmp_mp3 = os.path.join(tempfile.gettempdir(), f"tts_{os.getpid()}.mp3")
                with open(tmp_mp3, "wb") as f:
                    f.write(mp3_bytes)

                tmp_wav = tmp_mp3.replace(".mp3", ".wav")
                try:
                    subprocess.run(["ffmpeg", "-y", "-i", tmp_mp3, "-acodec", "pcm_s16le",
                                  "-ar", "22050", tmp_wav], capture_output=True, timeout=15)
                    with open(tmp_wav, "rb") as f:
                        wav_bytes = f.read()
                    os.remove(tmp_wav)
                except Exception:
                    # ffmpeg 不可用，直接返回 MP3
                    wav_bytes = mp3_bytes
                    mimetype = "audio/mpeg"
                finally:
                    try: os.remove(tmp_mp3)
                    except: pass

                return Response(wav_bytes, mimetype="audio/mpeg" if not wav_bytes.startswith(b"RIFF") else "audio/wav",
                              headers={"Content-Disposition": "inline; filename=speech.mp3",
                                       "X-TTS-Engine": "edge"})
            except ImportError:
                return err("TTS 模块未安装。请安装: pip install edge-tts", 5030, 503)
            except Exception as e:
                return err(f"Edge TTS 失败: {e}", 5000, 500)

        return err("TTS 引擎不可用", 5030, 503)

    # ---- M5: 获取可用音色列表 ----
    @app.route("/api/v1/voices", methods=["GET"])
    @require_auth
    def list_voices():
        """返回可用的 TTS 音色"""
        voices = []
        # Song Hao 模型（预训练）
        songhao_dir = os.path.join(_project_root, "GPT-SoVITS-v2pro", "GPT-SoVITS-v2pro", "GPT_weights_v2Pro")
        if os.path.exists(songhao_dir):
            ckpt_files = [f for f in os.listdir(songhao_dir) if f.endswith(".ckpt")]
            if ckpt_files:
                voices.append({
                    "voice_id": "songhao",
                    "name": "示例老师",
                    "description": "GPT-SoVITS 微调模型（高等数学教师）",
                    "checkpoints": len(ckpt_files),
                })

        # 检查是否有其他教师的音色
        teachers_root = os.path.join(os.path.dirname(__file__), "..", "data", "teachers")
        if os.path.exists(teachers_root):
            for tid in os.listdir(teachers_root):
                card = load_teacher_card(tid)
                if card and card.get("voice_id") and card["voice_id"] != "songhao":
                    voices.append({
                        "voice_id": card["voice_id"],
                        "name": card.get("display_name", tid),
                        "description": f"教师 {card.get('display_name', tid)} 的音色",
                    })

        return ok(voices)

    # ---- 音频文件服务（公开，因为浏览器 audio 标签无法带鉴权 header） ----
    @app.route("/api/v1/audio/<path:rel_path>", methods=["GET"])
    def serve_audio(rel_path):
        """提供音频/数据文件访问。JSON 需鉴权，音频公开。"""
        safe_path = os.path.normpath(rel_path)
        if safe_path.startswith(".."):
            return err("无效路径", 4000, 400)

        # playback_data.json 公开访问（session ID 本身就是随机密钥）
        if safe_path.endswith("playback_data.json"):
            pass  # 公开
        elif safe_path.endswith(".json"):
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            from auth import tokens
            if not tokens.get(token):
                return err("请先登录", 4010, 401)

        # 从 sessions 或 teachers 目录提供
        ext = os.path.splitext(safe_path)[1].lower()
        mime_map = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".json": "application/json"}
        mimetype = mime_map.get(ext, "audio/wav")

        for base in [
            os.path.join(_project_root, "data", "sessions"),
            os.path.join(_project_root, "data", "teachers"),
            os.path.join(_project_root, "GPT-SoVITS-v2pro", "data", "audio_output"),
        ]:
            full_path = os.path.join(base, safe_path)
            if os.path.exists(full_path) and os.path.isfile(full_path):
                return send_file(full_path, mimetype=mimetype)

        return err("文件不存在", 4040, 404)

    # ---- 教学插图服务（公开：<img> 标签无法带鉴权 header，且图库是公开教学素材） ----
    @app.route("/api/v1/media/<path:rel_path>", methods=["GET"])
    def serve_media(rel_path):
        """提供 data/media_library/images/ 下的教学插图。"""
        safe_path = os.path.normpath(rel_path).replace("\\", "/")
        if safe_path.startswith("..") or os.path.isabs(safe_path):
            return err("无效路径", 4000, 400)

        ext = os.path.splitext(safe_path)[1].lower()
        mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml"}
        if ext not in mime_map:
            return err("不支持的文件类型", 4000, 400)

        from media_library import IMAGES_ROOT
        full_path = os.path.join(IMAGES_ROOT, safe_path)
        if os.path.isfile(full_path):
            resp = send_file(full_path, mimetype=mime_map[ext])
            # 入库后文件不可变（换图必换 ID），可放心长缓存
            resp.headers["Cache-Control"] = "public, max-age=86400"
            return resp
        return err("文件不存在", 4040, 404)

    # ---- M5: 教学演示（AI→teaching_events→TTS→playback_data） ----
    @app.route("/api/v1/chat/<teacher_id>/demo", methods=["POST"])
    @require_auth
    def teaching_demo(teacher_id):
        """AI 回复 → 解析为教学事件 → TTS → 播放数据，返回给 M5 PlayerRuntime"""
        card = load_teacher_card(teacher_id)
        if not card:
            return err("教师不存在", 4040, 404)

        data = request.json
        question = data.get("question", "").strip()
        if not question:
            return err("请输入问题")

        # 1. 用蒸馏 Skill 让 AI 生成结构化教学回复
        from chat import _build_system_prompt
        from openai import OpenAI
        import os as _os

        user_id = request.user_id
        history_digest = _history_digest(user_id, teacher_id)
        system_prompt = _build_system_prompt(teacher_id, card)

        # 教学插图：按问题检索候选注入 prompt，LLM 只能引用候选内的 ID
        # 先把原句过一遍轻量 LLM 扩成关键词（含缩写/别名），再做子串检索以扩召回
        from media_library import retrieve_candidates, build_catalog, build_image_prompt_block
        image_candidates = retrieve_candidates(_image_search_query(question))
        image_catalog = build_catalog(image_candidates)
        demo_prompt = _build_demo_prompt(system_prompt, question, history_digest,
                                         build_image_prompt_block(image_candidates))

        api_key = _os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            return err("请配置 DEEPSEEK_API_KEY", 5030, 503)

        # 立刻后台预热该老师音色（不等 LLM），缩短前端首句等待
        _start_voice_warmup(teacher_id, tag="teaching_demo")

        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": demo_prompt}],
            temperature=0.7, max_tokens=2000,
        )
        ai_text = response.choices[0].message.content

        # 2. 解析为 teaching_events（catalog 内的 [image] 才会产出事件）
        events = _parse_demo_response(ai_text, image_catalog=image_catalog)
        if not events:
            return err("无法解析教学事件", 5000, 500)

        # 3. 流式：写事件清单，前端逐句按需合成（不在此预先合成全部音频）
        session_id = _new_session_id()
        _persist_demo_events(session_id, teacher_id, card.get("voice_id", ""), events)

        avatar_url, avatar_url_alt = _avatar_urls(teacher_id, card)

        # 4. 把教学大纲喂给 AI，生成一段开场引入语作为右侧文字回答
        summary = _generate_intro(client, question, events, card, history_digest)

        # 5. 讲课写回对话历史（下次提问可衔接）
        _append_demo_history(user_id, teacher_id, question, events, summary, session_id)

        return ok({
            "session_id": session_id,
            "teacher_id": teacher_id,
            "events": events,
            "events_count": len(events),
            "avatar_url": avatar_url,
            "avatar_url_alt": avatar_url_alt,
            "summary": summary,
            "ai_response": ai_text[:300],
        })

    @app.route("/api/v1/chat/<teacher_id>/demo/stream", methods=["POST"])
    @require_auth
    def teaching_demo_stream(teacher_id):
        """teaching_demo 的流式版本：DeepSeek 边生成边解析 events 边以 SSE 推送。

        注意：本路由是平台 {code,message,data} 响应信封的例外——流开始前的
        校验失败仍返回标准 err() JSON，流开始后改发 SSE 帧：
          meta → event×N → summary → done，异常时 error（partial 表示已有
          部分事件可继续播放）。帧格式见 event_stream.sse_frame。
        """
        from flask import stream_with_context
        from chat import _build_system_prompt
        from openai import OpenAI
        from event_stream import LineAssembler, DemoEventParser, sse_frame, SSE_PING
        from voice_service import _split_for_stability
        import threading
        import queue as _queue
        import os as _os

        card = load_teacher_card(teacher_id)
        if not card:
            return err("教师不存在", 4040, 404)

        # request 数据必须在 generator 外读取（generator 执行时已脱离请求上下文）
        data = request.json
        question = (data.get("question") or "").strip()
        if not question:
            return err("请输入问题")

        api_key = _os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            return err("请配置 DEEPSEEK_API_KEY", 5030, 503)

        user_id = request.user_id  # generator 内无请求上下文，此处取好
        history_digest = _history_digest(user_id, teacher_id)
        system_prompt = _build_system_prompt(teacher_id, card)

        # 教学插图：原句先过轻量 LLM 扩成关键词（含缩写/别名）再做子串检索以扩召回
        # （多一次轻量调用，已缓存+超时退回原句；USE_IMAGE_QUERY_EXPANSION 可关）
        from media_library import retrieve_candidates, build_catalog, build_image_prompt_block
        image_candidates = retrieve_candidates(_image_search_query(question))
        image_catalog = build_catalog(image_candidates)
        demo_prompt = _build_demo_prompt(system_prompt, question, history_digest,
                                         build_image_prompt_block(image_candidates))
        session_id = _new_session_id()
        voice_id = card.get("voice_id", "")
        avatar_url, avatar_url_alt = _avatar_urls(teacher_id, card)

        # 音色预热与 LLM 生成并行
        _start_voice_warmup(teacher_id, tag="demo_stream")

        # intro（开场引入语）触发阈值：第 4 个 speak 或大纲累计 800 字符
        INTRO_SPEAK_TRIGGER = 4
        INTRO_CHARS_TRIGGER = 800
        SUMMARY_WAIT_TOTAL = 15  # 主流结束后等 summary 的上限（秒）

        def generate():
            all_events = []
            partial = False
            asm = LineAssembler()
            parser = DemoEventParser(image_catalog=image_catalog)
            intro_q = _queue.Queue(maxsize=1)
            state = {"intro_started": False, "summary_sent": False,
                     "summary_text": "", "history_written": False}

            def _start_intro():
                if state["intro_started"]:
                    return
                state["intro_started"] = True
                snapshot = list(all_events)

                def _worker():
                    try:
                        # 独立 client：不与主流共享连接
                        c2 = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
                        intro_q.put(_generate_intro(c2, question, snapshot, card, history_digest))
                    except Exception as ie:
                        print(f"[demo_stream] intro 线程异常(忽略): {ie}")
                        try:
                            intro_q.put("")
                        except Exception:
                            pass

                threading.Thread(target=_worker, daemon=True).start()

            def _poll_summary():
                """非阻塞检查 intro 是否完成，完成则返回 summary 帧。"""
                if state["summary_sent"] or not state["intro_started"]:
                    return None
                try:
                    text = intro_q.get_nowait()
                except _queue.Empty:
                    return None
                state["summary_sent"] = True
                state["summary_text"] = text
                return sse_frame("summary", {"text": text})

            def _write_history():
                """讲课写回对话历史（幂等；中断时也写——已讲的部分就是讲过）。"""
                if state["history_written"] or not all_events:
                    return
                state["history_written"] = True
                _append_demo_history(user_id, teacher_id, question,
                                     all_events, state["summary_text"], session_id)

            def _emit(e):
                # 长 speak 切成小句供前端逐句流式合成+播放（首句更早开口）。
                # text 保持整句不变 → 字幕仍按整句显示，不被切碎；segments 仅供音频层。
                if e.get("type") == "speak":
                    try:
                        segs = _split_for_stability(e.get("text") or "")
                        if len(segs) > 1:
                            e["segments"] = segs
                    except Exception:
                        pass
                all_events.append(e)
                return sse_frame("event", e)

            try:
                yield sse_frame("meta", {
                    "session_id": session_id,
                    "teacher_id": teacher_id,
                    "voice_id": voice_id,
                    "avatar_url": avatar_url,
                    "avatar_url_alt": avatar_url_alt,
                    "teacher_name": card.get("display_name", ""),
                })

                client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
                stream = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": demo_prompt}],
                    temperature=0.7, max_tokens=2000,
                    stream=True,
                )
                speak_count = 0
                chars_seen = 0
                try:
                    for chunk in stream:
                        delta = chunk.choices[0].delta.content if chunk.choices else None
                        if not delta:
                            continue
                        chars_seen += len(delta)
                        for line in asm.feed(delta):
                            for e in parser.feed_line(line):
                                yield _emit(e)
                                if e["type"] == "speak":
                                    speak_count += 1
                        if speak_count >= INTRO_SPEAK_TRIGGER or chars_seen >= INTRO_CHARS_TRIGGER:
                            _start_intro()
                        s = _poll_summary()
                        if s:
                            yield s
                finally:
                    try:
                        stream.close()
                    except Exception:
                        pass

                # 主流结束：flush 残行与未闭合公式（max_tokens 截断场景）
                for e in parser.feed_line(asm.flush()):
                    yield _emit(e)
                for e in parser.finish():
                    yield _emit(e)

                if not all_events:
                    yield sse_frame("error", {"message": "无法解析教学事件",
                                              "code": 5000, "partial": False})

            except GeneratorExit:
                # 客户端断开（如学生连发第二问 abort 旧流）：落盘已有事件、
                # 写回历史（summary 可能尚未生成，写空）后退出
                partial = True
                try:
                    _write_history()
                except Exception:
                    pass
                raise
            except Exception as ex:
                # DeepSeek 流异常：先把已解析出的残余事件吐给前端，再报 error
                partial = True
                try:
                    for e in parser.feed_line(asm.flush()):
                        yield _emit(e)
                    for e in parser.finish():
                        yield _emit(e)
                except Exception:
                    pass
                print(f"[demo_stream] LLM 流异常: {ex}")
                yield sse_frame("error", {"message": f"生成中断: {ex}",
                                          "code": 5000, "partial": bool(all_events)})
            finally:
                if all_events:
                    try:
                        _persist_demo_events(session_id, teacher_id, voice_id,
                                             all_events, partial=partial)
                    except Exception as pe:
                        print(f"[demo_stream] events.json 落盘失败: {pe}")

            # ---- 收尾（GeneratorExit 已 re-raise，走不到这里）----
            if all_events and not state["intro_started"]:
                _start_intro()  # 不足触发阈值的短回答：此时才起 intro
            if state["intro_started"] and not state["summary_sent"]:
                waited = 0
                while waited < SUMMARY_WAIT_TOTAL:
                    try:
                        text = intro_q.get(timeout=5)
                        state["summary_sent"] = True
                        state["summary_text"] = text
                        yield sse_frame("summary", {"text": text})
                        break
                    except _queue.Empty:
                        waited += 5
                        yield SSE_PING  # 保活注释帧
                if not state["summary_sent"]:
                    yield sse_frame("summary", {"text": ""})

            _write_history()  # 讲课写回对话历史（下次提问可衔接）

            yield sse_frame("done", {
                "session_id": session_id,
                "events_count": len(all_events),
                "partial": partial,
            })

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )


def _build_demo_prompt(system_prompt, question, history_digest="", image_block=""):
    """教学演示模式的 prompt（公式/板书规则与 course.py 的 _FORMAT_RULES 对应，
    改规则时两处一起改，见 CLAUDE.md 公式约定）。
    history_digest: 该学生与该老师的近期对话/讲课摘要，用于课与课之间的衔接。
    image_block: media_library.build_image_prompt_block 产出的【插图规则】段；
    无候选插图时为空串，此时 prompt 与无图库版本逐字节一致。"""
    history_block = history_digest.strip() if history_digest else "（这是你和这名学生的第一次对话，没有历史记录）"
    return f"""{system_prompt}

【前情提要】你和这名学生此前的对话与讲课记录摘要：
{history_block}

【衔接规则·重要】
- 只有当前情提要里确实出现过的内容，才可以用“刚才我们讲了”“上次聊到”这类衔接语提及；前情提要里没有的内容绝对禁止编造。前情提要为空（第一次对话）时直接开始讲解，不要假装有过先前对话。
- 如果学生的问题是在询问此前对话本身（例如“我们刚才聊了什么”“上节课讲到哪了”），不要把它当作新的教学主题去展开，直接用少量 [speak]（可配一条 [board:write_bullets] 列要点）基于前情提要简要回顾，最后问学生接下来想学什么。

请以教学演示模式回答学生的问题。你的回答必须包含两类内容：
1. **[speak]** 口头讲解文本（口语化，按照 Speech Policy 风格）
2. **[board]** 板书内容（标题、定义、公式、要点）

【公式规则·重要】
- 数学公式只能出现在 [board] 或 [formula] 行；统一用 $...$（行内）或 $$...$$（块级）包裹，禁止使用 \\( \\)、\\[ \\] 等其它定界符。分式、根号、上下标等复杂公式也一律用 $$...$$ 包裹。
- [board] 行（write_bullets/write_steps/write_summary）里写公式：简单符号直接用 Unicode（如 x²、x₀、Δx、μ、σ²、≤、→），复杂式才用 $...$ 包裹。**绝不要在板书行里写裸的 LaTeX 上下标 `_{{...}}`/`^{{...}}`（会原样显示成 _{{x=x_0}} 这样的乱码），也绝不要用求值竖线 `|`**——`|` 是 write_bullets/write_summary 多条要点的分隔符，写进公式会把内容拦腰切断。需要表达「在某点取值」时用文字，例如写「导数 dy/dx 在 x₀ 处的值」而不是 dy/dx|_{{x=x_0}}。
- [speak] 口播文本必须是纯口语，绝对不能包含 LaTeX 或公式符号（语音合成念不出来）。需要提到公式时改用自然语言，例如说“X 服从均值 μ、方差 σ 平方的正态分布”，而不是写出 X ~ N(μ, σ²) 或 \\(X \\sim N\\)。

【板书规则·重要】
- [board:xxx] 的板书类型只能用这 5 种：write_title（标题）、write_subtitle（小标题）、write_bullets（要点，多条用 | 分隔）、write_steps（步骤）、write_summary（小结）。禁止使用 write_definition、write_highlight 等其它类型。
- 需要做对比/表格时，单独用一行 [table]，格式为：[table] 表标题 | 列名1,列名2,列名3 | 第一行格1,第一行格2,第一行格3 | 第二行... （竖线 | 分隔每一行，英文逗号分隔单元格）。
- 不要使用 markdown 语法（如 **加粗**、# 号），直接写纯文字。

【讲解顺序·重要】
- 要讲解公式、表格、图片或关键板书时，必须**先输出对应的 [formula]/[table]/[image]/[board] 行**（让它先出现在黑板上），**紧接着再用 [speak] 讲解它**。
- 绝对不要先用 [speak] 把内容讲完、最后才补上 [formula]/[image]/[board]——那样学生在听讲解时黑板还是空的。正确顺序永远是「先上黑板，再开口讲」。{image_block}

请按以下格式输出，每个事件一行（注意：公式/板书都在讲解它的 [speak] 之前）：
[speak] 同学们好，今天我们来学习正态分布。
[board:write_title] 正态分布
[formula] $$f(x)=\\frac{{1}}{{\\sqrt{{2\\pi}}\\sigma}}e^{{-\\frac{{(x-\\mu)^2}}{{2\\sigma^2}}}}$$
[speak] 大家看黑板上这个概率密度函数，μ 是它的均值、σ 是标准差，这两个参数决定了曲线的形状。
[board:write_bullets] 均值 μ 决定分布中心 | 标准差 σ 决定离散程度
[speak] 也就是说，μ 决定中心位置，σ 决定胖瘦程度。
[table] 常见分布对比 | 分布,均值,方差 | 正态分布,μ,σ² | 均匀分布,(a+b)/2,(b-a)²/12
[speak] 对比一下就更清楚了，这张表里列了几种常见分布的均值和方差。
[speak] 以上就是本节的核心内容。

学生问题：{question}"""


def _new_session_id():
    return f"SES_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(3)}"


def _history_digest(user_id, teacher_id, max_msgs=12, max_chars=1500):
    """把该学生×该老师的近期对话（含文字 chat 和 demo 讲课摘要）压成
    可注入 prompt 的前情提要。失败返回空串（记忆是增强，不阻塞讲课）。"""
    try:
        from chat import get_history
        msgs = get_history(user_id, teacher_id, limit=max_msgs)
    except Exception as e:
        print(f"[demo] 读取对话历史失败(忽略): {e}")
        return ""
    lines = []
    for m in msgs:
        content = str(m.get("content", "")).strip().replace("\n", " ")
        if not content:
            continue
        if len(content) > 220:
            content = content[:220] + "…"
        role = "学生" if m.get("role") == "user" else "老师"
        lines.append(f"{role}：{content}")
    return "\n".join(lines)[-max_chars:]


def _append_demo_history(user_id, teacher_id, question, events, summary, session_id=""):
    """讲课结束后把（学生问题, 讲课摘要）写回对话历史。
    摘要 = 开场引入语 + 板书提纲（标题/小标题/小结），控制长度避免撑爆后续 context。
    session_id 一并落库，供前端「回看这节课板书」链接到 sessions/{sid}/events.json
    （renderOnly 静态回看）；chat.py 注入 LLM 前只取 role/content，附加字段不影响推理。"""
    outline_parts = []
    for e in events:
        if e.get("type") == "board" and e.get("action") in ("write_title", "write_subtitle", "write_summary"):
            c = e.get("content")
            outline_parts.append(" ".join(str(x) for x in c) if isinstance(c, list) else str(c))
    outline = "；".join(outline_parts)[:400]
    text = (summary or "").strip() or "（已在黑板为你讲解）"
    if outline:
        text += f"\n（本次讲课提纲：{outline}）"
    assistant_entry = {"role": "assistant", "content": text[:800], "kind": "demo"}
    if session_id:
        assistant_entry["session_id"] = session_id
    try:
        from chat import append_history
        append_history(user_id, teacher_id, [
            {"role": "user", "content": question},
            assistant_entry,
        ])
    except Exception as e:
        print(f"[demo] 写入对话历史失败(忽略): {e}")


def _persist_demo_events(session_id, teacher_id, voice_id, events, partial=False):
    """落盘 events.json（回放/调试用）。partial=True 表示流被中断、事件不完整。"""
    session_dir = get_session_dir(session_id)
    os.makedirs(session_dir, exist_ok=True)
    payload = {
        "session_id": session_id,
        "teacher_id": teacher_id,
        "voice_id": voice_id,
        "events": events,
    }
    if partial:
        payload["partial"] = True
    with open(os.path.join(session_dir, "events.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _start_voice_warmup(teacher_id, tag="demo"):
    """后台线程预热该老师音色（加载 GPT 权重数秒，提前到 LLM 生成期间做）。"""
    try:
        import threading as _threading
        import sys as _sys
        _backend_dir = os.path.dirname(os.path.abspath(__file__))
        if _backend_dir not in _sys.path:
            _sys.path.insert(0, _backend_dir)
        import voice_service as _vs
        _threading.Thread(target=lambda: _vs.warmup(teacher_id), daemon=True).start()
    except Exception as _warm_e:
        print(f"[{tag}] 音色预热失败(忽略): {_warm_e}")


def _avatar_urls(teacher_id, card):
    """教师头像 URL（两张图用于口型同步切换），返回 (avatar_url, avatar_url_alt)。"""
    avatar_url = None
    avatar_url_alt = None
    avatar_data = card.get("avatar", {})
    if avatar_data:
        images = avatar_data.get("images", [])
        if len(images) >= 2:
            avatar_url = f"/api/v1/avatar/{teacher_id}/{images[0]}"
            avatar_url_alt = f"/api/v1/avatar/{teacher_id}/{images[1]}"
        elif images:
            avatar_url = f"/api/v1/avatar/{teacher_id}/{images[0]}"
        elif avatar_data.get("pixel_url"):
            avatar_url = avatar_data["pixel_url"]
    return avatar_url, avatar_url_alt


def _generate_intro(client, question, events, card, history_digest=""):
    """把教学大纲喂给 LLM，生成一段【开场引入语】作为右侧文字回答——
    课前预告这节课要讲什么、为什么值得学，并引导学生转向左侧黑板听讲（不是课后总结）。"""
    parts = []
    for e in events:
        if e.get("type") == "speak" and e.get("text"):
            parts.append(e["text"])
        elif e.get("type") == "board" and e.get("content"):
            c = e["content"]
            parts.append(" ".join(str(x) for x in c) if isinstance(c, list) else str(c))
    content = "\n".join(parts)[:3000]
    if not content.strip():
        return ""
    name = card.get("display_name", "老师")
    history_part = (
        f"你和这名学生此前的对话摘要如下，开场可以自然衔接其中确实出现过的内容，"
        f"但摘要里没有的内容绝对不要编造（不要凭空说“刚才我们讲了某某”）：\n{history_digest}\n\n"
        if history_digest.strip() else
        "这是你和这名学生的第一次对话，开场不要假装有过先前的交流。\n\n"
    )
    prompt = (
        f"下面是{name}即将在黑板上为学生讲解“{question}”的内容大纲。\n"
        f"{history_part}"
        f"请以{name}的口吻，用 2-3 句话写一段【课堂开场引入语】：自然地告诉学生这节课"
        f"将要学习什么、为什么有意思或重要，营造一点期待感，最后用一句话引导学生看左侧黑板听讲。\n"
        f"注意：这是上课前的引入开场白，不是课后总结——不要把结论和要点都讲完，"
        f"不要罗列板书格式，也不要出现 LaTeX 或公式符号。\n\n"
        f"讲解大纲：\n{content}"
    )
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6, max_tokens=300,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[teaching_demo] 引入语生成失败(忽略): {e}")
        return ""


def _parse_demo_response(text, image_catalog=None):
    """解析 AI 的教学演示响应为 events 列表。
    实现已移至 event_stream.DemoEventParser（支持流式增量解析），
    此处保留原签名供 course.py 等离线调用方使用，行为逐事件等价
    （等价性由 test_event_stream.py 保证）。
    image_catalog: 本次注入 prompt 的候选插图（media_library.build_catalog），
    [image] 行只有命中其中的 ID 才产出事件。"""
    from event_stream import parse_demo_text_merged
    return parse_demo_text_merged(text, image_catalog=image_catalog)


def _generate_tts_for_events(events, output_dir, teacher_id=None):
    """为所有 speak 事件批量生成 TTS。
    优先用该老师专属音色（GPT-SoVITS），不可用/失败则降级 edge-tts。"""
    import asyncio
    manifest = []
    for evt in events:
        if evt["type"] != "speak":
            continue
        text = evt.get("text", "")
        if not text:
            continue

        # 限制单段长度
        chunks = _chunk_text(text, 400)
        for ci, chunk in enumerate(chunks):
            evt_id = f"evt_{evt['seq']:04d}"
            if ci > 0:
                evt_id += f"_p{ci}"

            # 优先用该老师专属音色（GPT-SoVITS）；不可用/失败则降级 edge-tts
            if teacher_id:
                try:
                    import voice_service
                    import soundfile as _sf
                    va = voice_service.synthesize(teacher_id, chunk)
                    if va:
                        _sr, _audio = va
                        wav_path = os.path.join(output_dir, f"{evt_id}.wav")
                        _sf.write(wav_path, _audio, _sr)
                        manifest.append({
                            "event_id": evt_id,
                            "file": f"{evt_id}.wav",
                            "duration_sec": round(len(_audio) / _sr, 1),
                            "text_preview": chunk[:30],
                        })
                        continue
                except Exception as _e:
                    print(f"[voice] {evt_id} 老师音色失败，降级 edge-tts: {_e}")

            out_path = os.path.join(output_dir, f"{evt_id}.mp3")

            try:
                async def _run():
                    import edge_tts, os as _os
                    proxy = _os.environ.get("EDGE_TTS_PROXY") or None
                    communicate = edge_tts.Communicate(chunk, _get_edge_voice(teacher_id), proxy=proxy)
                    mp3_data = b""
                    async for ch in communicate.stream():
                        if ch["type"] == "audio":
                            mp3_data += ch["data"]
                    return mp3_data
                # edge-tts 在线服务偶发 NoAudioReceived，重试至多 3 次
                mp3_bytes = b""
                for _attempt in range(3):
                    try:
                        mp3_bytes = asyncio.run(_run())
                        if mp3_bytes:
                            break
                    except Exception as _re:
                        print(f"TTS retry {_attempt+1}/3 for {evt_id}: {_re}")
                if not mp3_bytes:
                    raise RuntimeError("edge-tts 未返回音频（NoAudioReceived）")
                with open(out_path, "wb") as f:
                    f.write(mp3_bytes)

                # 估算时长（中文约 4 字/秒）
                duration = max(len(chunk) / 4.0, 1.5)
                manifest.append({
                    "event_id": evt_id,
                    "file": f"{evt_id}.mp3",
                    "duration_sec": round(duration, 1),
                    "text_preview": chunk[:30],
                })
            except Exception as e:
                print(f"TTS failed for {evt_id}: {e}")

    return manifest


def _chunk_text(text, max_len):
    """将长文本按句子分块"""
    import re
    if len(text) <= max_len:
        return [text]
    chunks = []
    current = ""
    for sent in re.split(r'(?<=[。！？；\n])', text):
        if len(current) + len(sent) <= max_len:
            current += sent
        else:
            if current:
                chunks.append(current)
            current = sent
    if current:
        chunks.append(current)
    return chunks or [text]


def _simple_playback(events, audio_manifest, session_id="", teacher_name=""):
    """播放数据构建 — 字段名严格对齐 M5 PlayerRuntime types.ts"""
    timeline = []
    audio_map = {a["event_id"]: a for a in audio_manifest}
    time_offset = 0
    for evt in events:
        seq = evt["seq"]
        evt_id = f"evt_{seq:04d}"
        etype = evt["type"]

        if etype == "speak":
            audio = audio_map.get(evt_id, {})
            dur = audio.get("duration_sec", max(len(evt.get("text", "")) / 4.0, 1.5))
            audio_file = audio.get("file", "")
            timeline.append({
                "seq": seq, "event_id": evt_id, "type": "speak",
                "text": evt.get("text", ""),
                "audio_path": f"/api/v1/audio/{session_id}/audio/turn_1/{audio_file}" if audio_file else "",
                "duration_sec": round(dur, 1),
                "start_offset_sec": round(time_offset, 1),
            })
            time_offset += dur + 0.3

        elif etype == "board":
            timeline.append({
                "seq": seq, "event_id": evt_id, "type": "board",
                "action": evt.get("action", "write_bullets"),
                "content": evt.get("content", ""),
                "dwell_sec": 2.0,
                "start_offset_sec": round(time_offset, 1),
            })
            time_offset += 2.0

        elif etype == "formula":
            timeline.append({
                "seq": seq, "event_id": evt_id, "type": "formula",
                "latex": evt.get("latex", ""),
                "display_mode": "block" if evt.get("display_mode") else "inline",
                "start_offset_sec": round(time_offset, 1),
            })
            time_offset += 3.0

        elif etype == "image":
            timeline.append({
                "seq": seq, "event_id": evt_id, "type": "image",
                "src": evt.get("src", ""),
                "caption": evt.get("caption", ""),
                "media_type": evt.get("media_type", "static"),
                "dwell_sec": 3.0,
                "start_offset_sec": round(time_offset, 1),
            })
            time_offset += 3.0

        elif etype == "pause":
            dur = evt.get("duration_sec", 1.5)
            timeline.append({
                "seq": seq, "event_id": evt_id, "type": "pause",
                "duration_sec": dur,
                "start_offset_sec": round(time_offset, 1),
            })
            time_offset += dur

    return {
        "session_id": session_id,
        "turn": 1,
        "teacher_id": session_id,
        "voice_id": "edge-tts",
        "timeline": timeline,
        "total_duration_sec": round(time_offset, 1),
    }
    @require_auth
    def list_sessions():
        if not os.path.exists(SESSIONS_ROOT):
            return ok([])
        sessions = []
        for sid in os.listdir(SESSIONS_ROOT):
            state = load_session_state(sid)
            if state and state.get("student_id") == request.user_id:
                sessions.append({
                    "session_id": state["session_id"],
                    "teacher_id": state.get("teacher_id"),
                    "teacher_name": state.get("teacher_name"),
                    "mode": state.get("mode"),
                    "started_at": state.get("started_at"),
                    "qa_count": len(state.get("qa_history", [])),
                })
        sessions.sort(key=lambda s: s.get("started_at", ""), reverse=True)
        return ok(sessions)
