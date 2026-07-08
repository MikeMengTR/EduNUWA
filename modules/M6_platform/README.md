# M6 · Platform — 实现文档

> **EduNUWA v2 的 APP 外壳**：把 M1-M5 缝合成完整产品，提供教师端、学生端、AI 教学演示。

---

## 1. 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python Flask + Flask-CORS |
| 前端 | React 18 + Vite + React Router |
| AI | DeepSeek API (OpenAI 兼容) |
| TTS | edge-tts（云）+ GPT-SoVITS（GPU，待 conda 环境） |
| 存储 | JSON 文件（`data/` 目录） |

---

## 2. 已实现功能

### 2.1 认证系统

| 功能 | API |
|------|-----|
| 注册（教师/学生） | `POST /api/v1/auth/register` |
| 登录 | `POST /api/v1/auth/login` |
| 获取当前用户 | `GET /api/v1/auth/me` |

### 2.2 教师管理 + M1/M2/M3 集成

| 功能 | API |
|------|-----|
| 教师卡片 CRUD | `POST/GET/PUT /api/v1/teachers` |
| 教师详情（含 Skill 指标） | `GET /api/v1/teachers/{id}` |
| Skill 档案查看 | `GET /api/v1/teachers/{id}/skill` |
| Transcripts 列表 | `GET /api/v1/teachers/{id}/transcripts` |
| **上传素材 → M1 处理** | `POST /api/v1/uploads` |
| M1 进度查询 | `GET /api/v1/tasks/{task_id}` |
| **一键蒸馏 → M2** | `POST /api/v1/teachers/{id}/distill` |
| 蒸馏状态检查 | `GET /api/v1/teachers/{id}/distill/status` |
| **M3 风格匹配** | `POST /api/v1/match` |

### 2.3 AI 教学演示 + M4/M5

| 功能 | API |
|------|-----|
| AI 对话（Skill 驱动） | `POST /api/v1/chat/{teacher_id}` |
| 对话历史 | `GET/DELETE /api/v1/chat/{teacher_id}/history` |
| **教学演示（TTS+黑板+形象）** | `POST /api/v1/chat/{teacher_id}/demo` |
| 学习会话管理 | `/api/v1/sessions/*` |
| TTS 文本转语音 | `POST /api/v1/tts` |
| 可用音色列表 | `GET /api/v1/voices` |
| M5 播放器 | `/runtime/` |

### 2.4 视频功能

| 功能 | API |
|------|-----|
| 视频上传 | `POST /api/v1/videos/upload` |
| 视频列表 | `GET /api/v1/videos` |
| 视频流播放（支持拖动） | `GET /api/v1/videos/{id}/stream` |
| 教师视频列表 | `GET /api/v1/teachers/{id}/videos` |

### 2.5 教师主页 + 评价

| 功能 | API |
|------|-----|
| 教师详情主页（含指纹/标签/策略） | `GET /api/v1/teachers/{id}` |
| **学生评价（评分+评论）** | `POST /api/v1/teachers/{id}/feedback` |
| 评价列表 | `GET /api/v1/teachers/{id}/feedback` |
| 评价统计（均分/分布） | 同上 |

### 2.6 前端页面

| 路径 | 角色 | 功能 |
|------|------|------|
| `/login` | 所有人 | 登录/注册 |
| `/teacher` | 教师 | 教师卡片 + Skill 状态 + 蒸馏按钮 |
| `/teacher/upload` | 教师 | 上传素材 + M1 进度 |
| `/teacher/videos` | 教师 | 上传/管理教学视频 |
| `/student` | 学生 | 教师列表 + M3 风格匹配搜索 |
| `/teacher/:id` | 所有 | 教师主页（头像/指纹/标签/评价） |
| `/classroom/:id` | 学生 | 虚拟教室（M5 黑板+语音+形象） |
| `/student/videos/:id` | 学生 | 观看教师视频 |

---

## 3. 模块集成

| 模块 | 集成方式 | 状态 |
|------|---------|------|
| **M1** Ingest | `submit_ingest_task()` 异步上传处理 | ✅ |
| **M2** Distill | 一键蒸馏 + metric_extractor | ✅ |
| **M3** Catalog | `match_teachers()` LLM 语义匹配 | ✅ |
| **M4** Orchestrator | `OrchestratorPipeline` 教学事件生成 | ✅ |
| **M5** Runtime | TTS + 播放器 iframe + 黑板 + 虚拟形象 | ✅ |
| **Stream** | 流式编排（待接前端） | ⚳ |

---

## 4. 6 位种子教师

