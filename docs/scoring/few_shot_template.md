# MIND 评分校准库：8 样本人工标注表单 (v1)

> **用途**：在 Week 1 / 2 由两位标注者独立填写本表单，分歧复议后产出 `gold consensus`，再注入 LLM Judge 的 `{{FEWSHOT_BLOCK}}`。
> **存储位置**：完成后的样本以 JSON 形式存入 `data/teacher_skill/scoring/gold_samples/`，本 md 文档保留为模板与流程说明。

---

## 0. 校准库组成原则

总共 **8 个样本**，按以下结构分配，确保覆盖每个维度的高/中/低 + 对抗：

| 编号 | 角色 | 主要锚定维度 | 期望分数特征 |
|---|---|---|---|
| GS_001 | 高 Pace 锚 | Pace | Pace ≥ 0.75，其余可中性 |
| GS_002 | 低 Pace 锚 | Pace | Pace ≤ 0.30 |
| GS_003 | 高 Rigor / 低 Humor 锚 | Rigor, Humor | Rigor ≥ 0.75，Humor ≤ 0.25 |
| GS_004 | 高 Humor / 高 Interactivity 锚 | Humor, Interactivity | 二者均 ≥ 0.70 |
| GS_005 | 高 Abstraction / 低 Detail 锚 | Abstraction, Detail | Abstraction ≥ 0.75，Detail ≤ 0.30 |
| GS_006 | 低 Abstraction / 高 Detail 锚（直觉构建型）| Abstraction, Detail | Abstraction ≤ 0.30，Detail ≥ 0.70 |
| **GS_007** | **对抗：照本宣科** | 全维 | 看似 Rigor 高但 Interactivity 极低、自我纠正为零 |
| **GS_008** | **对抗：指标灌水** | A1 | 自评全维偏高，观测应显著低于自评（用于训练造假检测） |

---

## 1. 单个样本的填写流程

### Step 1：选定语料片段
- 从 3 位真实教师的 9 段录音中选 5 分钟连续片段
- 转写文本长度约 **600–1000 中文字符**
- 文本必须**自包含**（不依赖前后文也能判断风格）
- 含时间戳（每 30 秒一个标记）

### Step 2：独立标注
- 两位标注者**互不交流**地各自填写下表（Annotator A / B 列）
- 标注前必读 `docs/scoring/scoring_rubric.md`
- 每个维度必须附 **≥ 2 条证据原文 + 30 字理由**

### Step 3：分歧识别
- Fingerprint：|A.score − B.score| ≥ 0.20 → `DISPUTE_FP`
- Pedagogy：A.value ≠ B.value → `DISPUTE_PED`

### Step 4：复议
- 各自陈述证据、互相提问
- 达成一致 → 写入 `consensus` 列
- 未达成一致 → 提交第三人裁判 → 仍未一致 → 标 `DISPUTED`，本样本不入校准库

### Step 5：定型
- 完整样本（含两人原始打分、复议日志、最终 consensus）写入 JSON
- 文件名：`GS_<序号>_<role简称>.json`
- 进 `gold_samples/` 目录前必须通过 schema 校验

---

## 2. 单样本标注表单（模板）

> 每个样本复制一份，填入下列空位。

### 2.1 样本元信息

| 字段 | 值 |
|---|---|
| 样本 ID | `GS_001` |
| 校准角色 | `anchor_high_pace` |
| 源教师 ID | `T_<匿名>` |
| 源录音 session | `S<n>` |
| 时间范围 | `mm:ss – mm:ss` |
| 录音时长 | `5 min` |
| 课程主题 | _请填_ |
| 学生层级 | _请填_ |
| 班级规模 | _请填_ |
| 学科类别 | _请填_ |

### 2.2 转写片段

```
[00:00] <原文，含逐句时间戳，600–1000 字>
[00:30] ...
[01:00] ...
...
[05:00]
```

### 2.3 教师自评（**仅 GS_008 必填**，其他可选）

| 维度 | 自评分 / 自选 |
|---|---|
| pace | _0.xx_ |
| detail | _0.xx_ |
| abstraction | _0.xx_ |
| interactivity | _0.xx_ |
| humor | _0.xx_ |
| rigor | _0.xx_ |
| concept_entry | _enum_ |
| intuition_building | _enum_ |
| analogy_density | _enum_ |
| blackboard_strategy | _enum_ |
| misconception_alert | _enum_ |

### 2.4 双人独立标注（Fingerprint）

