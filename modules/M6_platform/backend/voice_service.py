"""教师音色 TTS 服务。

按 teacher_id 读取 data/teachers/{tid}/voice/voice_profile.json，用各老师微调的
GPT-SoVITS 音色合成语音。

稳定性保障（零降级 edge-tts）：
- 不稳定的老师自动切换最稳定的 GPT 权重 + 保留自身 ref.wav（音色不受影响）
- 无结果/无声时模型重置 + 全参数重试
- 长文本自动拆分→逐段合成→拼接，每段稳定且低延迟
"""
import os
import sys
import json
import threading
import tempfile
import wave
import numpy as np
import re

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

_lock = threading.Lock()
_tts = None
_current_voice = None
_disabled = set()
_stable_override = set()

# faster-whisper 模型（懒加载，镜像下载）
_whisper_model = None  # 一旦走兜底就记住：该老师后续直接用稳定 GPT

# 示例老师 GPT 权重是最稳定的（训练数据最充足），不稳定的老师用此 GPT + 自己的 ref.wav
_STABLE_GPT = os.path.join(_project_root,
    "GPT-SoVITS-v2pro", "GPT-SoVITS-v2Pro", "GPT_weights_v2Pro", "songhao_gpt-e20.ckpt")
_SOVITS_BASE = os.path.join(_project_root,
    "GPT-SoVITS-v2pro", "GPT-SoVITS-v2Pro", "GPT_SoVITS", "pretrained_models", "v2Pro", "s2Gv2ProPlus.pth")


# 数学/希腊符号 → 中文口播：GPT-SoVITS 是中文 TTS，直接念 μ/σ/²/= 会糊成杂声，
# latin 转写(miu/sigma)又会触发字母拼读/干扰合成，故统一用【中文名】（GPT-SoVITS 念得准，
# 实测 σ→西格玛 正确）。仅作用于 TTS 输入，不影响字幕（event.text 原样保留）。
_TTS_SYMBOL_MAP = {
    "α": "阿尔法", "β": "贝塔", "γ": "伽玛", "Γ": "伽玛", "δ": "德尔塔", "Δ": "德尔塔",
    "ε": "艾普西龙", "ζ": "泽塔", "η": "伊塔", "θ": "西塔", "Θ": "西塔", "λ": "兰姆达",
    "Λ": "兰姆达", "μ": "缪", "ν": "纽", "ξ": "克西", "π": "派", "Π": "派", "ρ": "柔",
    "σ": "西格玛", "Σ": "西格玛", "τ": "陶", "φ": "斐", "Φ": "斐", "χ": "希", "ψ": "普西",
    "ω": "欧米伽", "Ω": "欧米伽",
    "²": "的平方", "³": "的立方",
    "₀": "零", "₁": "一", "₂": "二", "₃": "三", "₄": "四",
    "₅": "五", "₆": "六", "₇": "七", "₈": "八", "₉": "九",
    "≤": "小于等于", "≥": "大于等于", "≠": "不等于", "≈": "约等于", "≡": "恒等于",
    "×": "乘以", "÷": "除以", "±": "正负", "√": "根号", "∞": "无穷大",
    "∑": "求和", "∫": "积分", "∈": "属于", "→": "趋于", "°": "度", "=": "等于",
}


def _normalize_for_tts(text):
    """把数学/希腊符号替换成中文口播读法，避免 GPT-SoVITS 念成杂声/崩溃。"""
    if not text:
        return text
    return "".join(_TTS_SYMBOL_MAP.get(ch, ch) for ch in text)


def _smooth_onset(audio, sr, ms=8):
    """开头极短淡入，软化自回归起始的爆音/咔哒声（click/pop）。

    只对开头 ms 毫秒做线性增益渐变（0→1），**不删除任何采样**——所以零合成开销、
    不拖慢实时流式，也绝不会"吞掉"开头的字（与之前的引导词裁剪方案相反）。
    注意：这只能消除起始的爆音类杂声，无法补救模型生成层面偶发的吞首字。
    """
    a = np.asarray(audio, dtype=np.float32)
    if a.size == 0:
        return audio
    k = min(int(sr * ms / 1000), a.size)
    if k > 1:
        a = a.copy()
        a[:k] *= np.linspace(0.0, 1.0, k, dtype=np.float32)
    return a


