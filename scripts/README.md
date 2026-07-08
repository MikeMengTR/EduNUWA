# scripts/ 脚本说明

本目录是 M2 评价/蒸馏 + M3 匹配的**工具与测试脚本**。核心业务代码在模块内
（`modules/M2_distill/metric_extractor/`、`modules/M2_distill/skill_distiller/`、
`modules/M3_catalog/matching_engine/`），这里是驱动它们的工具。

统一用项目 conda 环境运行：`D:/anaconda3/envs/edu/python.exe`。
中文输出建议加 `PYTHONIOENCODING=utf-8`（Windows 控制台默认 GBK 会乱码）。

---

## 数据准备

| 脚本 | 用途 |
|---|---|
| `migrate_teacher_data.py` | 把 `data/Teacher_data_new/`（M1 中转产物，中文 teacher_id）迁到规范位置 `data/teachers/{T_合规id}/`，修正 teacher_id 字段，生成 teacher_card |
| `check_teacher_data.py [dir]` | 检查一批教师数据是否符合 M1 契约 + 评价可用性（teacher_id 格式 / segment 字段 / manifest / wav 存在 / base_metrics 实算）|
| `gen_mock_teachers.py` | 造 6 个不同风格的 mock 老师 skill_profile（demo 用，落 `modules/M3_catalog/tests/fixtures/mock_teachers/`），全过 schema |

## 蒸馏（产 TeacherSkill.md + skill_profile）

| 脚本 | 用途 |
|---|---|
| `distill_all_full.py` | 对 6 位真实老师批量**完整蒸馏**（走 nuwa_distill → SKILL.md 7-phase agent），产出到各位 `skills/v2_full/`。串行，约 3-6 分钟/位 |
| `distill_demo.py` | 单位「真转写 → 评价 → 匹配」轻量闭环演示（base_metrics + style_tagger，非完整 agent 蒸馏）|

## 匹配 demo

| 脚本 | 用途 |
|---|---|
| `demo_match_real.py ["需求"]` | **真实闭环 demo**：加载 6 位完整蒸馏的老师，跑自然语言匹配，看精准召回 + 推荐理由 |
| `demo_match.py ["需求"]` | mock 数据匹配 demo（需先跑 `gen_mock_teachers.py`）|

## 测试 / 分析

| 脚本 | 用途 |
|---|---|
| `test_eval_system.py` | 评价系统验证：6 位蒸馏 + 风格关键词差异（Jaccard）+ 输出风格差异（带 skill 生成开场白）+ 健康判定 |
| `analyze_style_diff.py` | 对 6 位完整蒸馏产物做风格差异分析（style_tags Jaccard / pedagogy 多样性 / Teaching Philosophy 对比）|
| `test_skill_completeness.py [tids]` | 测文本量是否够构建完整 skill（对比不同语料量的标签丰富度）|

## 其他（既有，非本轮）

`bench_m4_latency.py`（M4 延迟基准）、`validate_events.py`（teaching_events 校验）、
`run_demo_pipeline.py` / `generate_sample_data.py`（旧 demo，待更新为 v2 路径）。

---

## 典型流程：从真转写到匹配

```bash
PY=D:/anaconda3/envs/edu/python.exe
# 1. 迁数据到规范位置（若数据在 Teacher_data_new）
$PY scripts/migrate_teacher_data.py
# 2. 完整蒸馏 6 位（产 TeacherSkill.md + skill_profile）
$PY scripts/distill_all_full.py
# 3. 验证风格差异
PYTHONIOENCODING=utf-8 $PY scripts/analyze_style_diff.py
# 4. 真实匹配 demo
PYTHONIOENCODING=utf-8 $PY scripts/demo_match_real.py
```

依赖：`.env` 需配 `DEEPSEEK_API_KEY`（评价 style_tagger / 匹配 matcher / 蒸馏均调 DeepSeek）。
蒸馏额外需 `npm install -g @anthropic-ai/claude-code`（走 claude-agent-sdk）。
