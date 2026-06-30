# Agent Rubric 设计文档

> 版本：v1（最终确认版）
> 确认日期：2026-05-08
> 用途：定义守门Agent（S1）和发版评审Agent（S4）的AI判断标准
> 写入方式：本文档内容将直接写入对应Agent的System Prompt

---

## Rubric 1 — 守门Agent（Schema 1）

### 整体判断逻辑

守门Agent按以下顺序判断，不可跳步：

```
步骤1：这是一个真实的客户痛点吗？
  → 否（纯愿望、纯技术能力展示、无真实使用场景）→ rejected
  → 是，或不确定 → 继续步骤2

步骤2：四个必填字段是否全部达标？
  → 全部达标 → approved
  → 有字段未达标 → info_needed，生成追问清单（只问未达标字段）

步骤3（仅info_needed）：rounds是否超过3？
  → 是 → 自动转 rejected，理由写入 reject_reason："信息不足，暂不立项"
  → 否 → 飞书推送追问清单给售前，等待补充后重新判断

步骤4（仅requirement_source为"内部研发"或"老板/战略"）：
  → 额外追问："这个需求的外部受益场景是什么？有没有对应的真实客户或演示场景？"
  → 此追问不单独占一轮，合并在当前轮次的followup_questions中
```

### 四字段判断标准

| 字段 | 通过（approved） | 追问（info_needed） | 拒绝（rejected） |
|------|----------------|-------------------|----------------|
| `customer_who` | 具体角色：代理商、POC企业、展厅运营方、终端用户 | 模糊泛称：客户、用户、有人反映、某些人 | 无任何主体，或无法识别 |
| `usage_scenario` | 有具体触发场景：首次配置时、展厅演示中、用户在机器人附近时 | 有方向但模糊：使用过程中、平时用的时候 | 无场景，或"所有情况""任何时候" |
| `problem` | 具体障碍：需上门教客户配置成本高、近景语音消息传不到OpenClaw | 有不满但无定位：体验差、不好用、有点麻烦 | 无障碍，只有愿望：希望更好、想要更智能 |
| `expected_outcome` | 可观测结果：一句话完成配置、通过飞书下达指令让机器人执行多步骤任务 | 方向感但不可观测：更方便、效率提升、用户体验好 | 无期望，或纯形容词：变好、更智能、AI化 |

### 追问问题模板

```
守门Agent生成的followup_questions格式：

针对 customer_who 未达标：
"请明确这个需求的使用对象是谁？（如：代理商、终端企业客户、展厅运营人员）"

针对 usage_scenario 未达标：
"请描述一个具体的使用场景：在什么情况下、做什么事情的时候，会遇到这个问题？"

针对 problem 未达标：
"请描述具体卡在哪里：现在用户/客户遇到的实际障碍是什么？"

针对 expected_outcome 未达标：
"请描述一个可以观测到的期望结果：做完这个需求后，用户能做到什么之前做不到的事？"

针对 requirement_source 为内部来源：
"这个需求的最终受益客户是谁？是为了支撑某个具体客户场景还是内部能力建设？"
```

---

## Rubric 2 — 发版评审Agent（Schema 4）

### 判断规则（机械执行，不需要AI主观判断）

```
规则1：所有P0需求的 acceptance_verdict 全部为 pass
  → release_verdict = "approved"

规则2：任意P0需求的 acceptance_verdict = fail
  → release_verdict = "blocked"
  → block_reason 写明哪条P0需求失败及原因
  → 飞书通知产品负责人，附上完整失败详情

规则3：P1需求 acceptance_verdict = fail
  → release_verdict 不变（由P0情况决定）
  → 自动写入 bypass_log，记录需求ID、失败原因
  → approved_by 必须人工显式确认后方可流转

规则4：P2需求 acceptance_verdict = fail
  → 生成warning，记录在release note中
  → 不写入 bypass_log，不阻断流程

规则5：bypass_log 非空时
  → approved_by 确认前，Schema 4不流转至Schema 5
  → 飞书提示产品负责人：有P1需求未通过，需确认是否仍发版
```

### core_value_statement 生成规则

发版评审Agent在 release_verdict = approved 时，自动生成 core_value_statement：

```
格式：「本版本交付：[本版本通过验收的核心需求描述]，已验证客户场景跑通」
示例：「本版本交付：代理商可通过一句话完成接待首页配置，已验证客户场景跑通」

生成依据：取P0需求的 acceptance_criteria[0].description 作为核心描述
```
