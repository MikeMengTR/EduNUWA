/* EduNUWA 展示页交互：i18n / 打字机 / 滚动浮现 / 灯箱 / 粉笔尘 */
(function () {
  "use strict";

  /* ============ i18n ============ */
  const I18N = {
    zh: {
      "nav.what": "它做什么", "nav.pipeline": "链路", "nav.demos": "演示", "nav.features": "特性", "nav.start": "上手",
      "hero.kicker": "AI × 教育 · 研究原型",
      "hero.desc": "学生提出问题，数字教师以真实教师的讲解风格作答——克隆音色开口讲课，虚拟黑板逐句写下提纲、公式与插图，边生成边播放。",
      "hero.watch": "▶ 观看演示",
      "stats.modules": "模块流水线", "stats.events": "类教学事件", "stats.teachers": "位示例教师",
      "stats.streamNum": "秒级", "stats.stream": "首句开口延迟",
      "what.no": "一、", "what.title": "它做什么",
      "what.c1.t": "蒸馏讲解风格",
      "what.c1.p": "从授课视频中提炼教师「怎么讲」：如何引入概念、建立直觉、设计板书、主动防错——产出七段契约的 TeacherSkill，而不只是知识问答。",
      "what.c2.t": "流式虚拟课堂",
      "what.c2.p": "LLM 流式产出教学事件，TTS 逐句合成并预取下一句：首句开口 ≈ 首句生成 + 首句合成。黑板、公式、插图与语音同步推进。",
      "what.c3.t": "反馈自进化",
      "what.c3.p": "学生评价通过「文本梯度」回流：众评风格标签按确定性公式累积置信度，Skill 修订经教师确认后生效——数字分身越用越像。",
      "pipe.no": "二、", "pipe.title": "一条数据契约驱动的流水线",
      "pipe.lead": "六个模块通过「文件路径 + 函数调用」解耦，每个交接文件都有入库的 JSON Schema。",
      "pipe.m1": "摄取 · ASR 转写", "pipe.m2": "蒸馏 · TeacherSkill", "pipe.m3": "目录 · 双轨发现",
      "pipe.q": "学生提问", "pipe.m4": "编排 · 教学事件", "pipe.m5": "运行时 · TTS + 黑板", "pipe.live": "流式课堂",
      "pipe.m6": "平台层把 M1–M5 缝合成完整产品（Flask + React）",
      "pipe.events": "教学事件类型：",
      "demo.no": "三、", "demo.title": "现场演示",
      "demo.lead": "下面是系统真实运行录屏：从教师上传素材，到风格蒸馏，再到学生在虚拟课堂里提问听课。",
      "demo.feat.t": "虚拟课堂 · 「什么是高斯分布？」",
      "demo.feat.p": "克隆音色开口讲课，黑板逐句写下推导与图示——全程流式生成，无预录音频。",
      "demo.v1.t": "素材上传", "demo.v1.p": "教师上传授课视频，系统自动切分与登记",
      "demo.v2.t": "文字稿处理", "demo.v2.p": "ASR 转写 + LLM 精修，产出可蒸馏的文字稿",
      "demo.v3.t": "风格蒸馏", "demo.v3.p": "从转写中提炼 TeacherSkill 七段契约",
      "demo.v4.t": "蒸馏结果", "demo.v4.p": "风格指纹、教学法策略与质量评估",
      "demo.v5.t": "PPT 抽图入库", "demo.v5.p": "拖入课件，视觉模型筛图并自动标注检索元数据",
      "demo.v6.t": "虚拟课堂 · 讲解电容", "demo.v6.p": "物理课示例：公式、图示与语音同步推进",
      "feat.no": "四、", "feat.title": "核心特性",
      "feat.f1.t": "✍ 七段 Skill 契约",
      "feat.f1.p": "教学理念 / 讲解模式 / 板书策略 / 语言风格……蒸馏产物是结构化契约，直接注入每一次讲课的 prompt。",
      "feat.f2.t": "⚡ 全链路流式",
      "feat.f2.p": "SSE 事件流 + 逐句 TTS 预取 + 双槽 iframe 推流，不等全文生成，开口即讲。",
      "feat.f3.t": "🎙 音色克隆与降级",
      "feat.f3.p": "GPT-SoVITS 少样本克隆教师音色；无 GPU / 无模型时自动降级 edge-tts，普通笔记本可跑。",
      "feat.f4.t": "🖼 教学插图检索",
      "feat.f4.p": "图库检索 → LLM 按 ID 引用 → 防幻觉闸门定稿 URL，配图零额外首句延迟。",
      "feat.f5.t": "🔍 双轨教师发现",
      "feat.f5.p": "按姓名找名师，或按风格指纹匹配「适合你的讲法」——同时承载名师效应与长尾发现。",
      "feat.f6.t": "📈 众评标签进化",
      "feat.f6.p": "推荐 → 反馈 → 归因 → 标签晋升的完整闭环；置信度由确定性公式计算，不采 LLM 拍脑袋。",
      "start.no": "五、", "start.title": "五分钟跑起来", "start.copy": "复制",
      "start.note": "仓库内置 12 位匿名化示例教师与自制教学图库，无重型模型也能体验完整链路（TTS 自动走 edge-tts）。",
      "start.star": "★ 去 GitHub 点个 Star",
      "footer.lic": "MIT 开源",
      "footer.ethics": "示例数据已匿名化；如需摄取真实课程，请先取得教师本人授权。",
      "_type": ["把教师的教学能力，蒸馏为数字资产。", "让 AI 教师，真正「像那位老师」。", "开口即讲，边生成边板书。"]
    },
    en: {
      "nav.what": "What", "nav.pipeline": "Pipeline", "nav.demos": "Demos", "nav.features": "Features", "nav.start": "Get Started",
      "hero.kicker": "AI × Education · Research Prototype",
      "hero.desc": "A student asks a question; a digital teacher answers in a real teacher's explanatory style — speaking with a cloned voice while writing notes, formulas and figures on a virtual blackboard, streamed sentence by sentence.",
      "hero.watch": "▶ Watch Demos",
      "stats.modules": "module pipeline", "stats.events": "teaching event types", "stats.teachers": "demo teachers",
      "stats.streamNum": "~sec", "stats.stream": "first-utterance latency",
      "what.no": "I. ", "what.title": "What it does",
      "what.c1.t": "Distill teaching style",
      "what.c1.p": "Extracts HOW a teacher teaches from lecture videos — concept entry, intuition building, blackboard design, misconception alerts — into a seven-section TeacherSkill contract, not just Q&A.",
      "what.c2.t": "Streaming classroom",
      "what.c2.p": "The LLM streams teaching events while TTS synthesizes sentence-by-sentence with prefetch: first utterance ≈ first sentence generated + synthesized. Board, formulas and voice advance together.",
      "what.c3.t": "Feedback-driven evolution",
      "what.c3.p": "Student feedback flows back as a textual gradient: crowd style tags accumulate via deterministic confidence formulas, and skill revisions apply only after teacher confirmation.",
      "pipe.no": "II. ", "pipe.title": "A data-contract-driven pipeline",
      "pipe.lead": "Six modules decoupled by file paths + function calls; every hand-off file has a JSON Schema checked into the repo.",
      "pipe.m1": "Ingest · ASR", "pipe.m2": "Distill · TeacherSkill", "pipe.m3": "Catalog · discovery",
      "pipe.q": "Student question", "pipe.m4": "Orchestrate · events", "pipe.m5": "Runtime · TTS + board", "pipe.live": "Live classroom",
      "pipe.m6": "The platform layer (M6) stitches M1–M5 into a product (Flask + React)",
      "pipe.events": "Teaching event types:",
      "demo.no": "III. ", "demo.title": "Live demos",
      "demo.lead": "Real screen recordings: from uploading lecture material, through style distillation, to a student asking questions in the virtual classroom.",
      "demo.feat.t": "Virtual classroom · \"What is a Gaussian distribution?\"",
      "demo.feat.p": "Cloned voice lecturing while the board writes derivations and figures — fully streamed, no pre-recorded audio.",
      "demo.v1.t": "Upload material", "demo.v1.p": "Teacher uploads lecture videos; automatic slicing & registration",
      "demo.v2.t": "Transcript refinement", "demo.v2.p": "ASR transcription + LLM refinement into distillable text",
      "demo.v3.t": "Style distillation", "demo.v3.p": "Extracting the seven-section TeacherSkill contract",
      "demo.v4.t": "Distillation result", "demo.v4.p": "Style fingerprint, pedagogy strategy & quality grading",
      "demo.v5.t": "PPT figure extraction", "demo.v5.p": "Drop in slides; a vision model filters & auto-annotates figures",
      "demo.v6.t": "Virtual classroom · Capacitors", "demo.v6.p": "Physics example: formulas, figures and voice in sync",
      "feat.no": "IV. ", "feat.title": "Core features",
      "feat.f1.t": "✍ Seven-section Skill contract",
      "feat.f1.p": "Teaching philosophy / explanation pattern / blackboard policy / speech policy… a structured contract injected into every lesson prompt.",
      "feat.f2.t": "⚡ Fully streaming",
      "feat.f2.p": "SSE event stream + per-sentence TTS prefetch + dual-slot iframes — teaching starts before the full answer exists.",
      "feat.f3.t": "🎙 Voice cloning with fallback",
      "feat.f3.p": "GPT-SoVITS few-shot voice cloning per teacher; automatically falls back to edge-tts without a GPU or model — runs on a plain laptop.",
      "feat.f4.t": "🖼 Teaching-figure retrieval",
      "feat.f4.p": "Library retrieval → LLM cites by ID → anti-hallucination gate finalizes URLs. Zero added first-utterance latency.",
      "feat.f5.t": "🔍 Dual-track discovery",
      "feat.f5.p": "Find teachers by name, or match by style fingerprint — serving both star teachers and the long tail.",
      "feat.f6.t": "📈 Crowd-tag evolution",
      "feat.f6.p": "A full loop of recommend → feedback → attribution → tag promotion; confidence comes from deterministic formulas, never LLM guesses.",
      "start.no": "V. ", "start.title": "Run it in five minutes", "start.copy": "Copy",
      "start.note": "Ships with 12 anonymized demo teachers and an original figure library — the full pipeline works without heavy models (TTS falls back to edge-tts).",
      "start.star": "★ Star it on GitHub",
      "footer.lic": "MIT licensed",
      "footer.ethics": "Demo data is anonymized. Obtain a teacher's consent before ingesting real lectures.",
      "_type": ["Distill teaching ability into digital assets.", "An AI teacher that truly teaches like them.", "Speaks instantly — writing the board as it thinks."]
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
    document.getElementById("langToggle").textContent = lang === "zh" ? "EN" : "中";
    document.title = lang === "zh"
      ? "EduNUWA — 把教学能力蒸馏为数字资产"
      : "EduNUWA — Distilling Teaching Ability into Digital Assets";
    restartTypewriter();
  }

  document.getElementById("langToggle").addEventListener("click", () => {
    lang = lang === "zh" ? "en" : "zh";
    localStorage.setItem("edunuwa-lang", lang);
    applyLang();
  });

  /* ============ 打字机 ============ */
  const twEl = document.getElementById("typewriter");
  let twTimer = null;

  function restartTypewriter() {
    if (twTimer) clearTimeout(twTimer);
    const phrases = I18N[lang]._type;
    let pi = 0, ci = 0, deleting = false;

    function tick() {
      const phrase = phrases[pi];
      if (!deleting) {
        ci++;
        twEl.textContent = phrase.slice(0, ci);
        if (ci >= phrase.length) { deleting = true; twTimer = setTimeout(tick, 2200); return; }
        twTimer = setTimeout(tick, 90 + Math.random() * 70);
      } else {
        ci--;
        twEl.textContent = phrase.slice(0, ci);
        if (ci <= 0) { deleting = false; pi = (pi + 1) % phrases.length; twTimer = setTimeout(tick, 500); return; }
        twTimer = setTimeout(tick, 32);
      }
    }
    twEl.textContent = "";
    tick();
  }

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
      const src = card.getAttribute("data-video");
      lbVideo.src = src;
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
        const old = btn.textContent;
        btn.textContent = lang === "zh" ? "已复制 ✓" : "Copied ✓";
        setTimeout(() => { btn.textContent = I18N[lang]["start.copy"]; }, 1600);
      });
    });
  });

  /* ============ 粉笔尘粒子 ============ */
  const canvas = document.getElementById("dust");
  const ctx = canvas.getContext("2d");
  let particles = [];
  const MAX_P = 90;

  function resize() { canvas.width = innerWidth; canvas.height = innerHeight; }
  resize();
  addEventListener("resize", resize);

  function spawn(x, y, n) {
    for (let i = 0; i < n && particles.length < MAX_P; i++) {
      particles.push({
        x, y,
        vx: (Math.random() - 0.5) * 1.2,
        vy: Math.random() * 0.8 + 0.15,
        r: Math.random() * 2.2 + 0.6,
        life: 1
      });
    }
  }

  let lastMove = 0;
  addEventListener("mousemove", e => {
    const now = performance.now();
    if (now - lastMove > 40) { spawn(e.clientX, e.clientY, 2); lastMove = now; }
  });

  // 环境飘尘
  setInterval(() => {
    if (document.hidden) return;
    spawn(Math.random() * canvas.width, Math.random() * canvas.height * 0.5, 1);
  }, 700);

  (function loop() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    particles = particles.filter(p => p.life > 0.02);
    for (const p of particles) {
      p.x += p.vx; p.y += p.vy; p.life *= 0.975;
      ctx.globalAlpha = p.life * 0.35;
      ctx.fillStyle = "#f2efe6";
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    requestAnimationFrame(loop);
  })();

  /* ============ 管线描边动画（进入视口触发） ============ */
  const pipeBox = document.getElementById("pipelineBox");
  if (pipeBox) {
    const io2 = new IntersectionObserver(es => {
      es.forEach(e => { if (e.isIntersecting) { pipeBox.classList.add("on"); io2.unobserve(pipeBox); } });
    }, { threshold: 0.3 });
    io2.observe(pipeBox);
  }

  applyLang();
})();
