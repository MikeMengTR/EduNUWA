"""
M1 ASR Pipeline 共享配置：所有 ASR 引擎的默认参数集中管理。

使用方式：
    from .config import get_engine_config
    cfg = get_engine_config("whisper", user_config)  # 合并基座 + 引擎默认 + 用户覆盖
"""

# ============================================================
# 基座配置：所有引擎共享的参数
# ============================================================
BASE_CONFIG = {
    "language": "zh",
    "device": "cuda",
    "cache_dir": None,       # 模型存储目录，None=使用各引擎默认位置
}

# ============================================================
# 数学课程领域术语（Whisper initial_prompt / FunASR hotwords 共用）
# ============================================================
MATH_DOMAIN_TERMS = (
    "这是大学高等数学与线性代数 MOOC 课程。学术术语包括：微积分、"
    "拉格朗日中值定理、泰勒展开式、麦克劳林级数、空间解析几何、"
    "多元函数微分、重积分、曲率、收敛、保号性、导数、不定积分等。"
)

# 简化版：仅关键词，供 hotwords 引擎使用
MATH_HOTWORDS = (
    "微积分,拉格朗日中值定理,泰勒展开式,麦克劳林级数,空间解析几何,"
    "多元函数微分,重积分,曲率,收敛,保号性,导数,不定积分,线性代数,"
    "概率论,数理统计,特征值,特征向量,极限,洛必达,偏导数"
)

# ============================================================
# Whisper 引擎专属默认值
# ============================================================
WHISPER_DEFAULTS = {
    "model_size": "large-v3",
    "compute_type": "float16",
    "cpu_threads": 16,
    "beam_size": 5,
    "initial_prompt": MATH_DOMAIN_TERMS,
    "vad_filter": True,
    "compression_ratio_threshold": 2.4,
    "no_speech_threshold": 0.6,
}

# ============================================================
# FunASR 引擎专属默认值
# ============================================================
FUNASR_DEFAULTS = {
    "model": "paraformer-zh",
    "vad_model": "fsmn-vad",
    "punc_model": "ct-punc",
    "ncpu": 16,
    "use_vad": True,
    "hotwords": MATH_HOTWORDS,
}

# ============================================================
# Cloud ASR 引擎专属默认值
# ============================================================
CLOUD_DEFAULTS = {
    "provider": "aliyun",           # aliyun / tencent / azure
    "model": "fun-asr",             # fun-asr(旗舰,推荐) / paraformer-v2(免费) / gummy-realtime-v1(多语种)
    "api_key": "",                  # 百炼 API Key（默认读 DASHSCOPE_API_KEY 环境变量）
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
}

# ============================================================
# 配置合并：基座 < 引擎默认 < 用户覆盖
# ============================================================
ENGINE_DEFAULTS = {
    "whisper": WHISPER_DEFAULTS,
    "funasr": FUNASR_DEFAULTS,
    "cloud": CLOUD_DEFAULTS,
}


def get_engine_config(engine: str, user_config: dict | None = None) -> dict:
    """获取合并后的引擎配置。

    优先级：用户配置 > 引擎默认 > 基座配置
    用户 config 中未被引擎识别的键会被静默保留（各引擎自行忽略）。

    Args:
        engine: "whisper" | "funasr" | "cloud"
        user_config: 用户传入的可选覆盖配置

    Returns:
        合并后的完整配置 dict
    """
    engine_key = engine.lower()
    if engine_key not in ENGINE_DEFAULTS:
        raise ValueError(f"未知引擎: {engine}，可选: {list(ENGINE_DEFAULTS)}")

    merged = {}
    merged.update(BASE_CONFIG)
    merged.update(ENGINE_DEFAULTS[engine_key])
    if user_config:
        merged.update(user_config)
    return merged
