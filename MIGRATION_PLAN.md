# MindTheGap → UiPath AgentHack 2026 改造计划

> **队名**: MindTheGap — Mind the information gap, knowledge gap, workflow gap
> 基于 `band-of-agents` 真实代码库的客观架构分析与迁移方案
> 创建日期：2026-06-08

---

## 一、现有架构全景

### 1.1 目录结构（精简）

```
band-of-agents/
├── core/                          # 业务核心层（平台无关）
│   ├── config.py                  # pydantic-settings 统一配置
│   ├── data_models.py             # RoutingDecision, FeedbackTrace, PIPELINE_STAGES
│   ├── pipeline_rules.py          # 6阶段流转规则、硬门禁、回退逻辑
│   ├── routing_logic.py           # 路由Agent核心逻辑（意图识别→检索→诊断→路由→通知）
│   ├── knowledge_logic.py         # 知识库查询逻辑（检索→AI摘要→发卡）
│   └── i18n.py                    # 中英双语
│
├── interfaces/                    # 平台抽象层（纯接口）
│   ├── llm.py                     # LLMInterface: chat(), chat_with_json_output()
│   ├── card.py                    # CardInterface: build_routing_card() 等6种卡片
│   ├── knowledge_base.py          # KnowledgeBaseInterface: search(), get_chain(), write_trace()
│   └── messaging.py               # MessagingInterface: send_message(), send_card(), start_listening()
│
├── platforms/feishu/              # 飞书实现层
│   ├── feishu_llm.py              # DeepSeek via OpenAI兼容协议
│   ├── feishu_card.py             # 飞书卡片2.0 JSON构建
│   ├── feishu_kb.py               # 飞书Bitable读写 + 关键词匹配检索
│   └── feishu_messaging.py        # 飞书消息API + WebSocket回调监听
│
├── platforms/band/                # Band平台实现（部分完成）
│   ├── band_connection.py
│   ├── engineering_agent.py
│   └── start_all_agents.py
│
├── band-routing/                  # Band路由Agent独立模块
│   ├── routing_agent.py           # Band SDK Agent
│   ├── knowledge_query_agent.py   # Band知识查询Agent
│   ├── lark_bridge.py             # Lark→Band桥接
│   ├── prompts/                   # 路由Agent的system prompt（中英）
│   └── tools/                     # Band Agent工具集
│
├── ai-requirement-pipeline/       # 原6阶段Pipeline（飞书版）
│   ├── pipeline/
│   │   ├── agent_runner.py        # LLM调用 + tool_use循环 + JSON提取
│   │   ├── schema_builder.py      # 纯Python规则引擎（verdict判定、算术计算）
│   │   ├── pipeline_config.yaml   # 流程定义（阶段/审批/硬门禁/工具白名单）
│   │   ├── card_templates.py      # 飞书交互卡片模板
│   │   ├── card_handler.py        # WebSocket卡片回调处理
│   │   ├── tools.py               # 飞书API工具（发消息/写Bitable/查用户）
│   │   └── demo.py                # 完整Pipeline演示入口
│   ├── agents/01~06.md            # 6个Agent的system prompt
│   └── schemas.md                 # 6个Schema JSON契约定义
│
├── harness/                       # 测试框架
│   ├── core/                      # 测试引擎、断言、报告
│   ├── adapters/                  # 适配器（模拟平台）
│   └── scenarios/                 # 3个测试场景（happy_path等）
│
├── main_feishu.py                 # 飞书平台入口（依赖注入）
├── main_slack.py                  # Slack平台入口（占位）
└── docs/business-logic-spec.md    # 22章业务逻辑规格文档
```

### 1.2 三层架构（已完成解耦）

