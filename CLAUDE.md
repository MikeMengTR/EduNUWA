# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目本质

EduNUWA 把教师的"教学能力"蒸馏为可复用的数字资产。核心链路是一条**数据契约驱动的流水线**：

```
教师音视频 → M1 ASR → teacher_transcript.json
           → M2 蒸馏 → TeacherSkill.md + skill_profile_v2.json + grade
           → M3 目录（双轨发现：按姓名 / 按风格）
学生问题   → M4 编排 → teaching_events.json（speak/board/formula/table/pause/quiz）
           → [stream 流式延迟层（可选）：按 L1-L7 教学节奏给 events 排时间]
           → M5 运行时 → TTS(audio_manifest.json) + playback_data.json → Live2D/黑板前端
M6 是把 M1–M5 缝合成产品的 APP 外壳
```

模块间**通过文件路径 + Python 函数调用解耦**，不通过内部 HTTP。每个模块函数返回 `dict`，必含 `status` 字段（`"success"` / `"error"`），成功时返回产物文件路径，失败时返回 `message`。这是跨模块集成的核心约定，见 `docs/api_contract.md`。

## ⚠️ 文档 vs 实际实现

`docs/modules/M6_platform.md` 等模块文档是**规划方案（aspirational）**，描述了 FastAPI + JWT + ORM + Celery 等目标架构。**实际落地的代码与之不同**，以代码为准：

- M6 后端是 **Flask**（不是 FastAPI），端口 **5000**，入口 `modules/M6_platform/backend/app.py`
- 鉴权是 `auth.py` 里的**内存 token dict**（`tokens = {}`），不是 JWT；用户存 `data/users.json`
- 没有数据库 / ORM / Celery；状态都落地为 JSON 文件
- M6 前端是单一 Vite + React 应用（`frontend/`），端口 **3000**，不是分离的师生两端

读模块 `docs/` 了解**设计意图和数据契约**，读 `modules/*/` 代码了解**真实行为**。

## 常用命令

### 启动整个平台（M6）
```bat
modules\M6_platform\start.bat
```
该脚本：杀掉占用 5000 端口的旧进程 → 用 conda 环境 `edu`（`D:\anaconda3\envs\edu\python.exe`）启动 Flask 后端 → `npm run dev` 启动 Vite 前端。后端 `http://localhost:5000/api/v1`，前端 `http://localhost:3000`。

### 手动启动后端 / 前端
```powershell
# 后端（必须用 edu 环境，依赖 torch/funasr/edge-tts 等都装在这里）
& D:\anaconda3\envs\edu\python.exe modules\M6_platform\backend\app.py

# 前端
cd modules\M6_platform\frontend; npm install; npm run dev
```

### 单模块本地测试入口
每个模块都有独立运行/测试脚本（约定见 api_contract.md §8.4）：
```powershell
& D:\anaconda3\envs\edu\python.exe modules\M1_ingest\run.py
& D:\anaconda3\envs\edu\python.exe modules\M5_runtime\run.py
& D:\anaconda3\envs\edu\python.exe modules\M4_orchestrator\test_m4.py
& D:\anaconda3\envs\edu\python.exe modules\M5_runtime\tts_service\test_package.py
```

### M5 前端（数字人 + 黑板运行时）
独立前端 `modules/M5_runtime/frontend`，构建后由 M6 后端在 `/runtime/` 路由下提供（读取 `frontend/dist`）。修改 M5 前端后需 `npm run build`，否则 `/runtime/` 看到的是旧产物。

## 关键约定与红线