| 维度 | A 分 | A 证据（≥ 2 条 + 30 字理由）| B 分 | B 证据 | 分歧? | Consensus |
|---|---|---|---|---|---|---|
| pace | | • [mm:ss] "..." <br> • [mm:ss] "..." <br> 理由：__ | | • <br> • <br> 理由：__ | | |
| detail | | | | | | |
| abstraction | | | | | | |
| interactivity | | | | | | |
| humor | | | | | | |
| rigor | | | | | | |

### 2.5 双人独立标注（Pedagogy）

| 维度 | A 枚举 | A 证据 + 理由 | B 枚举 | B 证据 + 理由 | 分歧? | Consensus |
|---|---|---|---|---|---|---|
| concept_entry | | | | | | |
| intuition_building | | | | | | |
| analogy_density | | | | | | |
| blackboard_strategy | | _若无板书数据填 INSUFFICIENT_EVIDENCE_ | | | | |
| misconception_alert | | | | | | |

### 2.6 复议日志（若有分歧）

```
DISPUTE: <维度名>
  A 立场：<陈述>
  B 立场：<陈述>
  新证据补充：<片段或时间戳>
  裁判（如有）：<陈述>
  最终决议：<分数/枚举>
  决议日期：YYYY-MM-DD
```

### 2.7 标注者笔记

> 100 字以内：本样本为什么是某个维度的锚点？标注过程发现了哪些 rubric 文档没覆盖的边界情况？

---

## 3. 8 样本预期分布速查

```
                    pace  detail  abstr  inter  humor  rigor
GS_001 (高 Pace)    ≥0.75   *      *      *      *      *
GS_002 (低 Pace)    ≤0.30   *      *      *      *      *
GS_003 (高严肃)      *      *      *      *      ≤0.25  ≥0.75
GS_004 (高互动幽默)   *      *      *     ≥0.70  ≥0.70   *
GS_005 (抽象骨架)    *      ≤0.30 ≥0.75   *      *      *
GS_006 (直觉详细)    *      ≥0.70 ≤0.30   *      *      *
GS_007 (照本宣科)    *      *      *     ≤0.15   *      ?
GS_008 (灌水)        ←  observed 应低于 self_declared 约 0.2 以上  →
```

`*` 表示该维度无强约束，自然观测即可。

---

## 4. JSON 落盘格式（程序消费版）

每个样本最终落盘为 `gold_samples/GS_xxx_<role>.json`，结构如下：

```json
{
  "sample_id": "GS_001",
  "rubric_version": "v1.0",
  "calibration_role": "anchor_high_pace",
  "source": {
    "teacher_id": "T_xxx",
    "session_id": "S2",
    "time_range": "10:30-15:30",
    "subject": "电路 / 大二",
    "class_size": 60
  },
  "transcript_excerpt": "[00:00] ... [05:00]",
  "self_declared": null,
  "annotations": {
    "annotator_A": {
      "fingerprint": {
        "pace": {"score": 0.80, "evidence": [...], "reasoning": "..."},
        ...
      },
      "pedagogy": {...},
      "annotator_notes": "..."
    },
    "annotator_B": {...},
    "disputes": [
      {"dim": "rigor", "A": 0.50, "B": 0.30, "resolution": 0.40,
       "judge": "X", "notes": "..."}
    ]
  },
  "consensus": {
    "fingerprint": {
      "pace": {"score": 0.80, "confidence": "HIGH",
               "evidence": [...], "reasoning": "..."},
      ...
    },
    "pedagogy": {...}
  },
  "for_use_in_fewshot": true,
  "created": "2026-05-22"
}
```

---

## 5. 校准库的"健康检查"

每次新增 ≥ 5 个样本后，必须跑：

1. **维度覆盖度检查**：每个 fingerprint 维度都至少有 1 个高 + 1 个低锚点
2. **互信息检查**：8 个样本两两之间，至少有 2 个维度差异 ≥ 0.3（避免样本同质）
3. **Judge 回归测试**：当前 LLM Judge 在历史所有样本上的 MAE ≤ 0.10
4. **跨样本一致性**：同一标注者在不同样本上对同一维度的打分分布要合理散布（不全堆在 0.5）

---

## 6. 知情同意 / 隐私

- 所有进入校准库的转写片段必须**去标识化**（删除人名、机构名、班级代号）
- 教师需签署《MIND 项目录音 / 转写使用知情同意书》并明确以下用途：
  - 内部评分校准
  - LLM Judge 提示词内嵌（不上传至模型训练数据）
  - 学术报告 / 论文中可能匿名引用片段
- 教师保留**随时撤回**权利，撤回后对应样本必须从校准库删除并重新评估 Judge 校准

---

## 7. 变更日志

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-05-18 | 初版：8 样本结构、流程、JSON schema |