```
┌──────────────────────────────────────────────┐
│  业务核心层 (core/)                           │
│  • 完全平台无关，零外部SDK依赖                  │
│  • 依赖4个interface，不知道具体平台             │
│  • routing_logic.py = 路由大脑                 │
│  • pipeline_rules.py = 流转规则引擎            │
│  • knowledge_logic.py = 知识库查询             │
└──────────────────┬───────────────────────────┘
                   │ 依赖注入
┌──────────────────┴───────────────────────────┐
│  平台抽象层 (interfaces/)                     │
│  • 4个ABC: LLM, Card, KB, Messaging          │
│  • 定义方法签名 + 统一数据结构                 │
└──────────────────┬───────────────────────────┘
                   │ 被具体实现
┌──────────────────┴───────────────────────────┐
│  平台实现层 (platforms/)                      │
│  • feishu/ — 当前完整实现                     │
│  • band/ — 部分实现                           │
│  • uipath/ — 本次新建 ← 改造目标              │
└──────────────────────────────────────────────┘
```

**关键发现：解耦已经完成。** `core/` 里没有任何飞书SDK import，全部通过interface调用。这意味着迁移到UiPath只需要写一个新的 `platforms/uipath/` 实现层。

### 1.3 数据流（当前）

```
客户在飞书群发消息
    ↓
feishu_messaging.py (WebSocket监听)
    ↓ MessageCallback
core/routing_logic.py
    ├── kb.search() → feishu_kb.py → 飞书Bitable API
    ├── llm.chat_with_json_output() → feishu_llm.py → DeepSeek API
    ├── card.build_routing_card() → feishu_card.py → 飞书卡片JSON
    └── messaging.send_card() → feishu_messaging.py → 飞书消息API
    ↓
飞书群显示路由通知卡片
```

### 1.4 6阶段Pipeline（原版，在 ai-requirement-pipeline/ 中）

```
S1 守门 → S2 价值转化 → S3 场景测试 → S4 发版审批 → S5 反馈收集 → S6 复盘
```

**关键细节（从代码中确认）：**

| 机制 | 实现位置 | 说明 |
|------|----------|------|
| S1三轮追问强制拒绝 | `pipeline_rules.py: check_s1_retry_limit()` | 3轮后强制rejected |
| S4硬门禁 | `pipeline_rules.py: can_advance()` + `pipeline_config.yaml: hard_gates` | scenario_verified≠yes → 代码拦截 |
| 回退机制 | `pipeline_rules.py: get_rollback_target()` | **`current_stage - 1`** — 退回上一阶段 |
| 回退选项 | `business-logic-spec.md` 第3节 | 重试/上退/放弃 |
| "上退" | `business-logic-spec.md` 回退链表格 | "继续往上退（S3→S1）" — **跨阶段回退** |
| Schema契约 | `schemas.md` | 6个JSON Schema，级联透传 |
| 规则引擎 | `schema_builder.py` | verdict机械判定，AI不做算术 |
| Agent工具循环 | `agent_runner.py: run_agent()` | 最多5轮tool_use，工具白名单按Agent过滤 |
| 知识库6种entry_type | `business-logic-spec.md` 第6节 | stage_output/human_correction/rejection_feedback等 |

### 1.5 路由层（新增的Band层）

```
客户后续反馈（非首次需求）
    ↓
routing_logic.py: process_feedback()
    ├── kb.search() → 检索历史需求
    ├── _diagnose() → LLM诊断：tech_bug/service_issue/new_requirement/complaint
    ├── DIAGNOSIS_TO_STAGE → 确定性映射（不经LLM）
    │   tech_bug → S3, service_issue → S2, new_requirement → S1, complaint → S5
    └── notify_handler() → 发卡片给阶段负责人
    ↓
write_trace() → 写入feedback_trace
```

---

## 二、客观架构对比：现有 vs 迁移后

### 2.1 架构层对照