- **环境**：所有 Python 在 conda 环境 `edu` 运行。重模型依赖（faster-whisper、funasr、GPT-SoVITS、torch）都在此环境，系统 Python 跑不起来。
- **API 响应格式**：统一 `{code, message, data}`，`code=0` 表示成功。用 `auth.py` 的 `ok(data, message)` / `err(message, code, http_status)` 构造，不要手写 jsonify。
- **鉴权**：除 `/auth/register`、`/auth/login` 外，路由加 `@require_auth`（来自 `auth.py`）。音频文件路由 `/api/v1/audio/...` 例外——浏览器 `<audio>` 标签无法带 header，故音频公开、JSON 需 token、`playback_data.json` 公开（session_id 本身即随机密钥）。
- **`.env` 绝不提交**（已 gitignore）。`DEEPSEEK_API_KEY` 必需（AI 教学回复 + 文本精修，走 `https://api.deepseek.com`，OpenAI 兼容协议）。`DASHSCOPE_API_KEY` 可选且当前 Cloud ASR 接口不可用，默认走本地 Whisper。
- **多租户数据隔离**：所有运行时数据按 `data/teachers/{teacher_id}/`、`data/courses/{course_id}/`、`data/sessions/{session_id}/` 划分，禁止全局单实例。
- **依赖方向无环**：M1→M2→M3/M4→M5，M6 顶层编排。M6 后端通过 `sys.path.insert(_project_root)` 把项目根加入路径，再 `from modules.M4_orchestrator.pipeline import ...` 调用各模块。M6 只编排、不实现业务逻辑（蒸馏/编排/渲染/评分属于 M1–M5）。
- **Skill 质量门槛**：M2 产出 grade（A/B/C/D），grade < B 软拒绝上架。

## 数据契约（跨模块交接文件）

字段级 schema 是单一真相源，改动前先看 schema 文件：

| 文件 | 生产 | 消费 | schema |
|---|---|---|---|
| `teacher_transcript.json` | M1 | M2 | `docs/api_contract.md` §2 |
| `TeacherSkill.md` | M2 | M4 | `docs/api_contract.md` §3（七段：Skill Purpose / Trigger / Teaching Philosophy / Explanation Pattern / Blackboard Policy / Speech Policy / Output Contract）|
| `skill_profile_v2.json` | M2 | M3,M4 | `modules/M2_distill/schemas/skill_profile_v2.schema.json` |
| `teaching_events.json` | M4 | M5 | `modules/M4_orchestrator/schemas/teaching_events.schema.json` |
| `audio_manifest.json` | M5 | M5 player | `modules/M5_runtime/schemas/audio_manifest.schema.json` |
| `playback_data.json` | M5 | 前端 | `modules/M5_runtime/schemas/playback_data.schema.json` |

**`playback_data.json` 的字段名必须严格对齐 M5 前端 `types.ts`**（`pipeline.py` 的 `_simple_playback` 里有注释强调），改 timeline 字段时两边一起改。teaching_events 的 board `action` 枚举：`write_title / write_subtitle / write_bullets / write_steps / write_summary / clear_board / highlight`。

### 公式约定（LLM 输出 → 渲染 → TTS 三方契约）
- 数学公式只能出现在 `[formula]` 事件或 `[board]` 文本中，统一用 `$...$`（行内）/ `$$...$$`（块级）包裹；`[speak]` 文本**绝对不含 LaTeX**（TTS 念不出来），需要提到公式时改用自然语言。该规则写死在 LLM prompt 里（`pipeline.py` teaching_demo 与 `course.py` 的 `_FORMAT_RULES`，两处需保持一致）。
- 前端渲染走 `modules/M5_runtime/frontend/src/shared/renderMath.ts`（KaTeX），它兼容 AI 实际输出的各种定界符（含 `\(...\)`、`\[...\]`），因为 AI 常把公式直接写进 board 文本而非独立 formula 事件。

### 教学插图（图库检索 → LLM 按 ID 引用 → 黑板渲染）
黑板可插入预置教学图（静态图/GIF），事件类型 `image`，链路完全本地化、零额外首句延迟：

