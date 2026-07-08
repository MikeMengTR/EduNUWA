# GPT-SoVITS-v2Pro TTS 推理服务

示例老师语音的实时文本转语音（TTS），基于 GPT-SoVITS v2Pro。

---

## 模型文件清单

全部使用 **Git LFS** 管理（`.ckpt` / `.pth` / `.onnx` / `.bin` / `.pickle`）。

### 核心模型

| 文件 | 大小 | 说明 |
|------|------|------|
| `GPT-SoVITS-v2pro/GPT_weights_v2Pro/songhao_gpt-e20.ckpt` | 148 MB | 微调 GPT（20 epoch），示例老师语言风格 |
| `GPT-SoVITS-v2pro/GPT_SoVITS/pretrained_models/v2Pro/s2Gv2ProPlus.pth` | 191 MB | SoVITS 生成器（v2ProPlus），将语义特征转为 mel 频谱 |
| `GPT-SoVITS-v2pro/GPT_SoVITS/pretrained_models/v2Pro/s2Dv2ProPlus.pth` | 121 MB | SoVITS 判别器（训练时用，推理可能不需要） |

### 通用预训练模型（中文语音必需）

| 文件 | 大小 | 说明 |
|------|------|------|
| `GPT-SoVITS-v2pro/GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large/pytorch_model.bin` | 621 MB | BERT 中文文本编码，将文本转为语义向量 |
| `GPT-SoVITS-v2pro/GPT_SoVITS/pretrained_models/chinese-hubert-base/pytorch_model.bin` | 180 MB | HuBERT 中文语音特征提取 |
| `GPT-SoVITS-v2pro/GPT_SoVITS/pretrained_models/fast_langdetect/lid.176.bin` | 125 MB | 语言检测（fastText） |
| `GPT-SoVITS-v2pro/GPT_SoVITS/pretrained_models/sv/pretrained_eres2netv2w24s4ep4.ckpt` | 103 MB | 说话人验证模型，提取音色嵌入 |
| `GPT-SoVITS-v2pro/GPT_SoVITS/text/G2PWModel/g2pW.onnx` | 606 MB | 中文多音字消歧（G2PW），判断"函数 shù" vs "数 shǔ 一数" |

### 参考音频

| 目录 | 说明 |
|------|------|
| `GPT-SoVITS-v2pro/data/sliced_audio/` | 示例老师原始语音片段（~5s），作为音色参考 |

### 环境依赖

```bash
pip install -r GPT-SoVITS-v2pro/requirements.txt
pip install -r GPT-SoVITS-v2pro/extra-req.txt
pip install soundfile librosa numpy torch
```

---

## 模型下载方式

### 方式一：Git LFS（推荐，如果仓库已配置）

```bash
# 1. 安装 Git LFS
#    Windows: 下载 https://git-lfs.com/
#    Mac:     brew install git-lfs
#    Linux:   apt install git-lfs 或 yum install git-lfs

# 2. 初始化
git lfs install

# 3. 克隆仓库（自动拉取 LFS 文件）
git clone <你的仓库地址>
cd tts_package
git lfs pull
```

### 方式二：手动下载（如果 LFS 拉取失败）

如果 `git lfs pull` 失败或没装 LFS，LFS 指针文件只有几百字节，需要手动下载真实模型。

1. **从原始 GPT-SoVITS 项目下载通用模型：**

   | 模型 | 下载地址 |
   |------|---------|
   | chinese-roberta-wwm-ext-large | https://huggingface.co/hfl/chinese-roberta-wwm-ext-large |
   | chinese-hubert-base | https://huggingface.co/TencentGameMate/chinese-hubert-base |
   | s2Gv2ProPlus + s2Dv2ProPlus | GPT-SoVITS 官方发布页 |
   | G2PW (g2pW.onnx) | GPT-SoVITS 官方发布页 |
   | fast-langdetect (lid.176.bin) | https://fasttext.cc/docs/en/language-identification.html |
   | eres2net (speaker verification) | 3D-Speaker 官方仓库 |