| 层 | 当前实现 | 迁移后（UiPath） | 改动量 |
|----|----------|-----------------|--------|
| **业务核心层** `core/` | routing_logic, pipeline_rules, knowledge_logic | **完全不动** | 0% |
| **平台抽象层** `interfaces/` | 4个ABC | **完全不动** | 0% |
| **LLM实现** `platforms/feishu/feishu_llm.py` | DeepSeek via OpenAI协议 | **完全不动**（或换模型） | 0% |
| **卡片实现** `platforms/feishu/feishu_card.py` | 飞书卡片2.0 JSON | 新写 `platforms/uipath/uipath_card.py` → Action Center Form | 重写 |
| **知识库实现** `platforms/feishu/feishu_kb.py` | 飞书Bitable API + 关键词匹配 | 新写 `platforms/uipath/uipath_kb.py` → Data Service | 重写 |
| **消息实现** `platforms/feishu/feishu_messaging.py` | 飞书API + WebSocket | 新写 `platforms/uipath/uipath_messaging.py` → Orchestrator | 重写 |
| **Pipeline编排** `ai-requirement-pipeline/pipeline/` | Python串行 + YAML配置 | UiPath Maestro BPMN图 | 重写编排层 |
| **Agent层** `agents/01~06.md` | 6个system prompt | **完全不动** | 0% |
| **Schema层** `schemas.md` + `schema_builder.py` | 6个JSON Schema + 规则引擎 | **完全不动** | 0% |
| **路由Agent** `band-routing/` | Band SDK | 保留或包装为BPMN Service Task | 待定 |
| **测试框架** `harness/` | 自研harness + 3场景 | 保留核心，适配器改UiPath | 部分 |

### 2.2 数据流对比

```
当前数据流:
  飞书群消息 → WebSocket → routing_logic → [KB/LLM/Card/Messaging] → 飞书卡片

迁移后数据流:
  UiPath Action Center表单提交 → Orchestrator触发 → routing_logic → [KB/LLM/Card/Messaging] → Action Center任务
```

### 2.3 回退机制的关键发现

从 `pipeline_rules.py` 代码确认：

```python
def get_rollback_target(current_stage: int) -> int:
    if current_stage <= 1:
        return 1
    return current_stage - 1  # ← 退回上一阶段
```

从 `business-logic-spec.md` 确认：

> | 任意阶段 | 更上一阶段 | rollback_escalate | 继续往上退（S3→S1） |

**当前代码确实实现了跨阶段回退。** 这与 Track2 BPMN"no need to return to earlier phases"冲突。

### 2.4 资产清单

| 资产 | 文件 | 行数(估) | 迁移后命运 |
|------|------|----------|-----------|
| **6个Agent Prompt** | `agents/01~06.md` | ~3000行 | ✅ 完全保留 |
| **6个Schema契约** | `schemas.md` | ~400行 | ✅ 完全保留 |
| **规则引擎** | `schema_builder.py` | ~350行 | ✅ 完全保留 |
| **流转规则** | `pipeline_rules.py` | ~200行 | ✅ 完全保留（改回退逻辑） |
| **路由逻辑** | `routing_logic.py` | ~350行 | ✅ 完全保留 |
| **知识库逻辑** | `knowledge_logic.py` | ~150行 | ✅ 完全保留 |
| **数据模型** | `data_models.py` | ~100行 | ✅ 完全保留 |
| **LLM实现** | `feishu_llm.py` | ~150行 | ✅ 完全保留 |
| **i18n** | `i18n.py` | ~200行 | ✅ 完全保留 |
| **4个接口定义** | `interfaces/*.py` | ~400行 | ✅ 完全保留 |
| **Pipeline编排** | `demo.py` + `pipeline_config.yaml` | ~500行 | 🔄 改为BPMN图 |
| **飞书卡片** | `feishu_card.py` + `card_templates.py` | ~800行 | 🔄 重写为Action Center |
| **飞书消息** | `feishu_messaging.py` + `card_handler.py` | ~400行 | 🔄 重写为Orchestrator |
| **飞书知识库** | `feishu_kb.py` + `tools.py` | ~600行 | 🔄 重写为Data Service |
| **测试框架** | `harness/` | ~500行 | 🔄 适配器改UiPath |
| **业务规格文档** | `business-logic-spec.md` | ~1500行 | ✅ 保留，更新回退章节 |
| **回退逻辑** | `pipeline_rules.py` 回退方法 | ~40行 | ⚠️ 改为升级裁决 |

**统计：**
- ✅ 完全保留：~5500行核心代码 + 3000行Agent Prompt
- 🔄 需重写：~2300行平台实现层
- ⚠️ 需修改：~40行回退逻辑

---

## 三、改造计划

### 3.1 改造原则