- **图库** `data/media_library/`（`index.json` + `images/{subject}/IMG_{subject}_{0000}.*`），schema 在 `modules/M4_orchestrator/schemas/media_library.schema.json`。维护脚本 `scripts/media_library/`：`gen_math_figures.py`（matplotlib 黑板风自制图）→ `ingest.py`（校验/缩放/分配 ID/原子写 index，GIF 限 5MB 不重采样）→ `verify.py`（index↔文件一致性）。元数据三字段分工：`keywords` 给检索（对学生问题做中文子串匹配）、`llm_desc` 给 LLM 决策、`caption` 给学生看。
- **检索与注入** `M6 backend/media_library.py`（只读零依赖）：`retrieve_candidates(query)` 零命中返回空 → `build_image_prompt_block` 返回空串，**prompt 与无图库时逐字节一致**（回归红线，test_media_library.py 锁定）。demo 两链路（`_build_demo_prompt` 的 `image_block` 参数）与 course.py 预录共用同一规则块。
- **防幻觉闸门**：`DemoEventParser(image_catalog=...)` 只认注入候选集内的 ID，编造 ID 静默丢弃且**不耗 seq**；ID→URL（`/api/v1/media/...`）服务端定稿，前端对图库结构无知。改解析逻辑跑 `test_event_stream.py`（含 image 专项）。
- **服务与渲染**：`/api/v1/media/<path>` 公开（`<img>` 带不了 header）+ 长缓存（入库后文件不可变）；M5 前端 `BoardImage.tsx`（限高 40vh、onError 整项隐藏不断课、GIF 自动播放），StreamingPlayer image dwell 默认 3s。
- **教师端上传（写侧）** `M6 backend/media_admin.py`（与只读的 media_library.py 分工，不污染那条红线）：路由 `/api/v1/images*`（list/annotate/upload/PATCH/DELETE，全 `@require_role("teacher")`），前端 `/teacher/images`（`ImageLibrary.jsx`）。**AI 标注 = 视觉优先 + 文本兜底**：传图 + 配了 `DASHSCOPE_API_KEY` → Qwen-VL 直接看图产元数据（阿里云 DashScope OpenAI 兼容接口，复用 M1 链路；`QWEN_VL_MODEL` 默认 `qwen3-vl-plus`、`QWEN_VL_BASE_URL` 可覆盖），失败/无 key 时退回 DeepSeek 文本扩写（需教师写一句话）。当前**全部进全局共享库**（上线前再按 `uploaded_by` 切教师隔离，已预埋该字段，零迁移）；教师只能改/删自己上传的，预置图只读。ID 受 `^IMG_[a-z]+_[0-9]{4}$` 约束 → subject 必须小写 ascii（`SUBJECTS` 映射中文标签）。**subject 由 AI 识图时一并推断**（annotate 返回 `subject`，前端自动预填选择器、教师可改，跨学科/拿不准默认 `other`），教师无需手选；它只作组织/ID 命名，不参与检索精确率（`retrieve_candidates` 的 `subject_hint` 加成在生产链路未启用）。
- **从 PPT 抽图**（教师端拖入 .pptx）`POST /api/v1/images/extract-ppt`：`media_admin._extract_pptx_images` 把 .pptx 当 zip 读 `ppt/media/` 下位图（md5 去重、<200px 小图本地滤掉、透明底合成白底统一转 PNG、GIF 保动图、跳过 emf/wmf 矢量），再对每张走 `_vl_judge_and_annotate`（一次视觉调用同时**判断"是否适合做教学插图"过滤 logo/背景/装饰**并产出元数据，`ThreadPoolExecutor` 并发、`_PPT_MAX_IMAGES=40` 上限），合格的连同 base64 返回给前端进批量编辑流。**需 `DASHSCOPE_API_KEY`**（靠像素判断,无文本兜底）。
- **关键词 = 调用场景，非内容清单（红线）**：检索是中文**子串精确匹配**（关键词须原样出现在学生问题里才命中）。`keywords` 要回答的是**「学生问什么时该调出这张图」**而非「图里有什么」：①**原子短词**（2-5 字，把「轨迹抛物线」拆成「抛物线」「轨迹」）；②**只放图真正用来讲解的核心概念**——图里顺带出现、非主旨的概念不要放，否则会在错误场景误命中（例「生物神经元 vs 人工神经元对比图」放「人工神经元」「神经元对比」，**不放裸的「生物神经元」**，否则纯生物课讲神经元就被误调）；③**覆盖学生会用的各种说法**：中文全称+英文缩写+别名都要列（多层感知机→「多层感知机」「MLP」「感知机」；正态分布→「正态分布」「高斯分布」），否则学生用缩写问就漏（实测「什么是MLP」曾因关键词只有「神经网络」而零命中）；④不放「图」「运动」「物体」等泛词。`llm_desc` 写清**适合在讲什么/做什么时展示**（对比图点明不适合单讲某概念），它是 LLM 那道精确率闸门的判据。三道闸门：retrieve（子串召回，宁宽）→ LLM 看 llm_desc 判贴合（`build_image_prompt_block` 里有「沾词不算贴合」指令）→ DemoEventParser 防幻觉。关键词/llm_desc 规则写死在 media_admin.py 的 `_vl_prompt`（视觉）与 `_annotate_prompt`（文本兜底）两处，**改一处必同步另一处 + 同步本节**。彻底覆盖同义/口语提问需 embedding 语义检索（与 M3 同源的阶段二，未做）。
- **查询扩展（demo/课堂）** `pipeline._image_search_query`：子串检索只认原句逐字出现的词（"什么是MLP" 不含 "神经网络" 就漏）。故学生原句先过一遍轻量 `deepseek-chat`，抽成「核心概念的各种叫法（全称/缩写/别名，如 MLP↔多层感知机、高斯↔正态）」拼到原句后再检索，扩召回。**只扩同义叫法、不发散到相关但不同的概念**（否则会误召回，如「勾股定理」发散出「面积法」误中定积分图）。进程内缓存 + 超时 5s 退回原句 + `USE_IMAGE_QUERY_EXPANSION` 可一键关；代价是讲课前多一次轻量调用（计入首句延迟）。course.py 预录用章节标题+brief 检索、已够丰富，不走扩展。图库涨到 ~50-80 张以上应转 embedding 语义检索。
- 验收脚本：`scripts/test_image_pipeline_e2e.py`（media 路由 + 流式配图 + 零候选控制组，需后端运行）、`modules/M6_platform/test_image_browser.py`（Playwright 黑板渲染）。