2. **微调模型（songhao_gpt-e20.ckpt）和参考音频：** 需从团队内部获取（自己训练的）。

3. 下载后按上方的"模型文件清单"路径放置。

### 方式三：从原项目复制

如果你本地有完整的训练项目：

```bash
# 假设原项目在 ~/GPT-SoVITS-v2pro/
ORIGINAL=~/GPT-SoVITS-v2pro/GPT-SoVITS-v2pro
PACKAGE=./GPT-SoVITS-v2pro

# 复制 GPT 权重
cp $ORIGINAL/GPT_weights_v2Pro/songhao_gpt-e20.ckpt $PACKAGE/GPT_weights_v2Pro/

# 复制 SoVITS 权重
cp $ORIGINAL/GPT_SoVITS/pretrained_models/v2Pro/s2Gv2ProPlus.pth $PACKAGE/GPT_SoVITS/pretrained_models/v2Pro/
cp $ORIGINAL/GPT_SoVITS/pretrained_models/v2Pro/s2Dv2ProPlus.pth $PACKAGE/GPT_SoVITS/pretrained_models/v2Pro/

# 复制通用预训练模型
cp -r $ORIGINAL/GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large $PACKAGE/GPT_SoVITS/pretrained_models/
cp -r $ORIGINAL/GPT_SoVITS/pretrained_models/chinese-hubert-base $PACKAGE/GPT_SoVITS/pretrained_models/
cp -r $ORIGINAL/GPT_SoVITS/pretrained_models/fast_langdetect $PACKAGE/GPT_SoVITS/pretrained_models/
cp -r $ORIGINAL/GPT_SoVITS/pretrained_models/sv $PACKAGE/GPT_SoVITS/pretrained_models/

# 复制 G2PW
cp $ORIGINAL/GPT_SoVITS/text/G2PWModel/g2pW.onnx $PACKAGE/GPT_SoVITS/text/G2PWModel/

# 复制参考音频
cp -r $ORIGINAL/../data/sliced_audio/* $PACKAGE/data/sliced_audio/
```

---

## 验证安装

```bash
cd tts_package
python test_package.py
```

全部显示 `[OK]` 即安装成功。

## 快速开始

### 1. 流式 LLM + TTS Demo

```bash
python llm_tts_streaming_demo.py
```

### 2. 批量合成

```python
from modules.tts_service.tts_inference import generate_tts_batch

result = generate_tts_batch("teaching_events.json", "output/")
# 会在 output/ 下生成 .wav 和 audio_manifest.json
```

### 3. 单句合成

```python
import sys, os
sys.path.insert(0, "GPT-SoVITS-v2pro")
sys.path.insert(0, "GPT-SoVITS-v2pro/GPT_SoVITS")
os.chdir("GPT-SoVITS-v2pro")

from GPT_SoVITS.inference_webui import change_gpt_weights, change_sovits_weights, get_tts_wav

change_gpt_weights(gpt_path="GPT_weights_v2Pro/songhao_gpt-e20.ckpt")
gen = change_sovits_weights(
    sovits_path="GPT_SoVITS/pretrained_models/v2Pro/s2Gv2ProPlus.pth",
    prompt_language="中文", text_language="中文"
)
for _ in gen: pass

result = get_tts_wav(
    ref_wav_path="data/sliced_audio/xxx.wav",
    prompt_text="参考音频对应的文本",
    prompt_language="中文",
    text="你好，欢迎来到高等数学课堂。",
    text_language="中文",
)
sr, audio = list(result)[-1]
```

---

## 常见问题

**Q: 克隆后模型文件只有几百字节？**
没有拉取 LFS 文件，执行 `git lfs pull`。

**Q: `No module named 'xxx'`？**
检查是否遗漏了 `sys.path.insert(0, "GPT-SoVITS-v2pro/GPT_SoVITS")`，`text`/`AR`/`BigVGAN` 等模块都在 `GPT_SoVITS/` 子目录下。

**Q: 提示找不到参考音频？**
参考音频放在 `GPT-SoVITS-v2pro/data/sliced_audio/`，需手动创建并放入示例老师的语音片段。
