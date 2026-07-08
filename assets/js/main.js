/* EduNUWA 展示页交互：i18n / 虚拟课堂 hero（粉笔标题 + 对话循环 + 黑板作图）/ 产品画廊 / 灯箱 */
(function () {
  "use strict";

  /* ============ i18n ============ */
  const I18N = {
    zh: {
      "nav.what": "它做什么", "nav.pipeline": "链路", "nav.product": "产品", "nav.demos": "演示", "nav.start": "上手",
      "hero.kicker": "EDUNUWA · 开源研究原型",
      "hero.desc": "学生提出问题，数字教师以真实教师的讲解风格作答——克隆音色开口讲课，虚拟黑板逐句写下提纲、公式与插图，边生成边播放。",
      "hero.watch": "看看产品",
      "stats.modules": "模块流水线", "stats.events": "类教学事件", "stats.teachers": "位示例教师",
      "stats.streamNum": "秒级", "stats.stream": "首句开口延迟",
      "what.kicker": "WHAT IT DOES", "what.title": "它做什么",
      "what.c1.t": "蒸馏讲解风格",
      "what.c1.p": "从授课视频中提炼教师「怎么讲」：如何引入概念、建立直觉、设计板书、主动防错——产出七段契约的 TeacherSkill，而不只是知识问答。",
      "what.c2.t": "流式虚拟课堂",
      "what.c2.p": "LLM 流式产出教学事件，TTS 逐句合成并预取下一句：首句开口 ≈ 首句生成 + 首句合成。黑板、公式、插图与语音同步推进。",
      "what.c3.t": "反馈自进化",
      "what.c3.p": "学生评价通过「文本梯度」回流：众评风格标签按确定性公式累积置信度，Skill 修订经教师确认后生效——数字分身越用越像。",
      "pipe.kicker": "PIPELINE", "pipe.title": "一条数据契约驱动的流水线",
      "pipe.lead": "六个模块通过「文件路径 + 函数调用」解耦，每个交接文件都有入库的 JSON Schema。",
      "pipe.m1": "摄取 · ASR 转写", "pipe.m2": "蒸馏 · TeacherSkill", "pipe.m3": "目录 · 双轨发现",
      "pipe.q": "学生提问", "pipe.m4": "编排 · 教学事件", "pipe.m5": "运行时 · TTS + 黑板", "pipe.live": "流式课堂",
      "pipe.m6": "平台层把 M1–M5 缝合成完整产品（Flask + React）",
      "pipe.events": "教学事件类型",
      "prod.kicker": "THE PRODUCT", "prod.title": "走进讲义馆",
      "prod.lead": "从登录到课堂的完整产品体验——温暖纸质的设计语言，承载一条严肃的技术链路。",
      "demo.kicker": "LIVE DEMOS", "demo.title": "现场演示",
      "demo.lead": "系统真实运行录屏：从教师上传素材，到风格蒸馏，再到学生在虚拟课堂里提问听课。",
      "demo.feat.t": "虚拟课堂 · 「什么是高斯分布？」",
      "demo.feat.p": "克隆音色开口讲课，黑板逐句写下推导与图示——全程流式生成，无预录音频。",
      "demo.v1.t": "素材上传", "demo.v1.p": "教师上传授课视频，系统自动切分与登记",
      "demo.v2.t": "文字稿处理", "demo.v2.p": "ASR 转写 + LLM 精修，产出可蒸馏的文字稿",
      "demo.v3.t": "风格蒸馏", "demo.v3.p": "从转写中提炼 TeacherSkill 七段契约",
      "demo.v4.t": "蒸馏结果", "demo.v4.p": "风格指纹、教学法策略与质量评估",
      "demo.v5.t": "PPT 抽图入库", "demo.v5.p": "拖入课件，视觉模型筛图并自动标注检索元数据",
      "demo.v6.t": "虚拟课堂 · 讲解电容", "demo.v6.p": "物理课示例：公式、图示与语音同步推进",
      "feat.kicker": "CORE FEATURES", "feat.title": "核心特性",
      "feat.f1.t": "七段 Skill 契约",
      "feat.f1.p": "教学理念 / 讲解模式 / 板书策略 / 语言风格……蒸馏产物是结构化契约，直接注入每一次讲课的 prompt。",
      "feat.f2.t": "全链路流式",
      "feat.f2.p": "SSE 事件流 + 逐句 TTS 预取 + 双槽 iframe 推流，不等全文生成，开口即讲。",
      "feat.f3.t": "音色克隆与降级",
      "feat.f3.p": "GPT-SoVITS 少样本克隆教师音色；无 GPU / 无模型时自动降级 edge-tts，普通笔记本可跑。",
      "feat.f4.t": "教学插图检索",
      "feat.f4.p": "图库检索 → LLM 按 ID 引用 → 防幻觉闸门定稿 URL，配图零额外首句延迟。",
      "feat.f5.t": "双轨教师发现",
      "feat.f5.p": "按姓名找名师，或按风格指纹匹配「适合你的讲法」——同时承载名师效应与长尾发现。",
      "feat.f6.t": "众评标签进化",
      "feat.f6.p": "推荐 → 反馈 → 归因 → 标签晋升的完整闭环；置信度由确定性公式计算，不采 LLM 拍脑袋。",
      "start.kicker": "GET STARTED", "start.title": "五分钟跑起来", "start.copy": "复制",
      "start.note": "仓库内置 12 位匿名化示例教师与自制教学图库，无重型模型也能体验完整链路（TTS 自动走 edge-tts）。",
      "start.star": "去 GitHub 点个 Star",
      "footer.lic": "MIT 开源",
      "footer.ethics": "示例数据已匿名化；如需摄取真实课程，请先取得教师本人授权。",
      "_gallery": [
        { img: "m6-login",        url: "edutwin.local / login",           t: "登录 · 讲义星系",         d: "深咖啡宇宙里的知识轨道，一句「蒸馏为数字资产」点燃入口。" },
        { img: "m6-discover",     url: "edutwin.local / student",         t: "学生端 · 发现你的老师",   d: "用一句话描述想要的讲课风格，AI 按贴合度排出最合适的人选。" },
        { img: "m6-profile",      url: "edutwin.local / teacher/T…001",   t: "教师详情 · 风格速写",     d: "蒸馏标签聚合成词云；设问自答、集合论类比——这位老师的讲法一目了然。" },
        { img: "m6-classroom",    url: "edutwin.local / classroom",       t: "虚拟课堂 · 数字人黑板",   d: "点一个问题，老师就上黑板讲：语音、板书、公式与插图流式同步。" },
        { img: "m6-courses",      url: "edutwin.local / courses",         t: "课程目录 · 自编排课程",   d: "按大纲自动编排的多讲课程，每讲实时以教师风格开讲。" },
        { img: "m6-teacher-dash", url: "edutwin.local / teacher",         t: "教师端 · 能力工作台",     d: "素材、文字库、风格 Skill、专属音色、课程与插图——从素材到分身的每一步。" },
        { img: "m6-skill",        url: "edutwin.local / teacher/skill",   t: "Skill 档案 · 风格指纹",   d: "六维风格指纹 + 可溯源标签 + 七段 TeacherSkill 契约，每条都有课堂引证。" },
        { img: "m6-imagelib",     url: "edutwin.local / teacher/images",  t: "教学插图库 · PPT 抽图",   d: "拖入 PPT 自动抽图，视觉模型判断是否适合教学并自动标注，讲课时按问题检索配图。" }
      ],
      "_cls": {
        headline: [
          { t: "把教师的教学能力，" }, { br: 1 },
          { t: "蒸馏", cls: "ignite" }, { t: "为数字资产" }, { t: "。", cls: "dot" }
        ],
        statusIdle: "待命中", statusLive: "开讲中",
        name: "示范教师 01", subject: "概率论", stageName: "示范教师 01 · 概率论",
        tagsLabel: "风 格 标 签", tagsMore: "展开全部 · 7",
        tags: ["设问自答", "实例驱动", "生活类比", "符号严谨", "结构总结"],
        hint: "输入问题，AI 将按这位老师的风格开讲",
        placeholder: "输入问题，试试让老师开讲…", send: "演示",
        scripts: [
          { q: "什么是高斯分布？", fig: "gauss", formula: "f(x) = e^-(x-μ)²/2σ² / √(2πσ²)",
            a: "同学们好！我们从掷骰子说起——把大量微小的随机误差叠加起来，一条优雅的钟形曲线就会浮现。它关于 x = μ 对称，中间高、两边低……",
            outline: "本节提纲 · 正态（高斯）分布" },
          { q: "勾股定理怎么证明？", fig: "pyth", formula: "a² + b² = c²",
            a: "别急着背公式，先画一个直角三角形。我们在三条边上各搭一个正方形，比一比面积——大正方形恰好等于两个小正方形之和。",
            outline: "本节提纲 · 勾股定理" },
          { q: "电容是什么？", fig: "cap", formula: "C = Q / U",
            a: "你可以把电容想象成一个「电荷的蓄水池」：两块平行板隔空相望，电压一推，电荷就在板上积蓄起来，需要时再放出去。",
            outline: "本节提纲 · 电容与电场" }
        ],
        custom: {
          a: "这个问题问得好！不过我只是着陆页上的示范分身——把仓库跑起来，真正的数字教师会开口讲课、逐句板书，认真回答你。",
          outline: "本节提纲 · 先把仓库跑起来 ↓"
        }
      }
    },
    en: {
      "nav.what": "What", "nav.pipeline": "Pipeline", "nav.product": "Product", "nav.demos": "Demos", "nav.start": "Get Started",
      "hero.kicker": "EDUNUWA · OPEN-SOURCE RESEARCH PROTOTYPE",
      "hero.desc": "A student asks a question; a digital teacher answers in a real teacher's explanatory style — speaking with a cloned voice while writing notes, formulas and figures on a virtual blackboard, streamed sentence by sentence.",
      "hero.watch": "See the product",
      "stats.modules": "module pipeline", "stats.events": "teaching event types", "stats.teachers": "demo teachers",
      "stats.streamNum": "~sec", "stats.stream": "first-utterance latency",
      "what.kicker": "WHAT IT DOES", "what.title": "What it does",
      "what.c1.t": "Distill teaching style",
      "what.c1.p": "Extracts HOW a teacher teaches from lecture videos — concept entry, intuition building, blackboard design, misconception alerts — into a seven-section TeacherSkill contract, not just Q&A.",
      "what.c2.t": "Streaming classroom",
      "what.c2.p": "The LLM streams teaching events while TTS synthesizes sentence-by-sentence with prefetch: first utterance ≈ first sentence generated + synthesized. Board, formulas and voice advance together.",
      "what.c3.t": "Feedback-driven evolution",
      "what.c3.p": "Student feedback flows back as a textual gradient: crowd style tags accumulate via deterministic confidence formulas, and skill revisions apply only after teacher confirmation.",
      "pipe.kicker": "PIPELINE", "pipe.title": "A data-contract-driven pipeline",
      "pipe.lead": "Six modules decoupled by file paths + function calls; every hand-off file has a JSON Schema checked into the repo.",
      "pipe.m1": "Ingest · ASR", "pipe.m2": "Distill · TeacherSkill", "pipe.m3": "Catalog · discovery",
      "pipe.q": "Student question", "pipe.m4": "Orchestrate · events", "pipe.m5": "Runtime · TTS + board", "pipe.live": "Live classroom",
      "pipe.m6": "The platform layer (M6) stitches M1–M5 into a product (Flask + React)",
      "pipe.events": "Teaching event types",
      "prod.kicker": "THE PRODUCT", "prod.title": "Step inside",
      "prod.lead": "The full product journey from login to classroom — a warm, paper-like design language carrying a serious technical pipeline.",
      "demo.kicker": "LIVE DEMOS", "demo.title": "Live demos",
      "demo.lead": "Real screen recordings: from uploading lecture material, through style distillation, to a student asking questions in the virtual classroom.",
      "demo.feat.t": "Virtual classroom · \"What is a Gaussian distribution?\"",
      "demo.feat.p": "Cloned voice lecturing while the board writes derivations and figures — fully streamed, no pre-recorded audio.",
      "demo.v1.t": "Upload material", "demo.v1.p": "Teacher uploads lecture videos; automatic slicing & registration",
      "demo.v2.t": "Transcript refinement", "demo.v2.p": "ASR transcription + LLM refinement into distillable text",
      "demo.v3.t": "Style distillation", "demo.v3.p": "Extracting the seven-section TeacherSkill contract",
      "demo.v4.t": "Distillation result", "demo.v4.p": "Style fingerprint, pedagogy strategy & quality grading",
      "demo.v5.t": "PPT figure extraction", "demo.v5.p": "Drop in slides; a vision model filters & auto-annotates figures",
      "demo.v6.t": "Virtual classroom · Capacitors", "demo.v6.p": "Physics example: formulas, figures and voice in sync",
      "feat.kicker": "CORE FEATURES", "feat.title": "Core features",
      "feat.f1.t": "Seven-section Skill contract",
      "feat.f1.p": "Teaching philosophy / explanation pattern / blackboard policy / speech policy… a structured contract injected into every lesson prompt.",
      "feat.f2.t": "Fully streaming",
      "feat.f2.p": "SSE event stream + per-sentence TTS prefetch + dual-slot iframes — teaching starts before the full answer exists.",
      "feat.f3.t": "Voice cloning with fallback",
      "feat.f3.p": "GPT-SoVITS few-shot voice cloning per teacher; automatically falls back to edge-tts without a GPU or model — runs on a plain laptop.",
      "feat.f4.t": "Teaching-figure retrieval",
      "feat.f4.p": "Library retrieval → LLM cites by ID → anti-hallucination gate finalizes URLs. Zero added first-utterance latency.",
      "feat.f5.t": "Dual-track discovery",
      "feat.f5.p": "Find teachers by name, or match by style fingerprint — serving both star teachers and the long tail.",
      "feat.f6.t": "Crowd-tag evolution",
      "feat.f6.p": "A full loop of recommend → feedback → attribution → tag promotion; confidence comes from deterministic formulas, never LLM guesses.",
      "start.kicker": "GET STARTED", "start.title": "Run it in five minutes", "start.copy": "Copy",
      "start.note": "Ships with 12 anonymized demo teachers and an original figure library — the full pipeline works without heavy models (TTS falls back to edge-tts).",
      "start.star": "Star it on GitHub",
      "footer.lic": "MIT licensed",
      "footer.ethics": "Demo data is anonymized. Obtain a teacher's consent before ingesting real lectures.",
      "_gallery": [
        { img: "m6-login",        url: "edutwin.local / login",           t: "Login · a galaxy of lecture notes", d: "Orbits of knowledge in a deep-coffee cosmos; one word — distill — ignites the entrance." },
        { img: "m6-discover",     url: "edutwin.local / student",         t: "Student · discover your teacher",   d: "Describe the teaching style you want in one sentence; AI ranks the best matches." },
        { img: "m6-profile",      url: "edutwin.local / teacher/T…001",   t: "Teacher profile · style sketch",    d: "Distilled tags gather into a word cloud — this teacher's way of explaining at a glance." },
        { img: "m6-classroom",    url: "edutwin.local / classroom",       t: "Virtual classroom · blackboard",    d: "Pick a question and the teacher walks to the board: voice, writing, formulas and figures, all streamed." },
        { img: "m6-courses",      url: "edutwin.local / courses",         t: "Course catalog · auto-arranged",    d: "Multi-lecture courses arranged from an outline, each delivered live in the teacher's style." },
        { img: "m6-teacher-dash", url: "edutwin.local / teacher",         t: "Teacher · capability workbench",    d: "Materials, transcripts, style Skill, personal voice, courses and figures — every step from footage to twin." },
        { img: "m6-skill",        url: "edutwin.local / teacher/skill",   t: "Skill archive · style fingerprint", d: "Six-dimension fingerprint + evidence-backed tags + the seven-section TeacherSkill contract." },
        { img: "m6-imagelib",     url: "edutwin.local / teacher/images",  t: "Figure library · PPT extraction",   d: "Drop in a PPT; a vision model filters teaching-worthy figures and annotates them for retrieval." }
      ],
      "_cls": {
        headline: [
          { t: "Distilling", cls: "ignite" }, { t: " teaching ability" }, { br: 1 },
          { t: "into digital assets" }, { t: ".", cls: "dot" }
        ],
        statusIdle: "Standing by", statusLive: "Teaching live",
        name: "Demo Teacher 01", subject: "Probability", stageName: "Demo Teacher 01 · Probability",
        tagsLabel: "S T Y L E   T A G S", tagsMore: "all · 7",
        tags: ["Socratic asks", "Example-driven", "Everyday analogies", "Rigorous notation", "Structured recaps"],
        hint: "Ask anything — the AI teaches in this teacher's style",
        placeholder: "Type a question, watch the teacher teach…", send: "Ask",
        scripts: [
          { q: "What is a Gaussian distribution?", fig: "gauss", formula: "f(x) = e^-(x-μ)²/2σ² / √(2πσ²)",
            a: "Great question! Start with dice: pile up many small random errors and an elegant bell curve emerges — symmetric about x = μ, high in the middle, low at both tails…",
            outline: "Outline · The normal distribution" },
          { q: "How do I prove the Pythagorean theorem?", fig: "pyth", formula: "a² + b² = c²",
            a: "Don't memorize it — draw a right triangle first. Build a square on each side and compare areas: the big one exactly equals the other two combined.",
            outline: "Outline · Pythagorean theorem" },
          { q: "What is a capacitor?", fig: "cap", formula: "C = Q / U",
            a: "Think of it as a reservoir for charge: two plates facing each other across a gap. Push a voltage, and charge piles up on the plates, ready to be released.",
            outline: "Outline · Capacitors & fields" }
        ],
        custom: {
          a: "Good question! I'm just the demo twin on this landing page — clone the repo and a real digital teacher will speak up, write on the board, and answer you properly.",
          outline: "Outline · Run the repo first ↓"
        }
      }
    }
  };

  let lang = localStorage.getItem("edunuwa-lang") || "zh";
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function applyLang() {
    const dict = I18N[lang];
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
    document.querySelectorAll("[data-i18n]").forEach(el => {
      const key = el.getAttribute("data-i18n");
      if (dict[key] !== undefined) el.textContent = dict[key];
    });
    document.getElementById("langToggle").textContent = lang === "zh" ? "EN" : "中";
    document.title = lang === "zh"
      ? "EduNUWA — 把教学能力蒸馏为数字资产"
      : "EduNUWA — Distilling Teaching Ability into Digital Assets";
    buildGallery();
    startClassroom();
  }

  document.getElementById("langToggle").addEventListener("click", () => {
    lang = lang === "zh" ? "en" : "zh";
    localStorage.setItem("edunuwa-lang", lang);
    applyLang();
  });

  /* ============ 虚拟课堂 hero ============ */
  const hero = document.querySelector(".hero");
  const headlineEl = document.getElementById("headline");
  const stageDot = document.getElementById("stageDot");
  const stageStatus = document.getElementById("stageStatus");
  const stageName = document.getElementById("stageName");
  const panelName = document.getElementById("panelName");
  const panelSubject = document.getElementById("panelSubject");
  const tagsLabel = document.getElementById("tagsLabel");
  const tagsMore = document.getElementById("tagsMore");
  const tagChips = document.getElementById("tagChips");
  const chatArea = document.getElementById("chatArea");
  const askChips = document.getElementById("askChips");
  const askForm = document.getElementById("askForm");
  const askInput = document.getElementById("askInput");
  const askBtn = document.getElementById("askBtn");
  const figFormula = document.getElementById("figFormula");
  const figs = document.querySelectorAll("#boardFigure .fig");

  let timers = [], typeIv = null;
  function later(fn, ms) { const id = setTimeout(fn, ms); timers.push(id); return id; }
  function stopClassroom() {
    timers.forEach(clearTimeout); timers = [];
    if (typeIv) { clearInterval(typeIv); typeIv = null; }
    hero.classList.remove("speaking");
    stageDot.classList.remove("live");
    // 若标题仍在书写，瞬间写完（用户提前交互时不留残句）
    headlineEl.querySelectorAll(".ch:not(.show)").forEach(s => s.classList.add("show"));
    headlineEl.querySelectorAll(".chalk-caret").forEach(s => s.remove());
    const em = headlineEl.querySelector(".ignite");
    if (em && headlineEl.querySelector(".ch")) em.classList.add("lit");
  }

  function C() { return I18N[lang]._cls; }

  /* --- 粉笔标题逐字书写 --- */
  function buildHeadline(done) {
    headlineEl.innerHTML = "";
    const chars = [];
    C().headline.forEach(seg => {
      if (seg.br) { headlineEl.appendChild(document.createElement("br")); return; }
      let parent = headlineEl;
      if (seg.cls) {
        parent = document.createElement(seg.cls === "ignite" ? "em" : "span");
        parent.className = seg.cls;
        headlineEl.appendChild(parent);
      }
      for (const ch of seg.t) {
        const s = document.createElement("span");
        s.className = "ch";
        // inline-block 会剥离首尾空白，空格须用 NBSP 占位
        s.textContent = ch === " " ? " " : ch;
        parent.appendChild(s);
        chars.push({ el: s, parent });
      }
    });
    const caret = document.createElement("span");
    caret.className = "chalk-caret";
    const finish = () => {
      caret.remove();
      const em = headlineEl.querySelector(".ignite");
      if (em) em.classList.add("lit");
      done && done();
    };
    if (reduceMotion) {
      chars.forEach(c => c.el.classList.add("show"));
      finish();
      return;
    }
    headlineEl.appendChild(caret);
    let i = 0;
    const speed = lang === "zh" ? 72 : 34;
    typeIv = setInterval(() => {
      if (i >= chars.length) { clearInterval(typeIv); typeIv = null; finish(); return; }
      const c = chars[i++];
      c.el.classList.add("show");
      c.el.after(caret);
    }, speed);
  }

  /* --- 黑板作图 --- */
  function showFigure(figKey, formula) {
    if (!figKey) return;
    figs.forEach(f => {
      const on = f.getAttribute("data-fig") === figKey;
      f.classList.toggle("on", on);
      f.classList.remove("draw");
      if (on) { void f.getBoundingClientRect(); f.classList.add("draw"); }
    });
    figFormula.classList.remove("show");
    figFormula.textContent = formula || "";
    void figFormula.offsetWidth;
    if (formula) figFormula.classList.add("show");
  }

  /* --- 对话气泡 --- */
  function addMsg(cls, text) {
    const div = document.createElement("div");
    div.className = "msg " + cls;
    const p = document.createElement("p");
    p.textContent = text;
    div.appendChild(p);
    chatArea.appendChild(div);
    chatArea.scrollTop = chatArea.scrollHeight;
    return div;
  }
  function addTyping() {
    const div = document.createElement("div");
    div.className = "msg msg--tea msg--typing";
    div.innerHTML = "<i></i><i></i><i></i>";
    chatArea.appendChild(div);
    chatArea.scrollTop = chatArea.scrollHeight;
    return div;
  }
  function addOutline(text) {
    const div = document.createElement("div");
    div.className = "mini-outline";
    div.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h10"/></svg>';
    div.appendChild(document.createTextNode(text));
    chatArea.appendChild(div);
    chatArea.scrollTop = chatArea.scrollHeight;
    return div;
  }
  function typeMsg(text, done) {
    const div = document.createElement("div");
    div.className = "msg msg--tea";
    const p = document.createElement("p");
    const node = document.createTextNode("");
    const caret = document.createElement("span");
    caret.className = "type-caret";
    p.appendChild(node); p.appendChild(caret);
    div.appendChild(p);
    chatArea.appendChild(div);
    if (reduceMotion) {
      node.nodeValue = text; caret.remove();
      chatArea.scrollTop = chatArea.scrollHeight;
      done && done(); return;
    }
    let i = 0;
    typeIv = setInterval(() => {
      if (i >= text.length) {
        clearInterval(typeIv); typeIv = null; caret.remove();
        done && done(); return;
      }
      node.nodeValue += text[i++];
      chatArea.scrollTop = chatArea.scrollHeight;
    }, lang === "zh" ? 46 : 22);
  }

  function setLive(on) {
    hero.classList.toggle("speaking", on);
    stageDot.classList.toggle("live", on);
    stageStatus.textContent = on ? C().statusLive : C().statusIdle;
  }

  /* --- 一次完整问答（脚本或自定义） --- */
  function playExchange(q, entry, next) {
    stopClassroom();
    chatArea.innerHTML = "";
    const hint = document.createElement("p");
    hint.className = "chat-hint";
    hint.textContent = C().hint;
    chatArea.appendChild(hint);

    addMsg("msg--stu", q);
    later(() => {
      const ty = addTyping();
      later(() => {
        ty.remove();
        setLive(true);
        if (entry.fig) showFigure(entry.fig, entry.formula);
        typeMsg(entry.a, () => {
          later(() => addOutline(entry.outline), 350);
          later(() => setLive(false), 900);
          later(next, 4600);
        });
      }, 1250);
    }, 550);
  }

  let scriptIdx = 0;
  function playLoop() {
    const s = C().scripts[scriptIdx % C().scripts.length];
    playExchange(s.q, s, () => { scriptIdx++; playLoop(); });
  }

  function buildPanel() {
    const c = C();
    stageStatus.textContent = c.statusIdle;
    stageName.textContent = c.stageName;
    panelName.textContent = c.name;
    panelSubject.textContent = c.subject;
    tagsLabel.textContent = c.tagsLabel;
    tagsMore.textContent = c.tagsMore;
    askInput.placeholder = c.placeholder;
    askBtn.textContent = c.send;
    tagChips.innerHTML = "";
    c.tags.forEach((t, i) => {
      const s = document.createElement("span");
      s.textContent = t;
      s.style.setProperty("--cd", (0.35 + i * 0.12) + "s");
      tagChips.appendChild(s);
    });
    askChips.innerHTML = "";
    c.scripts.forEach((sc, k) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "qchip";
      b.textContent = sc.q;
      b.addEventListener("click", () => {
        scriptIdx = k;
        playExchange(sc.q, sc, () => { scriptIdx++; playLoop(); });
      });
      askChips.appendChild(b);
    });
  }

  askForm.addEventListener("submit", e => {
    e.preventDefault();
    const text = askInput.value.trim();
    askInput.value = "";
    if (!text) {
      const s = C().scripts[scriptIdx % C().scripts.length];
      playExchange(s.q, s, () => { scriptIdx++; playLoop(); });
      return;
    }
    playExchange(text, C().custom, () => playLoop());
  });

  function startClassroom() {
    stopClassroom();
    buildPanel();
    figs.forEach(f => f.classList.remove("on", "draw"));
    figFormula.classList.remove("show");
    buildHeadline(() => later(playLoop, 500));
  }

  /* 粉笔尘埃 */
  const motesBox = document.getElementById("boardMotes");
  if (motesBox && !reduceMotion) {
    for (let i = 0; i < 14; i++) {
      const m = document.createElement("i");
      m.className = "mote";
      const sz = 1.5 + Math.random() * 2;
      m.style.width = m.style.height = sz + "px";
      m.style.left = (3 + Math.random() * 94) + "%";
      m.style.top = (30 + Math.random() * 65) + "%";
      m.style.animationDuration = (6 + Math.random() * 8) + "s";
      m.style.animationDelay = (-Math.random() * 12) + "s";
      motesBox.appendChild(m);
    }
  }

  /* 暖光视差 */
  const stageBg = document.getElementById("heroStage");
  if (hero && stageBg && !reduceMotion) {
    let tx = 0, ty = 0, x = 0, y = 0;
    hero.addEventListener("mousemove", e => {
      const r = hero.getBoundingClientRect();
      tx = ((e.clientX - r.left) / r.width - 0.5) * -22;
      ty = ((e.clientY - r.top) / r.height - 0.5) * -22;
    });
    hero.addEventListener("mouseleave", () => { tx = 0; ty = 0; });
    (function loop() {
      x += (tx - x) * 0.06; y += (ty - y) * 0.06;
      stageBg.style.transform = "translate(" + x.toFixed(2) + "px," + y.toFixed(2) + "px)";
      requestAnimationFrame(loop);
    })();
  }

  /* ============ 产品画廊 ============ */
  const galleryMain = document.getElementById("galleryMain");
  const galleryUrl = document.getElementById("galleryUrl");
  const galleryTitle = document.getElementById("galleryTitle");
  const galleryDesc = document.getElementById("galleryDesc");
  const thumbsBox = document.getElementById("thumbs");
  let gIndex = 0, gTimer = null;

  function showGallery(i, user) {
    const items = I18N[lang]._gallery;
    gIndex = (i + items.length) % items.length;
    const it = items[gIndex];
    galleryMain.classList.add("fading");
    setTimeout(() => {
      galleryMain.src = "assets/img/" + it.img + ".jpg";
      galleryMain.onload = () => galleryMain.classList.remove("fading");
    }, 180);
    galleryUrl.textContent = it.url;
    galleryTitle.textContent = it.t;
    galleryDesc.textContent = it.d;
    thumbsBox.querySelectorAll(".thumb").forEach((t, k) => t.classList.toggle("on", k === gIndex));
    if (user) restartAutoplay();
  }

  function buildGallery() {
    const items = I18N[lang]._gallery;
    thumbsBox.innerHTML = "";
    items.forEach((it, k) => {
      const b = document.createElement("button");
      b.className = "thumb" + (k === gIndex ? " on" : "");
      b.setAttribute("aria-label", it.t);
      const im = document.createElement("img");
      im.src = "assets/img/" + it.img + ".jpg";
      im.alt = "";
      im.loading = "lazy";
      b.appendChild(im);
      b.addEventListener("click", () => showGallery(k, true));
      thumbsBox.appendChild(b);
    });
    showGallery(gIndex, false);
  }

  function restartAutoplay() {
    if (gTimer) clearInterval(gTimer);
    gTimer = setInterval(() => showGallery(gIndex + 1, false), 7000);
  }
  restartAutoplay();

  /* ============ 滚动浮现 ============ */
  const io = new IntersectionObserver(entries => {
    entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add("on"); io.unobserve(e.target); } });
  }, { threshold: 0.15 });
  document.querySelectorAll(".reveal").forEach(el => io.observe(el));

  /* ============ 视频灯箱 ============ */
  const lb = document.getElementById("lightbox");
  const lbVideo = document.getElementById("lbVideo");
  document.querySelectorAll(".vcard").forEach(card => {
    card.addEventListener("click", () => {
      lbVideo.src = card.getAttribute("data-video");
      lbVideo.loop = card.hasAttribute("data-loop");
      lb.hidden = false;
      document.body.style.overflow = "hidden";
      lbVideo.play().catch(() => {});
    });
  });
  function closeLb() {
    lb.hidden = true;
    lbVideo.pause();
    lbVideo.removeAttribute("src");
    lbVideo.load();
    document.body.style.overflow = "";
  }
  document.getElementById("lbClose").addEventListener("click", closeLb);
  lb.addEventListener("click", e => { if (e.target === lb) closeLb(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !lb.hidden) closeLb(); });

  /* ============ 复制按钮 ============ */
  document.querySelectorAll(".copy-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const code = btn.parentElement.querySelector("code").innerText;
      navigator.clipboard.writeText(code).then(() => {
        btn.textContent = lang === "zh" ? "已复制 ✓" : "Copied ✓";
        setTimeout(() => { btn.textContent = I18N[lang]["start.copy"]; }, 1600);
      });
    });
  });

  /* ============ 管线描边动画 ============ */
  const pipeBox = document.getElementById("pipelineBox");
  if (pipeBox) {
    const io2 = new IntersectionObserver(es => {
      es.forEach(e => { if (e.isIntersecting) { pipeBox.classList.add("on"); io2.unobserve(pipeBox); } });
    }, { threshold: 0.3 });
    io2.observe(pipeBox);
  }

  applyLang();
})();
