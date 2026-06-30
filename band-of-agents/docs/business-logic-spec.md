# IQ Relay + Band Routing — 业务逻辑规格 & 解耦方案

> **用途**：本文档是平台无关的业务逻辑权威定义。Part 1-2 定义原有的6阶段需求流水线（IQ Relay）。Part 3 定义新增的 Band 路由层——处理客户后续反馈的智能路由。移植到任何新框架时，逐条核验本文件中的逻辑是否被完整保留。

---

## 目录

**Part 1：业务逻辑规格（IQ Relay 原有）**
1. [核心概念定义](#1-核心概念定义)
2. [流水线阶段定义](#2-流水线阶段定义)
3. [流转规则](#3-流转规则)
4. [硬门禁逻辑](#4-硬门禁逻辑)
5. [人机交互模式](#5-人机交互模式)
6. [知识库读写规则](#6-知识库读写规则)
7. [Session生命周期](#7-session生命周期)
8. [消息路由规则](#8-消息路由规则)
9. [异常与边界情况](#9-异常与边界情况)

**Part 2：解耦方案（IQ Relay 原有）**
10. [三层架构](#10-三层架构)
11. [四个平台接口](#11-四个平台接口)
12. [文件分类与抽离清单](#12-文件分类与抽离清单)
13. [抽离步骤](#13-抽离步骤)
14. [配置拆分](#14-配置拆分)

**Part 3：Band 路由层（新增）**
15. [两层关系：首次需求 vs 后续反馈](#15-两层关系首次需求-vs-后续反馈)
16. [Routing-Agent 角色定义](#16-routing-agent-角色定义)
17. [路由决策逻辑](#17-路由决策逻辑)
18. [Band 集成架构](#18-band-集成架构)
19. [后续反馈数据流](#19-后续反馈数据流)
20. [Band Room 通信协议](#20-band-room-通信协议)
21. [知识库扩展：反馈追踪条目](#21-知识库扩展反馈追踪条目)
22. [Band 路由层异常处理](#22-band-路由层异常处理)

---

# Part 1：业务逻辑规格

## 1. 核心概念定义

| 术语 | 定义 |
|---|---|
| **Session** | 一个用户与系统的一次交互上下文。包含当前流水线状态、阶段、phase、最后活跃时间。同一用户同时只有一个活跃 Session。 |
| **PipelineState** | 一条需求从提交到完成的全生命周期状态对象。包含 requirement_id、原始文本、累积输入、各阶段 schema、知识库检索结果、时间戳、日志。 |
| **Agent** | 执行特定阶段任务的 LLM 角色。6个 Agent 各有独立的系统提示词（`agents/01~06.md`）、token 上限、工具白名单。 |
| **Stage** | 流水线阶段编号 1-6。每个 Stage 有明确的输入 schema、输出 schema、操作角色。 |
| **Phase** | Stage 内部的子阶段。例如 Stage 2 有 `pm`（PM 填表）和 `confirm`（AI 生成后确认）两个 phase。Stage 3 有 `estimate` 和 `result`。Stage 5 有 `survey`、`feedback`、`result`。 |
| **Verdict** | 阶段判定结果。Stage 1 有三种：`approved`/`rejected`/`info_needed`。Stage 4 有两种：`approved`/`blocked`。Stage 3 审批有四种：`approve`/`reject`/`defer`/`delegate`。 |
| **Schema** | 每个阶段输出的标准 JSON 结构。Schema 1 = 守门结果，Schema 2 = 价值转化结果，以此类推。Schema 由 `schema_builder.py` 统一组装，不由 AI 直接输出。 |
| **Knowledge Entry** | 写入知识库的一条记录。6种 entry_type，详见知识库章节。 |
| **Foundry IQ** | 知识库系统。负责语义检索、归档写入、经验查询。当前实现为飞书 Bitable + LLM embedding 向量匹配，逻辑上是一个抽象层。 |
| **Accumulated Input** | Stage 1 多轮追问时累积的上下文。每轮补充信息追加（不覆盖）到 `accumulated_input`，AI 基于全量上下文重新提取。 |

---

## 2. 流水线阶段定义

### Stage 1 — 守门（Gatekeeping）

| 属性 | 值 |
|---|---|
| **角色** | 售前 / 提交者 |
| **输入** | 用户原始自然语言需求文本 |
| **AI 做什么** | (1) 检索 Foundry IQ 历史相似需求；(2) 从自然语言提取4个结构化字段；(3) 判断需求类型和来源可追溯性；(4) 如信息不足，生成追问问题 |
| **人做什么** | 看到可编辑表单（AI 预填4字段），修改/确认后点"Confirm"或"Reject" |
| **输出 Schema** | Schema 1：verdict + 4字段（customer_who, usage_scenario, problem, expected_outcome）+ requirement_type + source_traceable + reject_reason / followup_questions |
| **Verdict 逻辑** | **机械判定，不由 AI 决定**。根据 requirement_type 确定必填字段集 → 全填=approved，部分填=info_needed，全空=rejected |
| **特殊机制** | 多轮追问，最多3轮。每轮用 accumulated_input（全量拼接）。3轮后仍 info_needed → 强制 rejected。 |

**4个结构化字段：**

| 字段 | 含义 | 何时必填 |
|---|---|---|
| `customer_who` | 谁（客户身份） | requirement_type = customer_reported 时必填 |
| `usage_scenario` | 什么场景 | 所有类型必填 |
| `problem` | 什么问题 | 所有类型必填 |
| `expected_outcome` | 期望结果 | 所有类型必填 |

**需求类型（requirement_type）：**

| 类型 | 说明 | customer_who 必填 | source_traceable 必填 |
|---|---|---|---|
| `customer_reported` | 客户需求 | ✅ | ✅ |
| `internal_improvement` | 内部改进 | ❌ | ❌ |
| `compliance` | 合规需求 | ❌ | ❌ |
| `competitive` | 竞品对标 | ❌ | ❌ |

**字段合并规则（多轮）：**
- 当前轮提取到值 → 用新值
- 当前轮返回 null → 沿用上一轮的值（carry forward）
- 模型输出的 "null"/"none"/"n/a"/"unknown" 字符串 → 视为 null

---

### Stage 2 — 价值转化（Value Transform）

分两个 phase：

**Phase 2a — PM 填表**

| 属性 | 值 |
|---|---|
| **角色** | 产品经理 |
| **AI 做什么** | 用 `quick_completion` 轻量 LLM 调用，基于 Stage 1 的4字段预填 PM 表单 |
| **人做什么** | 编辑4个字段：core_value（核心价值）、acceptance_criteria（验收标准）、feature_def（功能定义）、priority（优先级 SP/P0/P1/P2） |
| **可升级** | ✅ 可升级组长（"Escalate to Lead"，组长裁决后放行或终止） |

**Phase 2b — AI 生成 + PM 确认**

| 属性 | 值 |
|---|---|
| **AI 做什么** | 基于 PM 输入 + Stage 1 的4问，生成结构化验收标准（structured_criteria）和测试用例（test_cases） |
| **人做什么** | 看到可编辑表单（AI 预填 criteria + test cases），修改后点"Confirm"或"Modify"（回到 2a） |
| **输出 Schema** | Schema 2：four_q + pm_core_value + pm_feature_def + pm_priority + structured_criteria[] + test_cases[] |

**结构化验收标准字段：**
```
criterion_id, description, metric, threshold, measurement_method, pm_original
```

**测试用例字段：**
```
case_id, criterion_id, actor, precondition, steps[],
expected_result, actual_result(null, 人工填), verdict(null, 人工填)
```

> `actual_result` 和 `verdict` 强制为 null —— AI 不可预填，必须人工填写。

---

### Stage 3 — 研发评估（Scenario Test）

分两个 phase：

**Phase 3a — RD 估算**

| 属性 | 值 |
|---|---|
| **角色** | 研发负责人 |
| **AI 做什么** | 无 AI 预填，纯人工填写 |
| **人做什么** | 填写：tech_plan（技术方案）、workload_days（工作量人天）、risks（技术风险） |
| **可升级** | ✅ 可升级组长（"Escalate to Lead"，组长裁决后放行或终止） |

**Phase 3b — RD 自测结果**

| 属性 | 值 |
|---|---|
| **AI 做什么** | 基于 RD 自测结果 + Schema 2 的 test_cases 生成测试分析 |
| **人做什么** | 填写：scenario_test（pass/partial/fail）、test_note、approval_result（approve/reject/defer/delegate）、approval_note |

**审批结果处理：**

| approval_result | 行为 |
|---|---|
| `approve` | 进入 Stage 4 |
| `reject` | 触发升级链 → 升级组长裁决，显示 escalation_notice_card |
| `defer` | 暂停，不移入下一阶段 |
| `delegate` | 转交他人，当前人不再处理 |

---

### Stage 4 — 发布审批（Release Review）

| 属性 | 值 |
|---|---|
| **角色** | 产品负责人 / 发布审批者 |
| **AI 做什么** | 基于 Schema 3 做发布预判 |
| **人做什么** | 填写：release_value、version、release_date、scenario_verified（yes/no）、release_risk（low/medium/high）、rollback_plan、approval_result（approve/reject/defer/delegate）、approval_note |
| **硬门禁** | 🔒 **approval=approve 且 scenario_verified=no → 代码层面拦截，不可绕过** |
| **输出** | release_verdict = `approved` 或 `blocked`（机械判定：P0 需求 acceptance_verdict=fail → blocked） |

**硬门禁具体逻辑：**
```
if approval == "approve" and scenario_verified != "yes":
    → 拦截！不发版，重新显示 Stage 4 表单
    → 提示："Customer Scenario Verified is No. Release cannot proceed."
```

---

### Stage 5 — 客户反馈（Feedback Collect）

分三个 phase：

**Phase 5a — 问卷设计**

| 属性 | 值 |
|---|---|
| **AI 做什么** | 基于 Stage 1 的 problem + Stage 2 的 criteria 生成问卷问题 |
| **人做什么** | 编辑问卷问题后发布 |

**Phase 5b — 反馈录入**

| 属性 | 值 |
|---|---|
| **人做什么** | 粘贴客户反馈数据（CSV 或文本格式） |

**Phase 5c — AI 分析**

| 属性 | 值 |
|---|---|
| **AI 做什么** | 分析反馈数据：识别投诉聚类（complaint_clusters）、意外好评（unexpected_positives）、客户健康度（customer_health_snapshot） |
| **输出** | Schema 5：complaint_clusters[] + unexpected_positives[] + customer_health_snapshot |

**前置条件：** Stage 4 release_verdict = "approved" 才执行 Stage 5。

---

### Stage 6 — 复盘（Retrospective）

| 属性 | 值 |
|---|---|
| **角色** | 全员 |
| **AI 做什么** | (1) 检索本需求所有 rejection 记录，计算返工统计；(2) 分析全流程 schemas + 时间戳；(3) 识别瓶颈（bottlenecks）；(4) 评估 ROI（roi_verdict）；(5) 生成知识条目（knowledge_entries_written）；(6) 计算流程健康度 |
| **人做什么** | 查看 AI 复盘结果，点"Finish"结束 |
| **唯一写入者** | Stage 6 是知识库经验条目（retrospective 类型）的**唯一写入者**。其他阶段只写 stage_output / rejection_feedback 等。 |
| **输出** | Schema 6：roi_verdict + bottlenecks[] + knowledge_entries_written[] + summary_for_team |

**返工统计逻辑：**
```python
# 检索本 requirement_id 的所有 rejection 记录
rej_records = search_similar(requirement_title, filter=requirement_id)
# 统计：总拒绝次数、拒绝阶段列表、拒绝原因列表
```

**流程健康度计算（纯算术，非 AI）：**
```python
health_score = max(0.0, 1.0 - improvement_actions_count * 0.1)
```

---

## 3. 流转规则

### 正向流转

```
S1(approved) → S2a(PM填表) → S2b(AI生成+确认) → S3a(RD估算) → S3b(RD自测)
→ S4(发布审批, approved) → S5a(问卷) → S5b(反馈) → S5c(AI分析) → S6(复盘) → Finish
```

### 回退链（升级裁决模式 — BPMN 兼容）

> **设计变更说明（2026-06-08）**：原回退链采用跨阶段回退（S3→S2→S1），
> 违反 BPMN 2.0 "no need to return to earlier phases for rework" 原则。
> 现改为**升级裁决模式**：不退回，改为升级给组长决策。不通过则终止流程。
> 流程方向始终向前，符合 BPMN Exclusive Gateway 分支语义。

| 从 | 动作 | 触发条件 | 行为 |
|---|---|---|---|
| S2 | 升级组长 | PM 点 "Escalate to Lead" | 弹 escalation_card → 组长裁决：approve→S3 / reject→终止 / info→S2原地重试 |
| S3 | 升级组长 | RD 点 "Escalate to Lead" 或 approval=reject | 弹 escalation_card → 组长裁决：approve→S4 / reject→终止 / info→S3原地重试 |
| S4 | 升级组长 | approval=reject | 弹 escalation_card → 组长裁决：approve→S5 / reject→终止 / info→S4原地重试 |
| S4 | 终止 | approval=defer | 写 rejection_feedback → 暂停 |
| 任意阶段 | 原地重试 | rollback_retry | 回到当前阶段起点，显示上次拒绝原因（BPMN Loopback） |
| 任意阶段 | 终止 | rollback_abandon | 终止流水线（BPMN End Event） |

### 升级通知卡（Escalation Notice Card）

被升级时显示：
- **from_stage → team_lead**
- **拒绝原因**（必须填写）
- **返工次数**（rework_count）
- 三个选项：✅ Approve & Advance / ❌ Reject & Terminate / ❓ Request More Info (Retry)

### 三轮追问强制拒绝

```
round 1: info_needed → 提示补充
round 2: info_needed → 提示补充
round 3: info_needed → 强制 rejected，写入 rejection_feedback
```

> 关键：`gatekeeping_rounds` 计数器在 `run_stage1_gatekeeper` 内递增，是单一事实来源。

### 人工修改保留规则

回退后重新显示表单时，**必须保留人之前填的数据**，不能被 AI 重新预填覆盖：

| 场景 | 保留的数据 |
|---|---|
| S2 modify → S2a | `state.stage2_pm_data`（core_value, acceptance_criteria, feature_def, priority） |
| S3 back → S3a | `state.stage3_estimate`（tech_plan, workload_days, risks） |
| rollback_retry → S2 | `state.stage2_pm_data` |
| rollback_retry → S1 | 重新跑 S1（accumulated_input 保留） |

---

## 4. 硬门禁逻辑

### 硬门禁 1 — Stage 1 来源可追溯性

**规则：**
- requirement_type = `customer_reported` 时，`source_traceable` 必须为 true
- `customer_who` 必须非空
- 不可由 AI 直接判断 true/false —— 由 schema_builder 根据 verdict 推断（approved → true）

**不满足时：**
- verdict 降级为 `info_needed` → 追问
- 3轮后仍不满足 → 强制 `rejected`

### 硬门禁 2 — Stage 4 场景验证

**规则：**
```python
if approval_result == "approve" and scenario_verified != "yes":
    BLOCK  # 代码层面拦截，不可绕过
```

**不满足时：**
- 不进入 Stage 5
- 重新显示 Stage 4 表单
- 提示："HARD GATE: Customer Scenario Verified is No. Release cannot proceed."

**发布判定（机械，非 AI）：**
```python
# Schema 4 verdict 逻辑
for req in requirements_list:
    if req.importance == "P0" and req.acceptance_verdict == "fail":
        return "blocked"
return "approved"
```

### 硬门禁与普通审批的区别

| | 普通审批 | 硬门禁 |
|---|---|---|
| 可绕过？ | ✅ 审批人可选择 approve | ❌ 代码层面拦截，审批人无法绕过 |
| 退回后 | 可选择 retry/escalate/abandon | 必须满足条件才能继续 |
| 验证位置 | 业务逻辑层 | 代码层面 `if` 拦截 |

---

## 5. 人机交互模式

### 核心原则：AI 预填 → 人工编辑 → 提交

**不是"AI 建议 → 人审批"，而是"AI 把表单填好 → 人改不对的地方 → 提交"。**

| 阶段 | AI 预填什么 | 人改什么 | 人不能改什么 |
|---|---|---|---|
| S1 | 4字段提取值 | 4字段均可编辑 | requirement_id, original_text, submitted_at |
| S2a | core_value, acceptance_criteria, feature_def, priority | 全部可编辑 | requirement_id, four_q |
| S2b | structured_criteria, test_cases | 全部可编辑（文本框） | requirement_id |
| S3a | 无预填（纯人工） | tech_plan, workload_days, risks | — |
| S3b | 无预填 | scenario_test, test_note, approval_result, approval_note | — |
| S4 | release_verdict 预判（只读显示） | release_value, version, date, scenario_verified, risk, rollback_plan, approval | release_verdict 预判结果 |
| S5a | 问卷问题 | 可编辑 | requirement_id |
| S5b | 无预填 | 反馈数据 | — |

### 字段级权限模型

```
字段权限 = {readonly | editable | hidden}
```

每个阶段的每个字段必须明确标注权限。移植时核验：**是否有任何字段原本应该是 readonly 却变成了 editable，或反之？**

### 必填校验规则

| 字段 | 必填条件 |
|---|---|
| S1 all 4 fields | 根据 requirement_type 的 required_fields 配置 |
| S2a core_value | 始终必填 |
| S2a acceptance_criteria | 始终必填 |
| S2a feature_def | 始终必填 |
| S2a priority | 始终必填 |
| S3a tech_plan | 始终必填 |
| S3a workload_days | 始终必填 |
| S3a risks | 始终必填 |
| S4 release_value | 始终必填 |
| S4 version | 始终必填 |
| S4 release_date | 始终必填 |
| S4 scenario_verified | 始终必填（硬门禁） |
| S4 release_risk | 始终必填 |
| S4 approval_result | 始终必填 |
| 审批备注 | reject/defer/delegate 时必填 |

> ⚠️ **飞书卡片处理**：飞书交互卡片（Interactive Card）的前端必填校验通过 `required: true` 字段实现。当前实现保留前端校验，同时服务端做二次校验。

### 下一负责人字段（next_person）

每个阶段表单底部都有 `next_person` 字段，用于流转通知。当前默认值硬编码为 "Jacky"。移植时应改为从用户目录动态获取或留空。

---

## 6. 知识库读写规则

### 6种 entry_type

| entry_type | 写入时机 | 写入者 | 内容 |
|---|---|---|---|
| `stage_output` | 每个阶段完成时 | PipelineState.archive() | 该阶段的完整 schema |
| `human_correction` | 人工修改了 AI 预填字段时 | bot._handle_card_action | 修改记录：field, old, new |
| `rejection_feedback` | 任何拒绝/退回时 | bot._handle_card_action 或 Pipeline | action, reason, lesson |
| `survey_design` | Stage 5a 问卷发布时 | bot | survey_questions |
| `feedback_analysis` | Stage 5c AI 分析完成时 | run_stage5_feedback_collect | complaint_clusters, health, insights |
| `retrospective` | Stage 6 复盘完成时 | run_stage6_retrospective（**唯一写入者**） | knowledge_entries_written[] |

### 统一 Schema（每条 Knowledge Entry）

```json
{
  "id": "req_xxx-s1-stage_output",
  "requirement_id": "req_xxx",
  "requirement_title": "AI生成标题",
  "entry_type": "stage_output",
  "stage": 1,
  "revision": 1,
  "status": "active",
  "author": "system | 用户名",
  "timestamp": "ISO 8601",
  "last_modified": "ISO 8601",
  "tags": ["customer_reported", "qc"],
  "searchable_text": "拼接的可检索文本",
  "content": { /* 阶段特定 payload */ },
  "retraction": null  // 或 {retracted_at_stage, retracted_by, reason}
}
```

### 写入规则

1. **每次流转至少写入一条 stage_output** —— 阶段完成时自动调用 `state.archive()`
2. **每次拒绝写入一条 rejection_feedback** —— 包含 reason 和 lesson
3. **每次人工修改写入一条 human_correction** —— 记录 field/old/new
4. **Stage 6 是 retrospective 类型的唯一写入者** —— 避免重复写入经验条目
5. **merge_or_upload** —— 相同 ID = 更新，不是重复创建
6. **revision 递增** —— 回退后重新提交，revision +1

### 读取规则

1. **Stage 1 开始时**：用原始需求文本检索 top 3 相似历史需求，弹 Foundry IQ Alert Card
2. **Stage 6 复盘时**：用 requirement_id 过滤检索本需求的所有 rejection 记录
3. **? 查询模式**：用户输入 `?关键词`，检索 top 3，用 AI 生成自然语言回答

### searchable_text 构建规则

根据 entry_type 拼接不同的可检索文本：

| entry_type | 拼接来源 |
|---|---|
| stage_output | title + customer_who + problem + expected_outcome + pm_core_value + pm_feature_def + rd_tech_plan + release_value |
| rejection_feedback | title + reason + lesson |
| human_correction | title + "Field X changed from A to B" |
| feedback_analysis | title + complaint theme + description |
| retrospective | title + knowledge entry summary |

### Demo 模式

- `DEMO_MODE=true` 时，知识库使用内存 dict（`_DEMO_STORE`）
- `seed_demo_data()` 预填5条 demo 数据（制造业场景）
- 适用于无飞书 Bitable 环境的本地开发

---

## 7. Session生命周期

### 创建

- 用户发送非 `?` 开头的文本，且无活跃 Session → 创建新 Session
- 创建时初始化 PipelineState，stage=1，phase=None

### TTL 过期

```python
_PIPELINE_TTL_SECONDS = 15 * 60  # 15分钟
```

- 每次交互更新 `last_active` 时间戳
- 如果 `now - last_active > 15分钟` → Session 过期，清除，下一条消息启动新 Session
- 过期时提示："Previous session expired. Starting fresh."

### 并发处理

- **同一用户同时只有一个活跃 Session**
- 如果 Session 活跃中且用户发送新需求文本 → 提示"Pipeline already in progress. Use card buttons to proceed. Send 'cancel' to stop."
- 用户必须先 `cancel` 或等 TTL 过期

### Session 状态

| status | 含义 | 允许的操作 |
|---|---|---|
| `active` | 流水线进行中 | 卡片按钮交互 |
| `info_needed` | Stage 1 等待补充信息 | 发送文本 = 补充信息 |
| `rejected` | 需求被拒绝 | 只能发新需求或 cancel |
| `completed` | 流水线完成 | 自动清除，发新需求 |

### 特殊命令

| 命令 | 行为 |
|---|---|
| `cancel` | 清除当前 Session |
| `new` / `restart` / `reset` | 清除当前 Session，提示发新需求 |
| `?关键词` | 不受 Session 状态影响，随时可查知识库 |
| 空消息 | 显示帮助信息 |

---

## 8. 消息路由规则

### 路由优先级

```
1. 卡片 Action（activity.value 是 dict）→ _handle_card_action
2. 空消息 → 显示帮助
3. ? 开头 → Foundry IQ 查询
4. 活跃 Session 中 → 按 status 处理
5. 无 Session → 启动新 Pipeline
```

### 卡片 Action 路由

卡片提交的 `action_data` 包含 `action` 和 `stage` 字段：

| action | stage | 行为 |
|---|---|---|
| `confirm_stage1` | 1 | 确认 S1 → 进入 S2a |
| `reject_stage1` | 1 | 弹 feedback_capture_card |
| `stage2_generate` | 2 | PM 提交 → AI 生成 → S2b |
| `stage2_sendback` | 2 | 退回 S1 |
| `stage2_confirm` | 2 | 确认 S2 → 进入 S3a |
| `stage2_modify` | 2 | 回到 S2a |
| `stage3a_confirm` | 3 | 估算确认 → S3b |
| `stage3_back` | 3 | 回到 S3a |
| `stage3_submit` | 3 | RD 提交审批 → approve/reject/defer/delegate |
| `stage3_reject` | 3 | 弹 feedback_capture_card |
| `stage4_submit` | 4 | 发布审批 → 硬门禁检查 |
| `stage5a_submit` | 5 | 问卷发布 → S5b |
| `stage5b_analyze` | 5 | AI 分析 → S5c |
| `stage5_continue` | 5 | 进入 S6 |
| `feedback_submit` | 任意 | 写入 rejection_feedback → rollback_notice_card |
| `feedback_skip` | 任意 | 跳过反馈，停止 |
| `rollback_retry` | 目标 stage | 回到目标阶段重做 |
| `rollback_escalate` | 目标 stage | 继续往上退 |
| `rollback_abandon` | — | 终止 |
| `next` | 当前 | 进入下一阶段 |
| `stop` | 当前 | 停止 |
| `finish` | 6 | 完成，清除 Session |

### 阶段一致性检查

- 卡片提交的 `stage` 必须与当前 Session 的 `stage` 一致
- 不一致时提示："This card is outdated. Please use the latest card."
- 例外：rollback 相关 action 跳过阶段检查（跨阶段操作）

---

## 9. 异常与边界情况

### LLM 返回非法 JSON

- `extract_json_from_response()` 尝试多种提取策略：```json 代码块 → 裸 JSON 对象 → schema_version 匹配
- `_repair_json_text()` 修复常见问题：未转义引号、换行符、尾随逗号
- 全部失败 → 返回 None → 阶段标记为失败，不崩溃

### LLM 超时 / API 错误

- `run_agent()` 捕获异常，返回 `{"text": "Error: ...", "tool_calls": []}`
- `quick_completion()` 捕获异常，返回空字符串
- Stage 2 AI 生成失败 → 构建空 fallback schema，提示"AI generation timed out — showing empty form"

### Agent 工具循环

- `run_agent()` 限制最多 5 轮工具调用，防止无限循环
- 未知工具名 → 返回 `{"error": "unknown tool"}`

### 用户中途切换话题

- 活跃 Session 中发送非命令文本 → 不启动新流水线，提示"use card buttons to proceed"
- 必须显式 `cancel` 或等 TTL 过期

### Stage 2 AI 预填失败

- `quick_completion` 返回空 → 使用规则兜底：
  - core_value → 用 expected_outcome
  - acceptance_criteria → 生成模板
  - feature_def → 用 customer + scenario 拼接
  - priority → customer_reported → P0，其他 → P1

### Demo 模式降级

- 飞书 Bitable 不可用时 → 降级到内存 `_DEMO_STORE`
- 搜索失败时 → `print(f"search failed, falling back to demo")` + 返回 demo 结果

### 多轮追问中模型自相矛盾

- verdict 不由模型决定，由 `schema_builder` 根据字段填充情况机械判定
- 模型可能输出 verdict=rejected 但字段全填了 → 被覆盖为 approved

---

# Part 2：解耦方案

## 10. 三层架构

```
┌──────────────────────────────────────────┐
│  业务核心层（完全平台无关，零外部依赖）      │
│                                          │
│  • pipeline.py    — 6阶段编排+流转规则    │
│  • schema_builder.py — Schema组装+校验    │
│  • agent_runner.py — LLM调用引擎         │
│  • agents/01~06.md — Agent系统提示词      │
│  • pipeline_config.yaml — 流程定义        │
│                                          │
│  依赖：4个接口（抽象），不依赖任何实现       │
└──────────────────┬───────────────────────┘
                   │ 依赖注入
┌──────────────────┴───────────────────────┐
│  平台抽象层（定义接口，纯抽象）             │
│                                          │
│  • MessagingInterface  — 消息收发         │
│  • CardInterface       — 卡片渲染         │
│  • KnowledgeBase       — 知识库读写       │
│  • UserDirectory       — 用户查找         │
└──────────────────┬───────────────────────┘
                   │ 接口被具体实现
┌──────────────────┴───────────────────────┐
│  平台实现层（每换一个框架写一套）           │
│                                          │
│  Teams实现（历史）    飞书/Lark实现（当前）│
│  Slack实现（未来）     Band实现（新增）    │
└──────────────────────────────────────────┘
```

**核心原则：业务核心层依赖接口，不依赖具体框架。换框架时只写新实现，核心代码零改动。**

---

## 11. 四个平台接口

### Interface 1: MessagingInterface — 消息收发

```python
class MessagingInterface(ABC):
    @abstractmethod
    async def receive_message(self) -> IncomingMessage:
        """接收用户消息。返回统一的 IncomingMessage 结构。"""

    @abstractmethod
    async def send_text(self, user_id: str, text: str) -> None:
        """发送纯文本消息。"""

    @abstractmethod
    async def send_card(self, user_id: str, card: dict) -> None:
        """发送可交互卡片。card 是平台无关的 CardSchema dict。"""

    @abstractmethod
    async def update_card(self, card_id: str, card: dict) -> None:
        """更新已有卡片（部分平台支持）。"""
```

**IncomingMessage 统一结构：**
```python
@dataclass
class IncomingMessage:
    user_id: str
    user_name: str
    text: str           # 纯文本部分
    card_action: dict   # 卡片提交数据（无卡片则为 None）
    timestamp: float
```

**当前飞书实现：** `card_handler.py` 中的 `RequirementBot` + lark_oapi WebSocket 长连接

**消息路由逻辑上移：** `?查询 / 新需求 / Action / 补充文本` 的分类逻辑在业务核心层，接口只管"收"和"发"。

---

### Interface 2: CardInterface — 卡片渲染

```python
class CardInterface(ABC):
    @abstractmethod
    def render_editable_form(
        self, stage: int, phase: str,
        prefill_data: dict, readonly_fields: list[str],
        actions: list[CardAction]
    ) -> dict:
        """渲染可编辑表单。返回平台特定卡片格式。"""

    @abstractmethod
    def render_display_card(
        self, title: str, sections: list, footer: str = ""
    ) -> dict:
        """渲染只读展示卡片。"""

    @abstractmethod
    def render_rollback_notice(
        self, from_stage: int, to_stage: int,
        reason: str, rework_count: int
    ) -> dict:
        """渲染回退通知卡片。"""

    @abstractmethod
    def parse_action(self, payload: dict) -> CardAction:
        """解析用户提交的卡片数据为统一 CardAction 结构。"""
```

**CardAction 统一结构：**
```python
@dataclass
class CardAction:
    action: str    # "confirm_stage1", "stage2_generate", etc.
    stage: int
    form_data: dict  # 用户填写的表单数据
```

**卡片 Schema（平台无关）上移到业务核心层：** 每个阶段哪些字段可编辑、哪些只读、审批选项列表、必填校验规则 —— 用纯 dict 表达，不依赖任何 UI 框架。`CardInterface` 只负责"拿 schema 渲染成对应框架的卡片格式"。

**当前飞书实现：** `card_templates.py` 中的所有 `*_card()` 函数（飞书交互卡片 JSON）

---

### Interface 3: KnowledgeBase — 知识库

```python
class KnowledgeBase(ABC):
    @abstractmethod
    def search_similar(
        self, query: str, top_k: int = 5,
        filter_expr: str | None = None
    ) -> list[dict]:
        """语义检索相似记录。返回统一 schema 的记录列表。"""

    @abstractmethod
    def archive(
        self, entry_type: str, requirement_id: str,
        requirement_title: str, stage: int, author: str,
        content: dict, tags: list[str] = None,
        revision: int = 1, status: str = "active"
    ) -> str:
        """写入知识库。返回记录 ID。"""

    @abstractmethod
    def get_entry(self, doc_id: str) -> dict | None:
        """按 ID 查询单条记录。"""
```

**写入时机和内容定义上移到业务核心层：** `pipeline.py` 中的 `PipelineState.archive()` 决定何时写、写什么。`KnowledgeBase` 接口只管"存"和"查"。

**统一记录 Schema：** 即 Part 1 第6节的 Knowledge Entry 结构。所有实现必须返回/接受这个 schema。

**当前飞书实现：** `tools.py` 中的 Bitable 读写 + LLM embedding 向量匹配

**其他可能实现：**
- Azure AI Search（原有 Teams 实现）
- 通用：Pinecone / Weaviate / pgvector / Elasticsearch

---

### Interface 4: UserDirectory — 用户查找

```python
class UserDirectory(ABC):
    @abstractmethod
    def search_users(self, name: str, top: int = 5) -> list[dict]:
        """按姓名搜索用户。返回 [{display_name, email, user_id, department, job_title}]"""

    @abstractmethod
    def lookup_user(self, name: str) -> dict | None:
        """查询单个用户。返回第一个匹配或 None。"""

    @abstractmethod
    def verify_next_person(self, name: str) -> str:
        """验证下一负责人是否存在。返回确认消息字符串。"""
```

**当前飞书实现：** `tools.py` 中的 `resolve_feishu_user_id`（飞书通讯录 API）

**其他可能实现：**
- Microsoft Graph（原有 Teams 实现）
- 通用：LDAP / 企业通讯录 API

---

## 12. 文件分类与抽离清单

### ✅ 直接复制（平台无关，零修改）

| 原路径 | 说明 |
|---|---|
| `agents/01-gatekeeper.md` | Agent 系统提示词 |
| `agents/02-value-transform.md` | |
| `agents/03-scenario-test.md` | |
| `agents/04-release-review.md` | |
| `agents/05-feedback-collect.md` | |
| `agents/06-retrospective.md` | |
| `pipeline/schema_builder.py` | Schema 组装+校验，纯数据逻辑，零外部依赖 |

### 🔧 复制后需修改

| 原路径 | 改什么 |
|---|---|
| `pipeline/agent_runner.py` | (1) 删除 `from config.config import DEEPSEEK_*`，改为 `from config.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL`；(2) `_client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)`；(3) 其余不变 |
| `pipeline/pipeline.py` | (1) 删除 `from pipeline.foundry_iq import ...`，改为 `from pipeline.interfaces import KnowledgeBase`；(2) 所有 `foundry_iq.xxx()` 改成 `self.kb.xxx()` 或注入的 `kb.xxx()`；(3) `PipelineState.archive()` 改为调用注入的 `kb.archive()`；(4) 删除未实现的 `send_teams_message` 工具引用 |
| `config/pipeline_config.yaml` | 保留飞书相关字段（bitable_stage, bitable_prefix, write_bitable_record, resolve_feishu_user_id, send_feishu_message） |
| `config/config.py` | 保留 `DEEPSEEK_*` → 改名为 `LLM_*`；保留 `FEISHU_*` `BITABLE_*`；删除 `AI_SEARCH_*` `TEAMS_*` `STORAGE_*` |

### 📝 需要新建

| 文件 | 内容 |
|---|---|
| `pipeline/interfaces.py` | 4个抽象接口定义（MessagingInterface, CardInterface, KnowledgeBase, UserDirectory）+ IncomingMessage / CardAction 数据类 |
| `pipeline/cards_schema.py` | 从 `cards.py` 提取纯数据层：每个阶段的字段定义、读写权限、必填规则、审批选项列表。用 dict 表达，不依赖任何 UI 框架 |
| `pipeline/router.py` | 消息路由骨架：`dispatch(msg) → action` 的分发逻辑，调用 MessagingInterface 收发消息。抽象出 `send(card_name, data)` 接口 |
| `pipeline/kb_demo.py` | KnowledgeBase 的 Demo 实现（内存 dict 版本），用于本地测试 |
| `platform/feishu/` | 飞书平台实现目录（现有代码重构后放入） |
| `band-routing/` | Band 路由层实现目录（新增，见 Part 3） |

### ❌ 不复制（平台锁死）

| 原路径 | 原因 | 替代方案 |
|---|---|---|
| `bot.py` | Bot Framework SDK 绑定，Teams 专用（历史代码） | 飞书已用 `card_handler.py` + lark_oapi WebSocket 替代 |
| `pipeline/cards.py` | Adaptive Cards JSON 格式，Microsoft 专用（历史代码） | 飞书已用 `card_templates.py` 替代 |
| `pipeline/foundry_iq.py` | Azure AI Search SDK 绑定（历史代码） | 飞书已用 Bitable + LLM embedding 替代 |
| `pipeline/work_iq.py` | Microsoft Graph 用户查找绑定（历史代码） | 飞书已用 `resolve_feishu_user_id` 替代 |

---

## 13. 抽离步骤

### Step 1: 写接口定义

创建 `pipeline/interfaces.py`，定义4个抽象接口 + IncomingMessage / CardAction 数据类。纯抽象，不含任何实现。

### Step 2: 提取卡片 Schema

创建 `pipeline/cards_schema.py`，从 `cards.py` 中提取每个阶段的：
- 字段列表（id, label, type, default, placeholder）
- 读写权限（readonly / editable）
- 必填规则
- 审批选项列表
- Action 定义（button id, label, action string, stage）

用纯 dict / dataclass 表达，不依赖任何 UI 框架。

### Step 3: 改造业务核心层

修改 `pipeline.py` 和 `agent_runner.py`：
- 删除所有 `from pipeline.foundry_iq import ...` 和 `from pipeline.cards import ...`
- 改为 `from pipeline.interfaces import KnowledgeBase, CardInterface, ...`
- `PipelineState` 的构造函数接收 `kb: KnowledgeBase` 实例
- 所有 `foundry_iq.xxx()` → `self.kb.xxx()`
- 所有卡片渲染调用 → 通过 `CardInterface` 实例

### Step 4: 飞书实现套接口

将飞书相关代码重构为接口的实现：
- `card_handler.py` → `platform/feishu/messaging.py`（`FeishuMessaging(MessagingInterface)`）
- `card_templates.py` → `platform/feishu/card_renderer.py`（`FeishuCardRenderer(CardInterface)`）
- `tools.py` 中的 Bitable 部分 → `platform/feishu/kb.py`（`BitableKB(KnowledgeBase)`）
- `tools.py` 中的 `resolve_feishu_user_id` → `platform/feishu/user_dir.py`（`FeishuUserDir(UserDirectory)`）

**逻辑不动，只套接口。**

### Step 5: 验证飞书版本仍能跑

```bash
cd /Users/jacky/build/hackathon/band-of-agents/ai-requirement-pipeline
python -c "from pipeline.tools import send_feishu_message; print('OK')"
python -c "from pipeline.card_handler import *; print('OK')"
# 运行 demo.py，确认飞书版本功能不变
git status  # 确认改动范围
```

### Step 6: 写 Band 路由层实现

Band 路由层是新增的，不在原有架构中。详见 Part 3。

```
band-routing/
├── routing_agent.py      — RoutingAgent（Band SDK + Anthropic Adapter）
├── lark_bridge.py        — Lark消息桥接到Band Room
├── tools/
│   ├── bitable_reader.py — search_bitable_history / get_requirement_chain
│   └── lark_notifier.py  — notify_via_lark
└── prompts/
    └── routing_prompt.md — routing-agent 系统提示词
```

**Band 路由层调用飞书 Bitable 读取历史数据，通过 Band Room @mention 调度 Pipeline Agent，Pipeline Agent 仍通过飞书卡片与人交互。**

### Step 7: 写启动入口

```python
# main_feishu.py — 飞书版启动（原有6阶段流水线）
from pipeline.pipeline import PipelineOrchestrator
from platform.feishu.messaging import FeishuMessaging
from platform.feishu.card_renderer import FeishuCardRenderer
from platform.feishu.kb import BitableKB
from platform.feishu.user_dir import FeishuUserDir

orchestrator = PipelineOrchestrator(
    messaging=FeishuMessaging(),
    card_renderer=FeishuCardRenderer(),
    kb=BitableKB(),
    user_dir=FeishuUserDir(),
)
orchestrator.run()

# main_band.py — Band路由层启动（新增）
from band_routing.routing_agent import RoutingAgent
from band_routing.lark_bridge import LarkBridge

bridge = LarkBridge()  # 监听Lark消息 → 转发到Band Room
agent = RoutingAgent()  # 常驻Band Room，等待@mention

await bridge.start()
await agent.run()
```

**飞书版处理首次需求，Band版处理后续反馈。两者共享 Bitable 数据。**

---

## 14. 配置拆分

### 拆分原则

配置分为两份：

| 文件 | 内容 | 平台无关？ |
|---|---|---|
| `config/core_config.yaml` | 流程定义、Agent参数、TTL、轮数上限、审批选项 | ✅ 是 |
| `config/platform_config.yaml` | API密钥、endpoint、索引名、应用ID | ❌ 否，每个平台一份 |

### core_config.yaml（平台无关）

```yaml
# 从现有 pipeline_config.yaml 提取，删除所有 bitable_* 字段
requirement_types: [...]
priorities: [...]
approval_outcomes: [...]
stages: [...]
defaults:
  pipeline_name: "AI需求管理Pipeline"
  max_concurrent_requirements: 10
  session_ttl_seconds: 900  # 15分钟
  max_gatekeeping_rounds: 3
```

### platform_config.yaml（飞书/Lark 版示例 — 当前使用）

```yaml
llm:
  api_key: ${ANTHROPIC_API_KEY}
  base_url: https://api.anthropic.com
  model: claude-sonnet-4-5

knowledge_base:
  backend: feishu_bitable
  app_token: ${BITABLE_APP_TOKEN}
  table_id: ${BITABLE_TABLE_ID}
  base_url: ${FEISHU_BASE_URL}  # 国内: https://open.feishu.cn/open-apis | 国际: https://open.larksuite.com/open-apis

messaging:
  backend: feishu_card
  app_id: ${FEISHU_APP_ID}
  app_secret: ${FEISHU_APP_SECRET}
  base_url: ${FEISHU_BASE_URL}
  websocket: true  # lark_oapi WebSocket 长连接

user_directory:
  backend: feishu_contact
  base_url: ${FEISHU_BASE_URL}

# Band 路由层配置（新增）
band:
  agent_id: ${BAND_AGENT_ID}
  api_key: ${BAND_API_KEY}
  room_id: ${BAND_ROOM_ID}
  sdk: thenvoi-sdk[anthropic]
```

---

## 附录：移植核验清单

移植到新框架后，逐条核验：

### 业务逻辑核验

- [ ] S1 四字段提取 + 多轮追问 + 3轮强制拒绝
- [ ] S1 verdict 机械判定（不由 AI 决定）
- [ ] S1 字段合并规则（carry forward）
- [ ] S2a AI 预填 → 人工编辑 → S2b AI 生成 → 确认
- [ ] S2b actual_result/verdict 强制 null
- [ ] S3a/S3b 两阶段，RD 先估算后自测
- [ ] S3 approval 四选项（approve/reject/defer/delegate）
- [ ] S4 硬门禁：scenario_verified=no 时代码拦截
- [ ] S4 release_verdict 机械判定（P0 fail → blocked）
- [ ] S5 三阶段（survey/feedback/result）
- [ ] S6 唯一 retrospective 写入者
- [ ] S6 返工统计检索逻辑
- [ ] 回退链完整（S2→S1, S3→S2, rollback_retry/escalate/abandon）
- [ ] 回退后人工输入保留（stage2_pm_data, stage3_estimate）
- [ ] Session TTL 15分钟过期
- [ ] 同一用户单 Session
- [ ] ?查询不受 Session 状态影响
- [ ] 知识库6种 entry_type 全部实现
- [ ] 知识库 merge_or_upload（相同ID=更新）
- [ ] searchable_text 按 entry_type 构建

### 交互核验

- [ ] 所有阶段都是"AI预填 → 人工编辑 → 提交"
- [ ] 字段读写权限正确（readonly/editable）
- [ ] 必填校验规则正确
- [ ] 回退通知卡显示原因 + 返工次数 + 三选项
- [ ] feedback_capture_card 在拒绝时弹出
- [ ] Foundry IQ Alert Card 在 S1 开始时弹出（有相似记录时）

### 异常处理核验

- [ ] LLM 返回非法 JSON 不崩溃
- [ ] LLM 超时有 fallback
- [ ] Agent 工具循环有上限（5轮）
- [ ] 知识库不可用时降级到 demo 模式

---

# Part 3：Band 路由层（新增）

> **定位**：Part 1-2 定义的6阶段流水线解决"首次需求"——从客户口头描述到交付复盘的全链路。Part 3 定义的 Band 路由层解决"后续反馈"——客户在交付后提出的 bug、使用问题、新需求，不需要重走全流程，由 routing-agent 诊断+判断最短路径，直接路由到对应阶段。

> **飞书与 Band 的生态分工**：飞书（Lark）负责人机交互（交互卡片审批、消息通知、Bitable 数据归档），Band 负责 Agent 间通信（@mention 路由、上下文传递、Room 协作）。两者不冲突——飞书管"人和数据"，Band 管"Agent 和 Agent"。Band 本身不提供业务工具（无卡片、无数据库、无用户目录），飞书补充了这些能力。

## 15. 两层关系：首次需求 vs 后续反馈

### 核心区分

| | 首次需求（IQ Relay） | 后续反馈（Band 路由层） |
|---|---|---|
| **触发** | 客户/售前提交新需求 | 客户在交付后提出反馈 |
| **处理方式** | 走完整6阶段流水线 | 跳过不必要环节，走最短路径 |
| **谁来路由** | 固定流程 S1→S2→...→S6 | routing-agent 根据历史上下文动态判断 |
| **运行在哪** | Lark/飞书侧（现有，不动） | Band Room（新增） |
| **数据来源** | 用户输入 | Bitable 历史需求档案 + 客户反馈文本 |

### 一句话

> **IQ Relay 管"第一次"，routing-agent 管"之后每一次"。两者共享同一份 Bitable 数据。**

### 关系图

```
客户首次需求
    │
    ▼
┌───────────────────────────────┐
│  IQ Relay 6阶段流水线（Lark）   │
│  S1→S2→S3→S4→S5→S6           │
│  飞书卡片审批 · Bitable沉淀     │
└──────────────┬────────────────┘
               │ 产生结构化需求档案
               ▼
        ┌──────────────┐
        │  飞书 Bitable  │ ◄──── routing-agent 读取历史
        └──────────────┘
               ▲
               │ 后续反馈触发
               │
┌──────────────┴────────────────┐
│     Band Room（新增）           │
│                               │
│  @routing-agent               │
│  1.查历史 → 2.诊断 → 3.路由    │
│         │                     │
│         ▼ @mention            │
│  对应Pipeline Agent启动        │
│  →发Lark卡片给负责人            │
└───────────────────────────────┘
```

---

## 16. Routing-Agent 角色定义

| 属性 | 值 |
|---|---|
| **名称** | `routing-agent` |
| **运行环境** | Band Room（常驻在线） |
| **角色** | 分诊 + 诊断 + 路由（三合一） |
| **模型** | Claude Sonnet（通过 Band AnthropicAdapter） |
| **能力** | CONTACTS（发现其他Agent）、自定义工具（Bitable查询、Lark通知） |

### 输入

| 字段 | 类型 | 说明 |
|---|---|---|
| `customer_name` | string | 客户名称 |
| `feedback_text` | string | 客户反馈原文 |
| `feedback_source` | string | 来源渠道（Lark群/工单/邮件） |
| `timestamp` | ISO 8601 | 反馈时间 |

### 输出（RoutingDecision）

```json
{
  "routing_id": "route_xxx",
  "matched_requirement_id": "REQ-089",
  "diagnosis": {
    "problem_type": "technical_bug",
    "severity": "high",
    "description": "搜索功能回归bug，非新需求"
  },
  "routing_decision": {
    "target_stage": 3,
    "target_agent": "@scenario-test-agent",
    "reason": "回归bug，需从S3场景测试切入，重新跑验收标准",
    "skip_stages": [1, 2],
    "context_summary": "REQ-089验收标准：响应<3秒。客户反馈：最近搜索又慢了。"
  },
  "notification": {
    "notify_role": "测试负责人",
    "card_type": "s3_rerun",
    "message": "REQ-089回归bug，请重新执行验收标准测试用例"
  }
}
```

### 工具白名单

| 工具 | 用途 | 来源 |
|---|---|---|
| `search_bitable_history` | 语义检索历史需求 | 新增（需实现） |
| `get_requirement_chain` | 拉取一条需求的完整S1-S6链路 | 新增（需实现） |
| `band_send_message` | @mention 对应Pipeline Agent | Band SDK原生 |
| `notify_via_lark` | 发Lark卡片给对应负责人 | 复用现有tools.py |

---

## 17. 路由决策逻辑

### 决策三步

```
Step 1 — 历史匹配
  查Bitable：这条反馈属于哪条历史需求的后续？
  ├── 命中 → 提取该需求的完整链路（S1-S6档案）
  └── 未命中 → 判定为全新需求 → 路由到S1守门

Step 2 — 问题诊断
  结合历史上下文 + 反馈文本，判断：
  ├── technical_bug（技术bug）→ 路由到S3或S4
  ├── usage_issue（使用问题）→ 通知运营/售后
  ├── new_requirement（新需求）→ 路由到S1
  ├── service_complaint（服务投诉）→ 通知售前/PM
  └── regression（回归问题）→ 路由到S3重新跑验收标准

Step 3 — 最短路径
  根据诊断结果决定从哪个Stage切入：
  ├── S1切入：全新需求，走全流程
  ├── S2切入：需求范围变更，需PM重新定义验收标准
  ├── S3切入：技术bug/回归，需重新跑测试用例
  ├── S4切入：发版相关问题，需重新评审
  ├── S5切入：客户反馈/满意度问题，需重新收集反馈
  └── 直接通知人：使用问题/服务投诉，不走流水线
```

### 路由规则表

| 诊断结果 | target_stage | target_agent | 通知谁 | 跳过哪些阶段 |
|---|---|---|---|---|
| `new_requirement` | 1 | @gatekeeper-agent | 售前 | 无（走全流程） |
| `technical_bug` | 3 | @scenario-test-agent | 测试负责人 | S1, S2 |
| `regression` | 3 | @scenario-test-agent | 测试负责人 | S1, S2 |
| `scope_change` | 2 | @value-transform-agent | PM | S1 |
| `release_issue` | 4 | @release-review-agent | 产品负责人 | S1, S2, S3 |
| `feedback_issue` | 5 | @feedback-collect-agent | 售后 | S1-S4 |
| `usage_issue` | — | 直接通知 | 运营/售后 | 不走流水线 |
| `service_complaint` | — | 直接通知 | 售前/PM | 不走流水线 |

### 诊断判定规则

诊断由 LLM 完成，但受以下硬约束：

```
约束1：如果历史匹配命中REQ-ID，且反馈内容包含"又出问题了/之前修过/上次也这样"
      → 优先判定为 regression，路由到S3

约束2：如果历史匹配命中REQ-ID，且反馈内容包含"能不能加/想要新功能"
      → 判定为 scope_change，路由到S2

约束3：如果历史未命中，且反馈描述了具体业务场景
      → 判定为 new_requirement，路由到S1

约束4：如果反馈内容是纯使用疑问（"怎么用/在哪设置"）
      → 判定为 usage_issue，直接通知运营，不走流水线

约束5：如果无法明确分类
      → 兜底路由到S1，走全流程（宁可慢，不可漏）
```

---

## 18. Band 集成架构

### 架构全景

```
┌─────────────────────────────────────────────────────────────┐
│                         用户侧                               │
│                                                              │
│   客户在Lark群发送后续反馈                                      │
│   "上次那个搜索功能最近又出问题了"                                │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                     Lark Bridge（桥接层）                      │
│                                                              │
│   收Lark消息 → 转发到Band Room → @routing-agent              │
│   单向转发，不做任何判断                                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                      Band Room                               │
│                                                              │
│   ┌─────────────────────────────────────────┐               │
│   │         @routing-agent                  │               │
│   │                                         │               │
│   │  1. 查Bitable历史 → 匹配REQ-ID           │               │
│   │  2. 诊断问题类型                          │               │
│   │  3. 判断最短路径                          │               │
│   │  4. @mention 对应Pipeline Agent          │               │
│   └─────────────┬───────────────────────────┘               │
│                 │                                            │
│                 │  @mention + 上下文                          │
│                 ▼                                            │
│   ┌─────────────────────────────────────────┐               │
│   │    被调度的Pipeline Agent               │               │
│   │    （从指定Stage启动，非从头开始）        │               │
│   └─────────────┬───────────────────────────┘               │
│                 │                                            │
└─────────────────┼────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                  AI需求链（Lark飞书侧，不动）                   │
│                                                              │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐                 │
│   │ S1守门   │  │ S2价值转化│  │ S3场景测试│                 │
│   └──────────┘  └──────────┘  └──────────┘                 │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐                 │
│   │ S4发版评审│  │ S5反馈收集│  │ S6复盘分析│                 │
│   └──────────┘  └──────────┘  └──────────┘                 │
│                                                              │
│   被调度的Agent从指定Stage启动                                 │
│   → 发Lark卡片给对应负责人                                    │
│   → 人审批/处理                                               │
│   → 结果写入Bitable                                           │
└─────────────────────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                  飞书 Bitable（数据层）                        │
│                                                              │
│   每条需求从S1到S6的完整档案                                    │
│   routing-agent 读取历史上下文                                 │
│   Pipeline Agent 写入处理结果                                  │
└─────────────────────────────────────────────────────────────┘
```

### Band Room 参与者

| 参与者 | 类型 | 职责 |
|---|---|---|
| `@routing-agent` | Band Agent（常驻） | 接收反馈，诊断+路由 |
| `@gatekeeper-agent` | Band Agent（按需唤醒） | S1守门（全新需求时） |
| `@value-transform-agent` | Band Agent（按需唤醒） | S2价值转化（范围变更时） |
| `@scenario-test-agent` | Band Agent（按需唤醒） | S3场景测试（bug/回归时） |
| `@release-review-agent` | Band Agent（按需唤醒） | S4发版评审（发版问题时） |
| `@feedback-collect-agent` | Band Agent（按需唤醒） | S5反馈收集（反馈问题时） |
| `@retrospective-agent` | Band Agent（按需唤醒） | S6复盘（需复盘时） |
| 人类用户 | Lark用户 | 收卡片，审批/处理 |

### 与官方Demo的对应

| 官方Demo | 本项目 |
|---|---|
| Personal Assistant（入口Agent） | routing-agent |
| weather_agent（1个） | Pipeline Agent（6个，按需唤醒） |
| 按Agent描述匹配 | 按历史上下文+问题诊断匹配 |
| 简单查询 | 企业需求链全流程 |

---

## 19. 后续反馈数据流

### 时序图

```
客户 Lark消息："搜索功能最近又慢了"
    │
    ▼
Lark Bridge
    │ 转发，不判断
    │
    ▼
@routing-agent（Band Room）
    │
    ├──→ search_bitable_history("搜索 慢")
    │    └──→ 命中 REQ-089（验收标准：响应<3秒）
    │
    ├──→ get_requirement_chain("REQ-089")
    │    └──→ 返回S1-S6完整档案
    │
    ├──→ 诊断
    │    └──→ "回归bug，反馈含'又慢了'，命中约束1"
    │
    ├──→ 路由决策
    │    └──→ target_stage=3, target_agent=@scenario-test-agent
    │
    └──→ band_send_message(
            content="REQ-089回归bug。验收标准：响应<3秒。
                    客户反馈：搜索又慢了。请重新执行S3测试用例。",
            mentions=["@scenario-test-agent"]
        )
              │
              ▼
        @scenario-test-agent 收到
              │
              ├──→ 读取REQ-089的Schema2（验收标准+测试用例）
              ├──→ 发Lark卡片给测试负责人
              │    "REQ-089回归bug，请重新跑以下测试用例：
              │     - TC001: 搜索响应时间<3秒
              │     - TC002: Top3结果相关度>80%"
              │
              ▼
        测试负责人在Lark审批/执行
              │
              ▼
        结果写入Bitable（REQ-089新增一条S3记录）
```

### 路径剪枝效果

| 场景 | 传统方式 | Band路由后 |
|---|---|---|
| 回归bug | 售前→PM→研发→测试→发版（6步） | routing→S3测试（2步） |
| 范围变更 | 售前→PM→研发→测试→发版（6步） | routing→S2 PM（2步） |
| 使用问题 | 售前→PM→运营（3步+等人） | routing→直接通知运营（1步） |
| 全新需求 | 售前→PM→研发→测试→发版（6步） | routing→S1（1步，走全流程） |

---

## 20. Band Room 通信协议

### 消息格式

routing-agent 发给 Pipeline Agent 的消息遵循统一格式：

```json
{
  "routing_id": "route_xxx",
  "matched_requirement_id": "REQ-089",
  "target_stage": 3,
  "context_summary": "REQ-089验收标准：响应<3秒。客户反馈：搜索又慢了。",
  "diagnosis": "regression",
  "instruction": "请重新执行S3测试用例，重点验证TC001和TC002",
  "skip_stages": [1, 2]
}
```

### @mention 规则

```
routing-agent 完成判断后，发送消息：
  band_send_message(
    content=<上述JSON>,
    mentions=["@scenario-test-agent"]
  )

被@的Agent被唤醒，处理完后：
  band_send_message(
    content="REQ-089 S3测试完成，TC001失败（响应4.2秒）。
             已通知研发。结果已写入Bitable。",
    mentions=["@routing-agent"]  // 可选：回报routing-agent
  )
```

### 通信约束

1. **routing-agent是唯一入口** — 客户反馈只@routing-agent，不直接@Pipeline Agent
2. **Pipeline Agent不主动@其他Agent** — 处理完即静默，由人或routing-agent决定下一步
3. **上下文完整传递** — routing-agent发出的消息必须包含matched_requirement_id和context_summary
4. **Band Memory存储路由状态** — 每次路由决策的routing_id、诊断结果、目标Stage存入Band Memory

---

## 21. 知识库扩展：反馈追踪条目

### 新增 entry_type

| entry_type | 写入时机 | 写入者 | 内容 |
|---|---|---|---|
| `feedback_routing` | routing-agent做出路由决策时 | routing-agent | routing_id, matched_requirement_id, diagnosis, target_stage |

### Knowledge Entry 扩展

```json
{
  "id": "route_xxx-feedback_routing",
  "requirement_id": "REQ-089",
  "requirement_title": "搜索功能优化",
  "entry_type": "feedback_routing",
  "stage": null,
  "revision": 1,
  "status": "active",
  "author": "routing-agent",
  "timestamp": "ISO 8601",
  "tags": ["regression", "technical_bug"],
  "searchable_text": "REQ-089 回归bug 搜索又慢了 路由到S3",
  "content": {
    "routing_id": "route_xxx",
    "feedback_text": "搜索功能最近又慢了",
    "diagnosis": "regression",
    "target_stage": 3,
    "skip_stages": [1, 2],
    "resolution": null
  },
  "retraction": null
}
```

### searchable_text 构建

```
feedback_routing: title + feedback_text + diagnosis + target_stage描述
```

### 价值

routing-agent 每次路由决策都写入知识库，形成**反馈追踪链**：
- 同一条需求的每次后续反馈都有记录
- 可以统计：哪些需求反复出bug？哪些客户反馈最频繁？
- S6复盘Agent可以读取所有feedback_routing条目，纳入复盘分析

---

## 22. Band 路由层异常处理

### routing-agent 无法匹配历史需求

```
search_bitable_history 返回空 →
  判定为 new_requirement →
  路由到S1守门，走全流程
```

### routing-agent 诊断不确定

```
LLM 无法明确分类 →
  兜底路由到S1（约束5：宁可慢，不可漏）
```

### target_agent 离线（Band Room中未注册）

```
@mention 后无响应（超时30秒）→
  routing-agent 降级：直接通过notify_via_lark通知对应负责人
  在Band Room发消息："@scenario-test-agent 离线，已通过Lark直接通知测试负责人"
```

### Bitable 查询失败

```
search_bitable_history 异常 →
  routing-agent 降级：跳过历史匹配，直接诊断反馈文本
  在消息中标注："⚠️ 历史数据不可用，诊断基于反馈文本仅，可能不准确"
```

### Lark通知失败

```
notify_via_lark 异常 →
  routing-agent 在Band Room发消息通知人类：
  "⚠️ Lark通知失败，请手动查看REQ-089的S3测试用例"
```

### Pipeline Agent 处理失败

```
被@的Pipeline Agent处理超时或报错 →
  Agent在Band Room发消息：
  "⚠️ S3测试执行失败：[错误原因]。请人工介入。"
  routing-agent记录异常，不自动重试
```

---

## 附录：Band 路由层核验清单

### 路由逻辑核验

- [ ] routing-agent 能接收Lark Bridge转发的反馈消息
- [ ] search_bitable_history 正确返回匹配的历史需求
- [ ] get_requirement_chain 返回完整的S1-S6档案
- [ ] 诊断结果符合5条约束规则
- [ ] 路由决策表8种情况全覆盖
- [ ] 兜底路由到S1生效（约束5）

### Band通信核验

- [ ] routing-agent 是唯一入口，客户反馈只@routing-agent
- [ ] @mention 消息包含完整的routing上下文JSON
- [ ] Pipeline Agent处理完不主动@其他Agent
- [ ] Band Memory存储路由状态

### 知识库核验

- [ ] feedback_routing 类型正确写入
- [ ] searchable_text 按规则构建
- [ ] S6复盘能读取feedback_routing条目

### 异常处理核验

- [ ] 历史未命中→路由S1
- [ ] 诊断不确定→兜底S1
- [ ] Agent离线→降级Lark通知
- [ ] Bitable失败→降级纯文本诊断
- [ ] Lark失败→Band Room通知

---

*本文档基于 IQ Relay 项目代码（2026年6月版本）+ Band of Agents Hackathon 架构设计整理。*

*代码路径：*
- *IQ Relay：`/Users/jacky/build/hackathon/band-of-agents/ai-requirement-pipeline/`*
- *Band路由层：`/Users/jacky/build/hackathon/band-of-agents/band-routing/`（待实现）*