| 教师 | 学科 | 风格标签数 | 头像 |
|------|------|-----------|------|
| 概率论·华东师大 | 概率论 | 8 | ✅ |
| 高等数学·某高校 | 高等数学 | 12 | ✅ |
| 机器学习·北理工 | 机器学习 | 10 | ✅ |
| 思政·华南理工 | 思想道德与法治 | 10 | ✅ |
| 园林史·北林 | 西方园林史 | 12 | ✅ |
| 线性代数·某高校 | 线性代数 | 12 | ✅ |

每位教师包含：
- M1 产物：`transcripts/`（ASR 转写）
- M2 产物：`skills/v2_full/TeacherSkill.md` + `skill_profile.json`
- 虚拟形象：`avatar/`（两张图，口型同步切换）

---

## 5. 启动方法

### 前置依赖

```bash
# Python 依赖
pip install flask flask-cors openai python-dotenv requests edge-tts

# 可选（M1 视频上传 + ASR）
pip install moviepy faster-whisper

# 前端
cd modules/M6_platform/frontend
npm install
```

### 配置 API Key

在项目根目录 `.env` 文件中填入：

```
DEEPSEEK_API_KEY=sk-你的密钥
DEEPSEEK_MODEL=deepseek-chat
```

不配置也可启动（AI 对话使用模拟回复，其他功能正常）。

### 启动

**方式一：一键启动**
```
双击 modules/M6_platform/start.bat
```

**方式二：手动启动**
```bash
# 终端 1 — 后端
cd modules/M6_platform/backend
python app.py
# → http://localhost:5000

# 终端 2 — 前端
cd modules/M6_platform/frontend
npm run dev
# → http://localhost:3000
```

浏览器打开 **http://localhost:3000**。

---

## 6. 典型使用流程

### 教师端
1. 注册教师 → 创建教师卡片
2. 上传教学视频/音频 → M1 自动 ASR 转写
3. 等待处理完成 → 点击「一键蒸馏」
4. 系统生成 TeacherSkill.md + skill_profile.json
5. 上传教学视频（可选）

### 学生端
1. 注册学生 → 浏览教师列表
2. 使用 M3 风格匹配：「我需要幽默、用生活例子的数学老师」
3. 点击教师 → 进入虚拟教室
4. 输入问题 → 点「🎓 教学演示」
5. 观看 AI 讲课（黑板 + 语音 + 教师形象）
6. 点教师头像 → 进入教师主页 → 写评价

### 虚拟教室体验
```
┌──────────────────────┬──────────────┐
│  M5 播放器            │  对话面板     │
│  ┌─────────────────┐ │              │
│  │ 黑板渲染区       │ │  User: 问题  │
│  │ ▶ 函数的概念     │ │  AI: 回答   │
│  │ ▸ 定义...       │ │              │
│  └─────────────────┘ │  [输入框]    │
│  [教师形象] [▶Play]  │  [🎓演示]    │
└──────────────────────┴──────────────┘
```

---

## 7. API 规范

- 所有端点 `/api/v1/` 前缀
- 响应格式 `{code: 0, message: "ok", data: {...}}`
- 错误码区段：4000(参数) 4010(认证) 4030(权限) 4040(不存在) 5000(服务器) 5030(下游)

---

## 8. 文件结构

```
modules/M6_platform/
├── backend/                   # Flask 后端
│   ├── app.py                 # 主入口
│   ├── auth.py                # 认证 + 响应格式
│   ├── teachers.py            # 教师 CRUD + M3 匹配
│   ├── upload.py              # M1 上传触发
│   ├── distill.py             # M2 一键蒸馏
│   ├── chat.py                # AI 对话（Skill 驱动）
│   ├── video.py               # 视频上传/播放
│   ├── pipeline.py            # M4/M5 编排 + TTS
│   └── feedback.py            # 学生评价
├── frontend/                  # React 前端
│   ├── src/
│   │   ├── pages/
│   │   │   ├── LoginPage.jsx
│   │   │   ├── TeacherDashboard.jsx
│   │   │   ├── StudentDashboard.jsx
│   │   │   ├── TeacherProfile.jsx
│   │   │   ├── VirtualClassroom.jsx
│   │   │   ├── UploadPage.jsx
│   │   │   ├── VideoManagePage.jsx
│   │   │   └── VideoWatchPage.jsx
│   │   ├── components/
│   │   │   ├── Navbar.jsx
│   │   │   ├── TeacherCard.jsx
│   │   │   ├── ChatBox.jsx
│   │   │   └── VideoPlayer.jsx
│   │   └── api.js
│   └── vite.config.js
└── start.bat                  # 一键启动
```
