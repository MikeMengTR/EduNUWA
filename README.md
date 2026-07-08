# EduNUWA

**Distill a teacher's teaching style into a reusable digital asset — then let students learn from an AI teacher that actually teaches like them.**

[中文文档 →](README_zh.md)

EduNUWA is a research prototype that turns recorded lectures into a structured, callable "TeacherSkill", and uses it to drive a streaming virtual classroom: a student asks a question, and a digital teacher answers **in that teacher's explanatory style** — speaking with a cloned (or synthetic) voice while writing structured notes, formulas and figures on a virtual blackboard, sentence by sentence, in real time.

> This project focuses on the **structured extraction and transfer of teaching thought patterns** — how a teacher introduces concepts, builds intuition, designs blackboard layouts and warns about misconceptions. It is not about replicating a real teacher's identity.

## How it works

The system is a data-contract-driven pipeline of six modules, decoupled by file paths + Python function calls (no internal HTTP between modules):

```
Teacher lecture video/audio
  → M1 Ingest      ASR transcription            → teacher_transcript.json
  → M2 Distill     style distillation           → TeacherSkill.md + skill_profile.json + quality grade
  → M3 Catalog     dual-track teacher discovery (by name / by style)

Student question
  → M4 Orchestrator  teaching-event generation  → teaching_events.json
                     (speak / board / formula / table / pause / quiz / image)
  → stream           pacing layer: schedules events to a natural teaching rhythm
  → M5 Runtime       streaming TTS + blackboard/avatar frontend
  → M6 Platform      the web app that stitches M1–M5 together (Flask + React)
```

Key design decisions:

- **Data contracts as the single source of truth** — every cross-module file (`teaching_events.json`, `playback_data.json`, …) has a JSON schema checked into the repo.
- **Fully streaming classroom** — first-utterance latency ≈ first sentence generation + first sentence TTS. The LLM streams teaching events, TTS synthesizes sentence-by-sentence with prefetch, and the frontend plays while the rest is still being generated.
- **Style, not just content** — M2 produces a seven-section `TeacherSkill.md` (teaching philosophy, explanation pattern, blackboard policy, speech policy, …) that the orchestrator injects into every lesson prompt.
- **Feedback-driven skill evolution** — student feedback flows back through a "textual gradient" loop: crowd style tags accumulate with deterministic confidence formulas, and skill revisions require explicit teacher confirmation.
- **Graceful degradation** — no GPU / no voice model? TTS falls back to edge-tts. No vision API key? Image annotation falls back to text. The demo runs on a plain laptop.

## Quick start

Prerequisites: Python 3.10+, Node.js 18+, ffmpeg (for edge-tts WAV conversion).

```bash
# 1. Python deps (a conda env is recommended; heavy ASR/TTS deps are optional for the demo)
pip install -r requirements.txt
pip install -r modules/M6_platform/backend/requirements.txt

# 2. Configure
cp .env.example .env       # fill in DEEPSEEK_API_KEY (required)

# 3. Backend (Flask, port 5000)
python modules/M6_platform/backend/app.py

# 4. Frontend (Vite + React, port 3000)
cd modules/M6_platform/frontend
npm install
npm run dev
```

Open `http://localhost:3000`, register a student account, pick a demo teacher and ask a question in the virtual classroom.

On Windows, `modules\M6_platform\start.bat` does steps 3–4 in one shot (edit the Python path inside to match your environment).

### Optional heavy components

| Component | Needed for | Without it |
|---|---|---|
| faster-whisper / FunASR | Ingesting your own lecture videos (M1) | Use the bundled demo transcripts |
| GPT-SoVITS + voice models | Per-teacher voice cloning | Automatic fallback to edge-tts |
| DASHSCOPE_API_KEY (Qwen-VL) | AI image annotation, PPT figure extraction | Text-only annotation fallback |

## Repository map

| Path | What it is |
|---|---|
| `modules/M1_ingest/` | Video/audio → transcript (ASR pipeline with hallucination guards) |
| `modules/M2_distill/` | Transcript → TeacherSkill.md + style profile + quality grade; tag evolver |
| `modules/M3_catalog/` | Teacher discovery & matching (LLM ranking) |
| `modules/M4_orchestrator/` | Question + skill → teaching events |
| `modules/stream/` | Teaching-rhythm pacing layer between M4 and M5 |
| `modules/M5_runtime/` | TTS service, streaming player, blackboard/avatar frontend |
| `modules/M6_platform/` | Flask backend + React frontend (accounts, classroom, courses, image library, admin console) |
| `docs/` | Architecture & per-module design docs, API contract |
| `data/` | Multi-tenant data layout (anonymized demo teachers included) |
| `scripts/` | Teaching-figure generation, voice training, e2e test scripts |

Core data contracts are documented in [`docs/api_contract.md`](docs/api_contract.md); per-module design docs live in [`docs/modules/`](docs/modules/). Note that module docs describe the target architecture — where they disagree with the code, the code wins (see `CLAUDE.md` for the honest map).

## Demo data & ethics

- The bundled teachers under `data/teachers/` are **anonymized samples** (pseudonymous names, no voice models) so the pipeline runs out of the box.
- If you ingest real lectures: obtain the teacher's consent first, especially before training a voice clone. The TTS service is designed so that voice models never leave the local machine and are never committed to git.

## License

[MIT](LICENSE). Third-party components are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) — notably a vendored copy of [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) (MIT) for local voice cloning.