## 模块入口速查

| 模块 | 关键导出 / 入口 |
|---|---|
| M1 Ingest | `modules/M1_ingest/run.py`；ASR 子模块 `asr_pipeline/`（有自己的 `CLAUDE.md`，**修改 ASR 前必读**） |
| M2 Distill | `modules/M2_distill/skill_distiller/nuwa_distill.py` |
| M4 Orchestrator | `OrchestratorPipeline().run(session_id, user_question, teacher_skill_path, mode)`（mode: `ondemand`/`follow`），`pipeline.py` |
| M5 Runtime | `tts_service` 导出 `generate_tts_batch`、`StreamingTTS`、`get_clone_references`、`edge_tts_synthesize`；`build_playback/` 提供 `build_playback_data` |
| stream | `modules/stream/`：M4→M5 之间的流式延迟层，按 L1-L7 节奏指标（首句开口≤8s、句间停顿、板书后接话等）给 events 排时间。CLI：`python modules/stream/run.py stream|build|verify`，详见其 `README.md` |
| M6 Platform | `backend/app.py` 注册各蓝图：`auth/teachers/upload/video/chat/pipeline/distill/feedback/course/evolution/voice_train/materials/media_admin/platform_admin`，每个文件暴露 `register_routes(app)`；`voice_service.py` 不是蓝图，是教师音色合成服务（被 pipeline.py 调用） |

### 平台监控台（俯瞰全平台 + 管控，`platform_admin.py` + `frontend/src/pages/platform/`）
运营/课题方查看与管控全平台数据的后台，与师生账号体系**完全隔离**：

