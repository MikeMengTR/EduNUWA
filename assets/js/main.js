/* EduNUWA 展示页交互：i18n / 星系视差与火星 / 产品画廊 / 灯箱 */
(function () {
  "use strict";

  /* ============ i18n ============ */
  const HTML_KEYS = new Set(["hero.headline"]);

  const I18N = {
    zh: {
      "nav.what": "它做什么", "nav.pipeline": "链路", "nav.product": "产品", "nav.demos": "演示", "nav.start": "上手",
      "hero.kicker": "EDUNUWA · 开源研究原型",
      "hero.headline": '<span class="ln">把教师的教学能力，</span><span class="ln"><em class="ignite">蒸馏</em>为数字资产<span class="dot">。</span></span>',
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
      ]
    },
    en: {
      "nav.what": "What", "nav.pipeline": "Pipeline", "nav.product": "Product", "nav.demos": "Demos", "nav.start": "Get Started",
      "hero.kicker": "EDUNUWA · OPEN-SOURCE RESEARCH PROTOTYPE",
      "hero.headline": '<span class="ln"><em class="ignite">Distilling</em> teaching ability</span><span class="ln">into digital assets<span class="dot">.</span></span>',
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
      ]
    }
  };

  let lang = localStorage.getItem("edunuwa-lang") || "zh";

  function applyLang() {
    const dict = I18N[lang];
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
    document.querySelectorAll("[data-i18n]").forEach(el => {
      const key = el.getAttribute("data-i18n");
      if (dict[key] !== undefined) el.textContent = dict[key];
    });
    const headline = document.getElementById("headline");
    if (headline) headline.innerHTML = dict["hero.headline"];
    document.getElementById("langToggle").textContent = lang === "zh" ? "EN" : "中";
    document.title = lang === "zh"
      ? "EduNUWA — 把教学能力蒸馏为数字资产"
      : "EduNUWA — Distilling Teaching Ability into Digital Assets";
    buildGallery();
  }

  document.getElementById("langToggle").addEventListener("click", () => {
    lang = lang === "zh" ? "en" : "zh";
    localStorage.setItem("edunuwa-lang", lang);
    applyLang();
  });

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

  /* ============ 讲义星系：火星 + 视差 ============ */
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const sparksBox = document.getElementById("sparks");
  if (sparksBox && !reduceMotion) {
    for (let i = 0; i < 16; i++) {
      const s = document.createElement("i");
      s.className = "spark";
      s.style.left = (4 + Math.random() * 92) + "%";
      s.style.top = (35 + Math.random() * 60) + "%";
      s.style.animationDuration = (5 + Math.random() * 7) + "s";
      s.style.animationDelay = (-Math.random() * 10) + "s";
      sparksBox.appendChild(s);
    }
  }

  const hero = document.querySelector(".hero");
  const stage = document.getElementById("heroStage");
  if (hero && stage && !reduceMotion) {
    let tx = 0, ty = 0, x = 0, y = 0;
    hero.addEventListener("mousemove", e => {
      const r = hero.getBoundingClientRect();
      tx = ((e.clientX - r.left) / r.width - 0.5) * -26;
      ty = ((e.clientY - r.top) / r.height - 0.5) * -26;
    });
    hero.addEventListener("mouseleave", () => { tx = 0; ty = 0; });
    (function loop() {
      x += (tx - x) * 0.06; y += (ty - y) * 0.06;
      stage.style.transform = "translate(" + x.toFixed(2) + "px," + y.toFixed(2) + "px)";
      requestAnimationFrame(loop);
    })();
  }

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