1. **核心不动**：`core/` + `interfaces/` + `agents/` + `schemas.md` + `schema_builder.py` 零改动
2. **新增平台层**：写 `platforms/uipath/`，实现4个interface
3. **改回退**：`pipeline_rules.py` 的 `get_rollback_target()` 改为升级裁决逻辑
4. **BPMN编排**：在UiPath Maestro中画6阶段流程图
5. **最小改动**：能用interface解决的问题，不动core

### 3.2 分阶段计划

#### Phase 1：环境搭建 + 回退改造（第1周）

| 任务 | 文件 | 说明 |
|------|------|------|
| 1.1 注册Devpost | — | 提交方案表单，领UiPath Labs沙盒 |
| 1.2 领60天试用 | — | 备选方案，不等审批 |
| 1.3 改回退逻辑 | `core/pipeline_rules.py` | `get_rollback_target()` → 升级裁决逻辑 |
| 1.4 更新回退选项 | `card_templates.py` 或新UiPath卡片 | "重试/上退/放弃" → "通过/终止/补信息后放行" |
| 1.5 更新业务文档 | `docs/business-logic-spec.md` 第3节回退链 | 改为升级裁决描述 |
| 1.6 写测试验证 | `harness/scenarios/` | 新增升级裁决场景测试 |

**关键改动：回退逻辑**

```python
# 改前（当前代码）：
def get_rollback_target(current_stage: int) -> int:
    return current_stage - 1  # 退回上一阶段

# 改后（升级裁决）：
def get_rollback_target(current_stage: int) -> int | None:
    return None  # 不退回。改为升级到组长决策，不通过则终止

# 新增：
def get_escalation_target(current_stage: int) -> dict:
    """升级裁决：不通过则终止流程，不退回早期阶段。"""
    return {
        "action": "escalate",
        "target_role": "team_lead",
        "on_approve": current_stage + 1,  # 通过→下一阶段
        "on_reject": None,                # 拒绝→终止
        "on_info_needed": current_stage,  # 需补充→当前阶段重试
    }
```

#### Phase 2：UiPath平台实现层（第2周）

| 任务 | 文件 | 说明 |
|------|------|------|
| 2.1 LLM实现 | `platforms/uipath/uipath_llm.py` | 直接复用DeepSeek，或换UiPath AI Center |
| 2.2 卡片实现 | `platforms/uipath/uipath_card.py` | 实现CardInterface → Action Center Form JSON |
| 2.3 知识库实现 | `platforms/uipath/uipath_kb.py` | 实现KnowledgeBaseInterface → Data Service API |
| 2.4 消息实现 | `platforms/uipath/uipath_messaging.py` | 实现MessagingInterface → Orchestrator API |
| 2.5 平台入口 | `main_uipath.py` | 依赖注入，类似 `main_feishu.py` |
| 2.6 冒烟测试 | — | 跑通routing_logic的完整链路 |

#### Phase 3：BPMN编排（第3周）

| 任务 | 工具 | 说明 |
|------|------|------|
| 3.1 画BPMN图 | UiPath Maestro Studio | 6个Service Task + 6个User Task + Gateway |
| 3.2 Agent调用包装 | BPMN Service Task | 每个Agent调用包装为HTTP endpoint |
| 3.3 人工审批映射 | BPMN User Task | Action Center Form |
| 3.4 硬门禁映射 | BPMN Exclusive Gateway | scenario_verified检查 |
| 3.5 升级裁决映射 | BPMN Gateway分支 | 升级→通过/终止/补充 |
| 3.6 知识库入口映射 | BPMN Service Task | S1入口前调用KB检索 |
| 3.7 状态持久化 | UiPath Data Service | 流程状态存储 |
| 3.8 端到端测试 | — | 完整6阶段跑通 |

#### Phase 4：提交准备（第4周）

| 任务 | 说明 |
|------|------|
| 4.1 GitHub公开仓库 | MIT License，整理README |
| 4.2 Demo视频 | 展示完整链路 + 知识库自学习 + 编程Agent使用 |
| 4.3 PPT | 论坛模板，三段式叙事 |
| 4.4 UiPath Forum提交 | 项目描述+代码+视频+PPT |

### 3.3 BPMN流程图设计（预览）