- **入口与鉴权**：登录页 `/login` **右下角低调齿轮入口**「平台监控台」→ 输口令 → `/platform`。口令是 `.env` 的 `PLATFORM_KEY`（gitignored；无配置默认 `edunuwa-admin`）。前端存 `localStorage.platform_key`，请求带 **`X-Platform-Key` 头**（不是 Bearer token）；装饰器 `require_platform_key`（常量时间比较）。`App.jsx` 让 `/platform/*` 在无账号登录态下也可达且不挂师生 Navbar。这条路由是 `{code,message,data}` 信封体系内、但**鉴权通道独立**的一组接口。
- **后端 `platform_admin.py`**：仿 `media_library.py` 的**只读零依赖红线**——读路径只 `import auth`(+标准库)自己扫 `data/`，**不 import M1–M5 重模块**；写路径（管控）一律在处理函数内**惰性 import** 业务模块，**复用其既有原子写/锁/统计同步**，不另起一套。
  - **只读聚合**(9)：`GET /api/v1/platform/{overview,users,students/<uid>,teachers,teachers/<tid>,sessions,feedback,matches,media}`。
  - **管控写**(9)：`DELETE …/users/<uid>`、`POST …/users/<uid>/password`、`POST …/teachers/<tid>/visibility`、`POST …/teachers/<tid>/account`(给无账号教师分配下一个 `t{N}` 账号、密码 1234，并回填 `teacher_card.user_id`)、`POST …/courses/<tid>/<cid>/publish`、`DELETE …/courses/<tid>/<cid>`、`DELETE …/feedback/<tid>/<fid>`(同步 `teacher_card` stats)、`POST …/media/<id>/status`、`DELETE …/media/<id>`。教师卡靠 `user_id` 关联登录账号，平台端教师列表/详情附 `account_username`/`account`，无账号者标「⚠ 无账号」可一键分配。
- **教师上下架是跨模块约定**：`POST …/teachers/<tid>/visibility` 在 `teacher_card.json` 写 `hidden` 标志；`teachers.py` 的 `list_teachers`(学生发现页)与 `match_teachers`(M3 匹配)**都过滤 `hidden`**（改可见性逻辑两处需同步，`list_all_teachers()` 本身不过滤——它也被「按 user_id 找自己卡片」的内部调用复用）。
- **前端**：`pages/platform/`（`PlatformApp` 壳 + 口令门 + 七页 Overview/Users/Teachers/Sessions/Feedback/Matches/Media，下钻走 `Drawer`）；图表是**零依赖手写 SVG** `components/charts.jsx`（项目坚持极简依赖，**不引入 recharts/echarts**）；写操作走 `ui.jsx` 的 `confirmRun`(二次确认)+`ActionBtn`，成功后 `useFetch` 的 `reload()` 重拉。`api.js` 的 `platformRequest` 带口令头、403 自动清 key 退回口令页。
- **风格速写/指纹/词云全站一套口径**：平台监控台 teacher 抽屉**直接复用学生端共享组件 `components/StyleProfile.jsx`**（`StyleSketchCard`+`TeachingStyleCard`，即 `buildSketch`/`buildRadar`/`buildCloudWords`）。后端 `platform_teacher` 用 `teachers.load_skill_profile`(优先 `_full` 版本，与学生端 `get_teacher` 同源)把 `base_metrics`/`pedagogy`/`style_tags`/`tags`/`live_tags` 富化进 `card`，前端喂给组件 → 平台端与学生端逐像素一致、不漂移。雷达 6 轴来自 `base_metrics`(设问频率/语速)+`pedagogy`(类比密度/直觉优先/主动防错/结构总结)，组件自注「仅作示意」。**坑**：profile 两种格式——legacy(示范教师01)带现成 `fingerprint` 六维字段、新格式(绝大多数)无该字段而靠 style_tags+base_metrics+pedagogy；StyleProfile 只读后者，故必须选到含 base_metrics/pedagogy 的版本(`load_skill_profile` 优先 `_full`)每位老师才都能渲染（示范教师01 `v2` 只有 legacy fingerprint，`v2_full` 才有 base_metrics/pedagogy）。教师卡列表另有简短 `style_line`(top 标签拼接，仅作卡片副标题)。前端复用 StyleProfile 必须包一层 `<div className="tp2">` 提供 `--c-form/--c-intuit/--c-style` 作用域变量。
- 注意：`playback_data.json` 的 `teacher_id` 是已知 bug(=session_id)，sessions 接口改从 `events.json` 取真实 teacher；`teacher_card.subject` 兼容 str/list 两种历史格式（`_subject_str`）。验收脚本见 `scratchpad/smoke_platform*.py`（test_client 进程内，不启重模型）。

