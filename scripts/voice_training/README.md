# 多老师语音模型训练（voice_training）

为 `data/teachers/` 下每位老师训练**独立的 GPT-SoVITS 音色模型**。
共享底模（SoVITS v2Pro + hubert/roberta/bert）只一份，每位老师只产出独有的
GPT 微调权重（~155MB）+ 参考音频，放进各自 `data/teachers/{tid}/voice/`。

只微调 GPT（决定语气节奏），SoVITS 用 v2Pro 共享底模 + 参考音频零样本克隆音色。

## 用法

```powershell
# 单个老师：ASR → 预处理+GPT微调 → 落地
& D:\anaconda3\envs\edu\python.exe scripts\voice_training\asr_to_list.py  T_20260604_001 --exp T001
& D:\anaconda3\envs\edu\python.exe scripts\voice_training\train_gpt.py    T001 --list data/teachers/T_20260604_001/voice/train/T001.list --wav-dir data/teachers/T_20260604_001/audio_samples --epochs 20
& D:\anaconda3\envs\edu\python.exe scripts\voice_training\finalize_voice.py T_20260604_001 --exp T001

# 批量（默认 002~006）
& D:\anaconda3\envs\edu\python.exe scripts\voice_training\train_all.py

# 合成验证
& D:\anaconda3\envs\edu\python.exe scripts\voice_training\synth_test.py T_20260604_001 "测试文本"
```

`train_gpt.py` 加 `--skip-preprocess` 可跳过已完成的预处理直接训练。

## 产物结构（每位老师独立部分）

```
data/teachers/{tid}/voice/
├── {exp}_gpt-e20.ckpt   该老师 GPT 微调权重（~155MB，独有）
├── ref.wav              参考音频（从切片选 SNR 最高 → 裁中段 8s）
├── voice_profile.json   voice_id + gpt_model + 共享sovits_model + ref_audio/ref_text
├── sample_test.wav      合成测试样本
└── train/{exp}.list     ASR 转写（wav|spk|ZH|text）
```

## 环境依赖

GPU torch（关键，CPU 版无法训练）：
```
pip install torch==2.11.0+cu128 torchaudio==2.11.0+cu128 --index-url https://download.pytorch.org/whl/cu128
```

训练 + 推理额外依赖（均已装入 edu 环境）：
```
faster-whisper funasr            # ASR（实际用 funasr 本地 paraformer）
jieba_fast opencc onnxruntime    # 中文文本前端（g2pw 多音字）
imageio-ffmpeg                   # 提供 ffmpeg.exe（预处理读音频）；复制到 envs/edu/Library/bin/ffmpeg.exe
fast_langdetect split_lang       # 推理语言分段
wordsegment g2p_en               # 英文文本前端（参考文本含字母时）
torchcodec                       # 已装但 Windows 缺 ffmpeg 共享DLL 用不了 → 已用 soundfile 绕过
```

本地 ASR 模型：`GPT-SoVITS-v2pro/GPT-SoVITS-v2pro/tools/asr/models/`（paraformer+vad+punc，无需联网）。

## 对 GPT-SoVITS 源码的必要修改（Windows 适配）

> 这些是 vendored 副本的本地修改，环境重建时需重新应用。

1. **`GPT_SoVITS/AR/data/data_module.py`** — Windows 下 `num_workers=0` + 禁用
   `persistent_workers`/`prefetch_factor`（多进程 DataLoader 导致 0xC0000005 访问违规）。
2. **`GPT_SoVITS/s1_train.py`** — `devices=1` + `strategy="auto"`（避免 Windows 上 DDP+gloo
   段错误）；手动 `init_process_group(gloo, world_size=1)`（供 DistributedBucketSampler）；
   `enable_progress_bar=False`（避免 rich 往 GBK 控制台打印 • 报 UnicodeEncodeError）。
3. **`modules/M5_runtime/tts_service/gpt_sovits_wrapper.py`** — import inference 前 monkeypatch
   `torchaudio.load` 用 soundfile（torchaudio 2.11 默认 torchcodec，Windows 缺 ffmpeg 共享DLL）。
4. **`modules/M5_runtime/tts_service/voice_clone.py`** — manifest 排序 key 容错 `snr_estimate` 为 null。

## 已知坑

- **参考音频必须 3~10 秒**：原切片是 15s，`finalize_voice.py` 自动裁中段 8s 并对裁剪段重新 ASR
  得到匹配文本（音频与 prompt_text 必须对应，否则零样本质量下降）。
- 切片首条常是片头静音，ASR 会跳过（list 行数 < 切片数属正常）。
- 数据量少的老师（002/003/004/006 各 15 条切片）参考文本可能选到结尾下课语，音色仍可用但
  韵律样本偏少；005（25 条）、001（50 条）数据更充分。
