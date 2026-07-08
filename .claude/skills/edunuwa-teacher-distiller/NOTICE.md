# NOTICE — edunuwa-teacher-distiller

## 衍生关系

本 Skill 是 [huashu-nuwa (女娲 · Skill造人术)](https://github.com/alchaincyf/nuwa-skill) 的衍生作品（derivative work）。

| 项 | 上游原版 | 本版 |
|---|---|---|
| 名称 | huashu-nuwa | edunuwa-teacher-distiller |
| 作者 | alchaincyf (花叔) | EduNUWA Team |
| 许可证 | MIT | MIT（见 [LICENSE](LICENSE)） |
| 仓库 | https://github.com/alchaincyf/nuwa-skill | 本仓库 `.claude/skills/edunuwa-teacher-distiller/` |
| 上游版本基线 | `main` 分支（vendor 时间：2026-05-08） | — |

原版的完整副本保留在 `.claude/skills/nuwa-skill/`，本版本与原版**目录平级共存**，便于对照、复现与答辩。

---

## 范式迁移：从「人物思维蒸馏」到「教师讲解蒸馏」

我们识别到女娲的**方法论结构**与教师讲解风格蒸馏在抽象层面同构：

```
女娲：素材采集 → 多维度提炼 → 检查点确认 → 模板组装 → 质量验证
本版：转写读取 → 教学维度提炼 → 检查点确认 → 契约组装 → 教学场景验证
```

但**输入源、提炼维度、输出契约、应用场景**四个层面需要重新设计。这种"识别同构 → 范式迁移 → 维度重构 → 契约对齐"的过程构成了本 Skill 的实质性创新。

---

## 修改清单（diff against upstream）

### 1. 输入源

| 项 | 原版 | 本版 | 修改原因 |
|---|---|---|---|
| 触发输入 | 人名 / 主题 / 模糊需求 | `teacher_transcript.json` 路径 + `output_dir` | 教学场景已通过模块二 ASR 获得一手转写，无须网搜 |
| 模糊需求支持 | 提供 Phase 0B 诊断推荐流程 | 不支持，输入必须明确 | 教学场景目标明确（已知教师 + 已有语料） |

### 2. 流程裁剪

| Phase | 原版 | 本版 | 修改原因 |
|---|---|---|---|
| Phase 0A 需求澄清 | 人名 + 聚焦方向 + 用途 + 本地语料 | **简化**：仅校验转写文件存在与有效 | 输入已结构化 |
| Phase 0B 模糊诊断 | 包含 | **删除** | 不适用 |
| Phase 0.5 创建目录 | `[person]-perspective/` 多子目录 | **删除** | 输出单文件 `TeacherSkill.md`，无须复杂目录 |
| Phase 1 6-Agent 调研 | 著作/对话/表达/他者/决策/时间线 6 个并行 Agent 网络搜集 | **完全删除** | 转写文本就是一手素材，权重最高 |
| Phase 1.5 调研检查点 | 6 维度来源数 / 一手二手比 | **保留思路，简化形式**：仅展示已读 segments 数与覆盖时长 | 单一信息源无需多维度统计 |
| Phase 2 提炼 | 心智模型 / 决策启发式 / 表达 DNA / 价值观 / 智识谱系 / 诚实边界 | **重构维度**：8 项教学维度（见下） | 教学场景特化 |
| Phase 2.5 提炼确认 | 提炼摘要确认 | **保留** | 复用上游的"主观判断重的环节先确认"思想 |
| Phase 3 模板组装 | `references/skill-template.md`（人物视角模板） | **替换**：按 `docs/api_contract.md §3` 的 7 段契约组装 | 对齐 EduNUWA 接口规范 |
| Phase 4 质量验证 | 已知 / 边缘 / 风格 3 项测试 | **替换**：教学场景 3 项测试（见下） | 验证目标不同 |
| Phase 5 双 Agent 精炼 | auto-skill-optimizer + skill-creator | **可选保留** | 对教学场景同样有用，但优先级降低 |

### 3. 提炼维度重构（核心改动）

| 上游维度 | → | 本版维度 | 提取重点 |
|---|---|---|---|
| 心智模型（3-7 个） | → | **教学哲学** | 教师反复强调的「为什么这样讲」信念 |
|  | → | **讲解模式** | 概念引入 → 直觉 → 定义 → 公式 → 例子 → 易错 → 总结的实际节奏 |
| 决策启发式 | → | **类比方式** | 类比来源领域、类比频率、类比 vs 形式定义的优先顺序 |
| 表达 DNA | → | **板书策略** | 写标题 / 写步骤 / 写公式 / 写对比表的频率与时机 |
|  | → | **公式讲法** | 先写公式还是先讲含义？逐项解释还是整体？ |
|  | → | **口吻特征** | 口头禅、互动方式、停顿习惯、提问句式 |
|  | → | **易错点提醒** | 「常见错误是…」「很多同学会…」等模式 |
|  | → | **总结方式** | 阶段总结 / 整节课总结的句式 |
| 价值观 / 反模式 | → | **保留诚实边界** | 语料不足时明确标注薄弱维度（继承上游"60 分原则"） |
| 智识谱系 | →  | **删除** | 教学场景不关心教师受谁影响 |

### 4. 输出契约对齐

| 项 | 原版输出 | 本版输出 |
|---|---|---|
| 输出路径 | `.claude/skills/[person]-perspective/SKILL.md` | 调用方传入的 `output_dir/TeacherSkill.md` |
| 文件结构 | frontmatter + 角色扮演规则 + 心智模型 + 决策启发式 + 表达 DNA + 时间线 + 智识谱系 + 诚实边界 | **严格按 `api_contract.md §3` 7 段**：Skill Purpose / Trigger / Teaching Philosophy / Explanation Pattern / Blackboard Policy / Speech Policy / Output Contract |
| Output Contract 段 | **不存在** | **新增**：明确事件类型 = `speak / board / formula / table / pause / quiz`，供下游 Agent 直接消费 |
| 元数据 | 无 | 同时输出 `skill_profile.json`（教师名 / 转写 ID / 维度覆盖 / 生成时间） |

### 5. 质量验证替换

| 上游测试 | → | 本版测试 |
|---|---|---|
| Sanity Check：选 3 个该人物公开表态过的问题对比立场 | → | **风格一致性**：用 Skill 重讲一段转写中的内容，与原转写片段对比讲解风格 |
| Edge Case：选 1 个该人物没公开讨论过的问题推断 | → | **跨知识点迁移**：用 Skill 讲一个转写未覆盖的新概念，看是否仍体现教学风格 |
| Voice Check：100 字判断表达特征 | → | **多模态契约一致性**：检查 Skill 产出能否驱动 `speak / board / formula` 事件流 |

### 6. 集成路径

| 项 | 原版 | 本版 |
|---|---|---|
| 触发方式 | 在 Claude Code 里 `/huashu-nuwa` 或自然语言 | Python 函数 `distill_teacher_skill()` 调用，符合 `api_contract.md §7.2` |
| 调用方 | 用户直接交互 | 后端服务 / `run_demo_pipeline()` |
| 返回 | Skill 文件落盘 | 文件落盘 + `dict {"status": ..., "skill_md": ..., "skill_profile": ...}` |

---

## 未引入 / 已删除的上游资产

为减小体积、降低耦合，本 vendor 未保留：

- 上游 `examples/`（13 个人物示例 + 1 个主题示例）—— 与教学场景无关
- 上游 `assets/`（图片素材） —— 与教学场景无关
- 上游 `references/`（方法论文档与 skill-template）—— 本版有自己的契约，不复用模板
- 多语言 README —— 仓库根 README 单独维护
- 上游 `scripts/download_subtitles.sh` —— 我们走 ASR，不下载字幕
- 上游 `scripts/srt_to_transcript.py` —— 不处理 SRT
- 上游 `scripts/merge_research.py` —— 不走 6-Agent 调研
- 上游 `scripts/quality_check.py` —— 检查项与本版维度不一致；如需自动化质量自检，将另行实现教学维度版

完整原版仍可在 `.claude/skills/nuwa-skill/` 查阅，便于对照与复现。

---

## 致谢 / Acknowledgements

感谢 [alchaincyf (花叔)](https://github.com/alchaincyf) 开源 nuwa-skill 项目，其方法论给了本项目重要启发。本版本在保留 MIT 协议的前提下进行了范式迁移与维度重构。