### TTS：教师专属音色 + 降级
M6 的 `/api/v1/tts`（参数 `engine: auto|sovits|edge`）链路：优先 **voice_service**（按 `teacher_id` 读 `data/teachers/{tid}/voice/voice_profile.json`，用该老师微调的 GPT-SoVITS 音色合成；进程内 `StreamingTTS` 单例 + 锁串行，切老师只换 GPT 权重、SoVITS 底模共享；`warmup()` 失败的老师进禁用集）→ 无专属音色或失败时降级 **edge-tts**（`zh-CN-YunxiNeural`，需 ffmpeg 转 WAV，否则返回 MP3）。GPT-SoVITS 模型在 `GPT-SoVITS-v2pro/`（示例老师为预置微调音色 `voice_id="songhao"`）；教师音色训练管线在 `scripts/voice_training/`（`train_gpt.py` / `train_all.py`）。

**流式播放**：M5 前端 `player_runtime/StreamingPlayer.ts` 在 `/runtime/?...&stream=1` 模式下逐句按需请求 `/api/v1/tts` 并预取下一句（边合成边播），不依赖预生成的 `playback_data.json` 绝对时间线。与静态 Player 同接口（play/pause/setSpeed/on/destroy）。

### 虚拟课堂全链路流式（demo/stream）
学生提问 → DeepSeek 边生成边播的完整流水线（首句开口 ≈ 首句生成 + 首句 TTS，不再等全文）：

- **后端** `POST /api/v1/chat/<tid>/demo/stream`（pipeline.py `teaching_demo_stream`）：DeepSeek `stream=True` → `event_stream.py` 的 `LineAssembler`+`DemoEventParser` 增量解析 → SSE 帧 `meta → event×N → summary → done`（异常发 `error`，`partial` 表示已有部分事件可播）。**该路由是 `{code,message,data}` 信封的唯一例外**（流开始前的校验失败仍用标准 `err()`）。summary（开场引入语）由并行线程生成、尾部插入，不阻塞事件流。流结束/中断都会落盘 `events.json`（中断时带 `"partial": true`）。
- **对话记忆**：demo 与文字 chat 共用 `data/conversations.json`（key=`{user_id}_{teacher_id}`，`chat.py` 的 `get_history`/`append_history`，模块级锁保护）。demo 读最近对话做"前情提要"注入 prompt（衔接语必须有据、meta 问题直接回顾——规则在 `_build_demo_prompt`），讲课结束写回 `(问题, summary+板书提纲)`（assistant 条目带 `"kind":"demo"`）。文字 chat 注入 LLM 前要剥掉附加字段只留 role/content。验收脚本 `backend/test_demo_memory.py`。
- **解析器**：`_parse_demo_response` 已是 `event_stream.parse_demo_text` 的薄包装（course.py 离线预录共用），改解析逻辑必须跑 `test_event_stream.py` 等价测试。
- **M6 前端** `VirtualClassroom.jsx`：`api.js teachingDemoStream`（fetch+ReadableStream，POST 带 Authorization，不用 EventSource）；**固定双槽 iframe**（两个元素永不换位/换 key——React 移动 iframe 节点会触发浏览器强制 reload 丢事件）；事件经 postMessage 推进 iframe。`USE_DEMO_STREAM=false` 一行回退旧链路，流式在 meta 前失败自动降级。
- **M5 前端** `/runtime/?push=1&session=...`：不 fetch events，`StreamingPlayer` 以 live 模式空缓冲起播（`waiting` 态），父页面经 postMessage 推事件（协议：iframe→父 `m5:ready`/`m5:end`，父→iframe `m6:init`/`m6:events`/`m6:done`/`m6:error`，均校验 origin+session，按 seq 去重，重复 `m5:ready` 重发全量自愈）。`endOfStream()` 前缓冲耗尽只进 `waiting` 不发 `end`。
- 验收脚本：`backend/test_demo_stream_client.py`（SSE 帧时延）、`test_e2e_stream.py`（Playwright 浏览器级）。