```
⭕ 开始
  ↓
[Service Task: KB检索历史相似需求]
  ↓
[User Task: S1守门 — AI预填4字段，人确认/修正]
  ↓
◇ Gateway: S1 Verdict?
  ├─ approved → [Service Task: S2价值转化]
  ├─ info_needed → (回环S1，max 3轮)
  └─ rejected → ⭕ 结束(需求终止)

[Service Task: S2价值转化 — AI生成验收标准+测试用例]
  ↓
[User Task: S2 PM确认 — 人编辑后确认]
  ↓
◇ Gateway: S2 Verdict?
  ├─ approved → [Service Task: S3场景测试]
  ├─ escalate → [User Task: 组长裁决]
  │             ├─ approve → S3
  │             ├─ reject → ⭕ 结束
  │             └─ info → (回环S2)
  └─ rejected → ⭕ 结束

[Service Task: S3场景测试 — RD评估]
  ↓
[User Task: S3 RD审批]
  ↓
◇ Gateway: S3 Verdict? (同S2升级模式)
  ├─ approved → S4
  ├─ escalate → [User Task: 组长裁决]
  └─ rejected → ⭕ 结束

[Service Task: S4发版预判 — AI检查场景验证]
  ↓
[User Task: S4发布审批]
  ↓
◇ Gateway: 硬门禁检查
  ├─ scenario_verified=yes & approve → S5
  ├─ scenario_verified=no & approve → 🔒 BLOCKED (代码拦截)
  └─ reject → ⭕ 结束

[Service Task: S5反馈分析 — AI分析问卷]
  ↓
[Service Task: S6复盘 — AI全链路分析+知识库写入]
  ↓
⭕ 结束(完成)
```

### 3.4 回退机制改造对照

| 场景 | 当前代码 | 改后 | BPMN建模 |
|------|----------|------|----------|
| S2退回S1 | `get_rollback_target(2) → 1` | ❌ 取消。改为升级组长 | Gateway分支→终止 |
| S3退回S2 | `get_rollback_target(3) → 2` | ❌ 取消。改为升级组长 | Gateway分支→终止 |
| rollback_escalate (S3→S1) | 跨阶段回退 | ❌ 取消 | 不存在 |
| S1三轮追问 | 同阶段内循环 | ✅ 保留 | Loopback Gateway |
| 各阶段驳回 | 退回上一阶段 | 改为升级裁决→不通过则终止 | Gateway→End Event |
| rollback_abandon | 终止 | ✅ 保留 | End Event |
| rollback_retry | 回到当前阶段 | ✅ 保留 | Loopback Gateway |

---

## 四、风险矩阵

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| 沙盒审批延迟(5天) | 高 | 中 | 今天提交+领60天试用备选 |
| Action Center Form API不熟悉 | 中 | 中 | 参考UiPath文档，飞书卡片逻辑可平移 |
| Data Service查询能力不如Bitable | 中 | 低 | 知识库检索逻辑在core层，实现层可换 |
| BPMN Service Task调Python Agent | 中 | 中 | 包装为HTTP endpoint，BPMN标准支持 |
| 评委质疑"BPMN深度不足" | 中 | 中 | 用知识库自学习+硬门禁做差异化 |
| 回退改动影响现有测试 | 低 | 低 | harness测试框架已解耦，改适配器即可 |
| 29天内完不成 | 低 | 高 | 核心代码已跑通，只改实现层，风险可控 |

---

## 五、核心资产保留清单（提交时附录）

以下资产**完全不变**，是本项目的核心价值：

1. `agents/01-gatekeeper.md` — S1守门Agent（三轮追问机制）
2. `agents/02-value-transform.md` — S2价值转化Agent（验收标准+测试用例生成）
3. `agents/03-scenario-test.md` — S3场景测试Agent（技术方案评估）
4. `agents/04-release-review.md` — S4发版评审Agent（场景验证检查）
5. `agents/05-feedback-collect.md` — S5反馈收集Agent（问卷+聚类分析）
6. `agents/06-retrospective.md` — S6复盘Agent（全链路分析+知识库写入）
7. `schemas.md` — 6个JSON Schema契约
8. `schema_builder.py` — 规则引擎（verdict机械判定、纯算术计算）
9. `pipeline_rules.py` — 流转规则（硬门禁、S1重试限制）
10. `routing_logic.py` — 路由大脑（意图识别→检索→诊断→路由）
11. `knowledge_logic.py` — 知识库查询逻辑
12. `data_models.py` — 核心数据结构
13. `interfaces/*.py` — 4个平台抽象接口
14. `business-logic-spec.md` — 22章业务逻辑规格文档

