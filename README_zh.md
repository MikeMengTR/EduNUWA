# EduNUWA

**把教师的「教学能力」蒸馏为可复用的数字资产——让学生向一个真正“像那位老师”的 AI 教师提问学习。**

[English →](README.md)

EduNUWA 是一个研究原型：把录制的授课视频蒸馏为结构化、可调用的 **TeacherSkill**，并用它驱动一个全链路流式的虚拟课堂——学生提出问题，数字教师**以该教师的讲解风格**作答：用克隆（或合成）音色开口讲课，同时在虚拟黑板上逐句写下提纲、公式和插图，边生成边播放。

> 本项目关注的是**教师讲解思维的结构化提取与迁移**——如何引入概念、建立直觉、设计板书、主动防错——而非复刻真实教师的身份。

## 工作原理

系统是一条数据契约驱动的六模块流水线，模块间通过文件路径 + Python 函数调用解耦（内部不走 HTTP）：

```
教师授课音视频
  → M1 摄取     ASR 转写                → teacher_transcript.json
  → M2 蒸馏     讲解风格蒸馏            → TeacherSkill.md + skill_profile.json + 质量等级
  → M3 目录     双轨教师发现（按姓名 / 按风格）

学生问题
  → M4 编排     生成教学事件            → teaching_events.json
                （speak / board / formula / table / pause / quiz / image）
  → stream      节奏层：按教学节奏给事件排时间
  → M5 运行时   流式 TTS + 黑板/数字人前端
  → M6 平台     把 M1–M5 缝合成产品的 Web 应用（Flask + React）
```

关键设计决策：

- **数据契约是单一真相源**——所有跨模块交接文件（`teaching_events.json`、`playback_data.json` 等）都有入库的 JSON schema。
- **全链路流式课堂**——首句开口延迟 ≈ 首句生成 + 首句 TTS。LLM 流式产出教学事件，TTS 逐句合成并预取下一句，前端边播边等后续生成。
- **蒸馏的是风格，不只是内容**——M2 产出七段契约的 `TeacherSkill.md`（教学理念、讲解模式、板书策略、语言风格等），编排器把它注入每一次讲课的 prompt。
- **反馈驱动的 Skill 自进化**——学生评价通过「文本梯度」闭环回流：众评风格标签按确定性公式累积置信度，Skill 修订需教师确认后才生效。
- **优雅降级**——没有 GPU / 音色模型？TTS 自动降级 edge-tts。没配视觉 API？图片标注退回纯文本。普通笔记本即可跑通 demo。

## 快速上手

前置：Python 3.10+、Node.js 18+、ffmpeg（edge-tts 转 WAV 用）。

```bash
# 1. Python 依赖（建议 conda 环境；重型 ASR/TTS 依赖对 demo 是可选的）
pip install -r requirements.txt
pip install -r modules/M6_platform/backend/requirements.txt

# 2. 配置
cp .env.example .env       # 填入 DEEPSEEK_API_KEY（必需）

# 3. 后端（Flask，端口 5000）
python modules/M6_platform/backend/app.py

# 4. 前端（Vite + React，端口 3000）
cd modules/M6_platform/frontend
npm install
npm run dev
```

打开 `http://localhost:3000`，注册学生账号，选择一位示例教师，在虚拟课堂里提问。

Windows 下 `modules\M6_platform\start.bat` 可一键完成第 3–4 步（需先把脚本里的 Python 路径改成你的环境）。

### 可选的重型组件

| 组件 | 用途 | 缺省时 |
|---|---|---|
| faster-whisper / FunASR | 摄取你自己的授课视频（M1） | 使用内置示例转写 |
| GPT-SoVITS + 音色模型 | 教师专属音色克隆 | 自动降级 edge-tts |
| DASHSCOPE_API_KEY（Qwen-VL） | 图片智能标注、PPT 抽图 | 退回文本标注 |

## 仓库导览

| 路径 | 内容 |
|---|---|
| `modules/M1_ingest/` | 音视频 → 转写（含防幻觉参数的 ASR 管线） |
| `modules/M2_distill/` | 转写 → TeacherSkill.md + 风格画像 + 质量等级；标签进化器 |
| `modules/M3_catalog/` | 教师发现与匹配（LLM 排序） |
| `modules/M4_orchestrator/` | 问题 + Skill → 教学事件 |
| `modules/stream/` | M4→M5 之间的教学节奏层 |
| `modules/M5_runtime/` | TTS 服务、流式播放器、黑板/数字人前端 |
| `modules/M6_platform/` | Flask 后端 + React 前端（账号、课堂、课程、图库、监控台） |
| `docs/` | 架构与模块设计文档、API 契约 |
| `data/` | 多租户数据布局（内含匿名化示例教师） |
| `scripts/` | 教学插图生成、音色训练、端到端测试脚本 |

核心数据契约见 [`docs/api_contract.md`](docs/api_contract.md)，各模块设计文档见 [`docs/modules/`](docs/modules/)。注意：模块文档描述的是目标架构，与代码不一致时**以代码为准**（`CLAUDE.md` 里有真实实现的导览）。

## 示例数据与伦理

- `data/teachers/` 下内置的是**匿名化示例教师**（化名、不含音色模型），保证开箱即跑。
- 如果你摄取真实课程：请先取得教师本人同意，尤其是训练音色克隆之前。TTS 服务的设计保证音色模型只存在本地、绝不进 git。

## 许可

[MIT](LICENSE)。第三方组件见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)——特别地，仓库内含 [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS)（MIT）推理代码副本用于本地音色克隆。