### 课堂预录制（course.py）
教师按大纲生成多讲课程：每讲一次 LLM 调用产出 events（与 M5 demo 同格式），**不预合成音频**；落地 `data/teachers/{tid}/courses/{cid}/course.json` + `{chapter_id}/events.json`。学生端 `CoursePlayer.jsx` 嵌 `/runtime/` iframe（stream 模式）实时合成。注意：前端 `src/mock/courses.js` 的预置蓝图课程（引用 `DEMO_L1/L2/L3` events）与真实课程**并存**于目录页，改课程逻辑时分清两条数据来源。

### 推荐-反馈-Skill 自进化闭环（textual gradient）
学生反馈驱动风格标签与 skill 描述迭代更新，链路：`/api/v1/match` 落盘推荐事件（`data/match_log/{YYYYMM}/{match_id}.json`，不可变无锁）→ 前端 api.js 用 sessionStorage 把 match_id 随 30 分钟内的评价自动回传 → `feedback.py` 服务端校验后快照 `match_context` 进评价条目 → 未处理反馈 ≥5 条（`EVOLUTION_REFRESH_THRESHOLD`）自动触发 daemon 线程进化。

- **进化器** `modules/M2_distill/tag_evolver/`（纯函数，不做 IO 不 import 下游）：`refresh_crowd_tags` 让 LLM 先对每条反馈**归因**（teaching_quality/platform 类差评不产生标签梯度），再给现有标签 confirm/contradict 信号、提新标签；**confidence 数值一律由确定性公式算，不采 LLM 给值**；新标签须 ≥2 名不同学生（student_hash 去重）支持才晋升，单人入候补池跨批累积。`propose_skill_revision` 只允许改 TeacherSkill.md 的 Teaching Philosophy / Explanation Pattern / Speech Policy 三段（Output Contract 等代码层禁改）。改逻辑必须跑 `tag_evolver/test_evolver.py`。
- **编排** `M6 backend/evolution.py`（全部 IO+锁，evolution API 6 条路由）：众评标签落 `data/teachers/{tid}/style_tags_live.json`（严格按 `style_tags_live.schema.json`，crowd 标签**永不进** skill_profile——M2 H14）；游标/校准/候补池/审计在 `data/teachers/{tid}/evolution/`。**skill 修订是教师确认制**：信号积累够 → 教师 Dashboard"生成修订"→ pending_revision diff → 确认才落 `skills/v{n+1}/`（H12 旧版本目录只读不动，confirm 后 calibration 清零）。
- **消费**：M3 `matcher.py` prompt 区分"蒸馏标签 vs 学生众评标签(N 名)"，H9 防幻觉集合 = auto ∪ crowd；`teachers.py` 给 card 附 `live_tags`；前端 TeacherProfile 蓝色众评 chip、VirtualClassroom 讲课结束浮出课后评价条（带 session_id）。
- 验收脚本：`scripts/test_evolution_e2e.py`（闭环 HTTP 冒烟，需后端运行）、`scripts/test_evolution_promote.py`（标签晋升）、`scripts/test_revision_sandbox.py`（修订流程，用沙箱副本教师，跑完需清理）。

## 子模块专属指令

- `modules/M1_ingest/asr_pipeline/CLAUDE.md` — ASR 引擎降级策略、防幻觉参数（`condition_on_previous_text=False` 等）、三层 config 体系。修改 ASR 必读，其中的硬性约束（禁改函数签名、热词配置）不可妥协。

## Legacy 与迁移

仓库 2026-05 从单 Skill demo（v1）重构为 6 模块多租户平台（v2）。`MIGRATION.md` 记录 v1→v2 路径映射；示例老师 v0 demo 数据迁至 `data/teachers/T_legacy_001/`，可用于 M2 回归测试与基线对比。`scripts/run_demo_pipeline.py` 是 v1 遗留、未更新为 v2 路径。

其它非运行代码目录：`edu-twin/` 是静态 HTML 高保真 UI 原型（设计稿，不参与运行）；`Web/` 是早期 Web 应用残骸（只剩 `node_modules` / `__pycache__`，源码已删）；M6 前端的 `VideoManagePage` / `VideoWatchPage` 文件保留但已从路由移除（被课程功能取代）。