---

## 六、Demo叙事结构

### 6.1 一句话Pitch

> Jira管理需求列表。我们管理需求**流转过程中的决策**——并把每次决策变成组织的永久记忆。

### 6.2 三段式

**第一段：痛点**
- 信息磨损：用户说"响应慢"，PM理解成"优化前端"，RD做成"压缩图片"
- 无效需求消耗研发：没有守门，RD排进sprint两周后才发现做错了
- 组织知识断层：员工离职经验归零，前人的坑后人继续踩

**第二段：解法**
- Relay层：6阶段流水线，AI预填→人确认，信息不失真
- IQ层：每次修正/驳回/决策自动入库，下次主动推送
- 硬门禁：场景未验证→代码级阻断

**第三段：为什么Track2**
- 确定性6阶段串行流程 = BPMN的教科书用例
- 每阶段Service Task(LLM Agent) + User Task(人确认) = Track2要求的"协调人+Agent+API"
- 知识库自学习 = Track2里几乎无人做的差异化
- "会学习的BPMN" = 别人的BPMN是静态的，你的是越跑越聪明的

### 6.3 Demo流程

1. 输入一条模糊需求 → S1 AI提取4字段 → 人修正 → 知识库弹出历史坑警告
2. S2 AI生成验收标准 → PM确认 → S3 RD评估
3. S4 硬门禁触发（场景未验证→阻断）→ 补充验证后通过
4. S5-S6 反馈分析+复盘 → 知识库自动写入13+知识点
5. 再输入一条类似需求 → 知识库主动推送上次教训

---

## 七、文件改造清单（精确到文件）

### 需要新建的文件

| 文件 | 说明 |
|------|------|
| `platforms/uipath/__init__.py` | 包初始化 |
| `platforms/uipath/uipath_llm.py` | LLM实现（复用DeepSeek或换AI Center） |
| `platforms/uipath/uipath_card.py` | CardInterface实现 → Action Center Form |
| `platforms/uipath/uipath_kb.py` | KnowledgeBaseInterface实现 → Data Service |
| `platforms/uipath/uipath_messaging.py` | MessagingInterface实现 → Orchestrator |
| `main_uipath.py` | UiPath平台入口（依赖注入） |
| `harness/adapters/uipath_routing.py` | UiPath测试适配器 |
| `bpmn/iq-relay-bpmn.xml` | BPMN 2.0流程定义（从Maestro导出） |
| `GITHUB_README.md` | GitHub公开仓库README |

### 需要修改的文件

| 文件 | 改动 |
|------|------|
| `core/pipeline_rules.py` | `get_rollback_target()` → 升级裁决逻辑，新增`get_escalation_target()` |
| `core/data_models.py` | 新增 `EscalationDecision` 数据结构 |
| `docs/business-logic-spec.md` | 第3节回退链改为升级裁决描述 |
| `harness/scenarios/` | 新增升级裁决场景测试 |
| `core/config.py` | 新增UiPath相关配置项 |

### 完全不动的文件

| 文件 | 原因 |
|------|------|
| `core/routing_logic.py` | 平台无关，零改动 |
| `core/knowledge_logic.py` | 平台无关，零改动 |
| `core/i18n.py` | 平台无关，零改动 |
| `interfaces/*.py` | 接口定义不变 |
| `agents/01~06.md` | Agent Prompt不变 |
| `schemas.md` | Schema契约不变 |
| `ai-requirement-pipeline/pipeline/schema_builder.py` | 规则引擎不变 |
| `ai-requirement-pipeline/pipeline/agent_runner.py` | LLM调用引擎不变 |
| `ai-requirement-pipeline/pipeline/pipeline_config.yaml` | 流程定义不变（回退逻辑在rules层改） |