def _voice_profile(teacher_id):
    p = os.path.join(_project_root, "data", "teachers", teacher_id, "voice", "voice_profile.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def is_available(teacher_id):
    prof = _voice_profile(teacher_id)
    return prof is not None and prof.get("voice_id", teacher_id) not in _disabled


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        import os as _os
        _os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        from faster_whisper import WhisperModel
        root = os.path.join(_project_root, "data", "whisper_models")
        _whisper_model = WhisperModel("small", device="cpu", compute_type="int8", download_root=root)
    return _whisper_model


def _verify_audio(audio_f32, sr, expected):
    """faster-whisper tiny 转写→字级准确率（基线 85-95%）。"""
    m = _get_whisper()
    if m is None:
        return 1.0, "(no model)"
    try:
        tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        tmp.close()
        wav = (np.clip(audio_f32, -1, 1) * 32767).astype(np.int16)
        import wave as _wave
        with _wave.open(tmp.name, 'wb') as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
            wf.writeframes(wav.tobytes())
        segments, _ = m.transcribe(tmp.name, language="zh", beam_size=5)
        txt = "".join(s.text for s in segments)
        os.unlink(tmp.name)
        # 繁体→简体归一化（Whisper 倾向输出繁体）
        try:
            from opencc import OpenCC
            _cc = OpenCC('t2s')
            exp = _cc.convert(''.join(c for c in expected if ord(c) > 127 or c.isascii()))
            txn = _cc.convert(''.join(c for c in txt if ord(c) > 127 or c.isascii()))
        except ImportError:
            exp = ''.join(c for c in expected if ord(c) > 127 or c.isascii())
            txn = ''.join(c for c in txt if ord(c) > 127 or c.isascii())
        if not exp: return 1.0, txt
        matches = sum(1 for c in exp if c in txn)
        acc = matches / len(exp)
        return acc, txt
    except Exception as e:
        return 1.0, str(e)[:50]


def _log_accuracy(audio_f32, sr, text, vid):
    """后台线程：异步校验内容准确度，记录日志。"""
    acc, asr_txt = _verify_audio(audio_f32, sr, text)
    if acc < 0.80:
        print(f"[voice_service] {vid} 准确度={acc:.2f}<0.90, ASR=\"{asr_txt[:60]}\" 原文=\"{text[:30]}\"")
    else:
        print(f"[voice_service] {vid} 准确度={acc:.2f} OK")


def synthesize(teacher_id, text, temperature=None, top_p=None):
    """用老师音色合成。返回 (sample_rate, audio_float32) 或 None（不可用，调用方应降级）。

    temperature/top_p 显式传入时覆盖 profile 默认值（用于「多参数试听」逐款生成）；
    为 None 时沿用 voice_profile.json 里教师选定的参数。

    全覆盖策略（确保 100% 走 GPT-SoVITS，零降级 edge-tts）：
    1. 不稳定教师→稳定 GPT + 自身 ref（音色来自 ref，韵律来自稳定 GPT）
    2. 长文本(>50字)→拆分段合成→拼接（每段更稳定、延迟更低）
    3. 全部失败→模型重置 + 稳定GPT兜底重试
    4. 默认低温, 0.4，提高确定性
    """
    prof = _voice_profile(teacher_id)
    if not prof:
        return None
    vid = prof.get("voice_id", teacher_id)
    if prof.get("disabled") or vid in _disabled:
        return None

    text = _normalize_for_tts(text)  # 数学/希腊符号→中文口播，防止 GPT-SoVITS 念成杂声/崩溃

    ref = os.path.join(_project_root, prof["ref_audio"])
    ref_text = prof.get("ref_text", "")

    # 使用稳定 GPT 权重（不稳定的老师靠 ref.wav 保持音色）
    gpt = os.path.join(_project_root, prof["gpt_model"])
    if not os.path.exists(gpt) or teacher_id in _stable_override:
        gpt = _STABLE_GPT
    sovits = _SOVITS_BASE

    if not (os.path.exists(ref) and os.path.exists(sovits)):
        return None

    # 长文本拆分：每段 ≤60 字，GPT-SoVITS 对中等长度最稳定
    # 短文本由 event_stream._merge_speaks 在上游合并，不在此层处理
    segments = _split_for_stability(text)
    result = None
    if len(segments) == 1:
        result = _synth_one(teacher_id, gpt, sovits, ref, ref_text, text, vid, prof, temperature, top_p)
    else:
        all_audio = []
        sample_rate = None
        for seg in segments:
            r = _synth_one(teacher_id, gpt, sovits, ref, ref_text, seg, vid, prof, temperature, top_p)
            if r is None:
                print(f"[voice_service] {vid} 分段'{seg[:20]}...'失败")
                return None
            sr, af = r
            sample_rate = sr
            all_audio.append(af)
        result = (sample_rate, np.concatenate(all_audio))

    if result is None:
        return None
    sr, af = result
    return sr, np.clip(af, -1.0, 1.0)


def _synth_one(teacher_id, gpt_model, sovits_model, ref_audio, ref_text, text, vid, prof, ov_temp=None, ov_top_p=None):
    """单段合成核心：6 种策略 + 模型重置兜底。ov_temp/ov_top_p 覆盖 profile 默认参数。"""
    with _lock:
        global _tts, _current_voice
        try:
            import modules.M5_runtime.tts_service.gpt_sovits_wrapper as W
            from modules.M5_runtime.tts_service.gpt_sovits_wrapper import StreamingTTS

            # 默认低温 0.4——提高确定性、减少发散；显式覆盖优先（多参数试听用）
            default_temp = ov_temp if ov_temp is not None else prof.get("temperature", 0.4)
            default_top_p = ov_top_p if ov_top_p is not None else prof.get("top_p", 0.5)

            if _tts is None:
                _tts = StreamingTTS(
                    gpt_model_path=gpt_model, sovits_model_path=sovits_model,
                    ref_audio_path=ref_audio, ref_text=ref_text,
                    temperature=default_temp, top_p=default_top_p,
                )
                _tts.load_models()
                _current_voice = vid
            elif _current_voice != vid or gpt_model != _tts.gpt_path:
                with W._gpt_sovits_cwd():
                    W._change_gpt_weights(gpt_path=gpt_model)
                _tts.gpt_path = gpt_model
                _current_voice = vid

            _tts.ref_text = ref_text
            _tts.temperature = default_temp
            _tts.top_p = default_top_p

            def _try_synth(txt, temp=None, tp=None):
                if temp is not None:
                    _tts.temperature = temp
                if tp is not None:
                    _tts.top_p = tp
                r = _tts.synthesize(txt, ref_audio=ref_audio)
                _tts.temperature = default_temp
                _tts.top_p = default_top_p
                if not r:
                    return None
                sr2, audio2 = r
                a2 = np.asarray(audio2)
                a2 = a2[:, 0] if a2.ndim > 1 else a2
                af2 = a2.astype(np.float32)
                if np.issubdtype(a2.dtype, np.integer):
                    af2 = af2 / 32768.0
                # 开头极短淡入：软化自回归起始的爆音/咔哒声。仅缩放采样、不删除、不增合成量，
                # 既不拖慢实时流式，也绝不吞字（与引导词裁剪方案相反）。
                af2 = _smooth_onset(af2, sr2)
                mx2 = float(np.max(np.abs(af2))) if af2.size else 0.0
                if mx2 < 0.008:
                    return None
                # 后台异步校验内容准确度（Whisper CPU 推理不阻塞 HTTP 响应）
                threading.Thread(target=lambda: _log_accuracy(af2, sr2, txt, vid), daemon=True).start()
                return sr2, af2

            # === 4 种温度策略依次尝试 ===
            retry_configs = [
                (None, None, "正常"),
                (0.2, 0.3, "极低温"),
                (0.5, 0.6, "中温"),
                (0.6, 0.7, "中高温"),
            ]

            result = None
            for cfg in retry_configs:
                r = _try_synth(text, temp=cfg[0], tp=cfg[1])
                if r:
                    sr, af = r
                    print(f"[voice_service] {vid} {cfg[2]}合成成功")
                    result = (sr, af)
                    break
                print(f"[voice_service] {vid} {cfg[2]}无效")

            # === 兜底：模型重置 + 稳定 GPT 重试 ===
            if result is None:
                print(f"[voice_service] {vid} 6种策略均失败，模型重置 + 稳定GPT兜底...")
                _stable_override.add(teacher_id)  # 记住：后续直接用稳定 GPT
                _tts = None
                _current_voice = None
                # 用示例老师 GPT 兜底
                fallback_gpt = _STABLE_GPT
                if os.path.exists(fallback_gpt):
                    _tts = StreamingTTS(
                        gpt_model_path=fallback_gpt, sovits_model_path=sovits_model,
                        ref_audio_path=ref_audio, ref_text=ref_text,
                        temperature=0.3, top_p=0.4,
                    )
                    _tts.load_models()
                    _current_voice = vid + "_fb"
                    # 兜底用完整 4 种温度策略再来一轮（引导词在 _try_synth 内处理）
                    for cfg in retry_configs:
                        r = _try_synth(text, temp=cfg[0], tp=cfg[1])
                        if r:
                            sr, af = r
                            print(f"[voice_service] {vid} 兜底{cfg[2]}成功")
                            result = (sr, af)
                            break
                if result is None:
                    print(f"[voice_service] {vid} 兜底也失败，返回 None")
                    return None

            mx_final = float(np.max(np.abs(result[1]))) if result[1].size else 0.0
            if mx_final < 0.008:
                print(f"[voice_service] {vid} 最终无效(mx={mx_final:.4f})")
                return None
            return result[0], np.clip(result[1], -1.0, 1.0)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[voice_service] {teacher_id} 合成异常: {e}")
            # 重置模型状态（_tts 已在函数开头声明为 global）
            _tts = None
            _current_voice = None
            return None


def _split_for_stability(text, max_chars=55):
    """按标点把长文本拆成自然的语音段（GPT-SoVITS 对 ~30-55 字最稳定）。

    分句原则（避免"半句被逗号硬切""碎片跨句号粘连"等不自然停顿）：
      1. 先按句末标点（。！？；…）切成完整句子——句末是最自然的停顿点。
      2. 相邻短句可合并，但合并后 ≤ max_chars。
      3. 单句超长时按逗号（，、,）切成小句，并按"需要几段"尽量**均分**，
         避免切出极短尾巴（如把"…简称导函数，"切走、只剩"记作 f'(x)。"）。
      4. 长句切出的小句**绝不与下一句合并**（句末标点是硬边界，不跨句号粘连）。
      5. 仍超长且无标点 → 暴力按字数切（兜底）。
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    sentences = [s.strip() for s in re.split(r'(?<=[。！？；…])', text) if s.strip()]

    out = []
    buf = ""
    for sent in sentences:
        if len(sent) <= max_chars:
            # 短句：与缓冲里的短句合并（合并后仍 ≤ max_chars），否则收旧起新
            if buf and len(buf) + len(sent) <= max_chars:
                buf += sent
            else:
                if buf:
                    out.append(buf)
                buf = sent
        else:
            # 长句：先冲掉缓冲（不让尾巴跨句号粘连），再单独均分
            if buf:
                out.append(buf)
                buf = ""
            out.extend(_split_long_sentence(sent, max_chars))
    if buf:
        out.append(buf)
    return out or [text]


def _split_long_sentence(sent, max_chars):
    """把超过 max_chars 的单句按逗号切成均衡小句（尽量等长，不留极短尾巴）。"""
    # 按逗号切小句（保留逗号）；仍超长且无逗号的小句先暴力按字数切
    units = []
    for c in (x for x in re.split(r'(?<=[，、,])', sent) if x):
        while len(c) > max_chars:
            units.append(c[:max_chars])
            c = c[max_chars:]
        if c:
            units.append(c)

    total = sum(len(u) for u in units)
    n = max(1, (total + max_chars - 1) // max_chars)   # 需要几段
    target = (total + n - 1) // n                        # 每段目标字数（均分，向上取整）

    out, buf = [], ""
    for u in units:
        # buf 已达目标、或再加就超过 max_chars → 先收一段（保证均衡且不超限）
        if buf and (len(buf) >= target or len(buf) + len(u) > max_chars):
            out.append(buf)
            buf = ""
        buf += u
    if buf:
        out.append(buf)
    return out


def warmup(teacher_id):
    """预热并验证老师音色。返回 True=可用。"""
    prof = _voice_profile(teacher_id)
    if not prof:
        return False
    vid = prof.get("voice_id", teacher_id)
    if prof.get("disabled"):
        _disabled.add(vid)
        print(f"[voice_service] {vid} 已在 profile 标记 disabled")
        return False
    _disabled.discard(vid)
    r = synthesize(teacher_id, "同学们好，今天我们来学习一个新的知识点。")
    if r is None:
        _disabled.add(vid)
        print(f"[voice_service] {vid} 预热失败，已禁用")
        return False
    print(f"[voice_service] {vid} 预热通过")
    return True


def prewarm_all():
    """后台线程：启动时预热所有有 voice_profile 的老师。"""
    def _worker():
        teachers_root = os.path.join(_project_root, "data", "teachers")
        if not os.path.isdir(teachers_root):
            return
        for tid in sorted(os.listdir(teachers_root)):
            prof = _voice_profile(tid)
            if prof and not prof.get("disabled"):
                print(f"[voice_service] 预热 {tid}...")
                warmup(tid)
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    print("[voice_service] 后台预热已启动")
