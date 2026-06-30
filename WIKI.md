# 🏆 UiPath AgentHack 2026 — 项目专用 Wiki

> **最后更新**: 2026年6月8日
> **队名**: MindTheGap
> **项目**: IQ Relay — Mind the information gap, knowledge gap, workflow gap

---

## 一、概览

| 项目 | 详情 |
|------|------|
| 全称 | UiPath AgentHack 2026 |
| 形式 | 🌐 纯线上，全球范围 |
| 平台 | [Devpost](https://uipath-agenthack.devpost.com) + [UiPath 社区论坛](https://forum.uipath.com) |
| 主题 | 构建生产级AI Agent，由 UiPath Automation Cloud 编排治理 |
| 团队 | 个人或 1~4 人 |
| 费用 | 🆓 免费 |
| 总时长 | 5月15日 → 7月7日（约7周，当前剩余约29天） |

---

## 二、关键日期

| 日期 | 事件 | 备注 |
|------|------|------|
| 5月15日 | 注册&提交开放 | Devpost上注册，提交方案表单 |
| **7月7日** | ⚠️ 最终提交截止 | Anywhere on Earth（AoE时间） |
| 7月15日 | 决赛入围公布 | 每赛道约10-12队入围 |
| 7月23日 | Zoom线上路演决赛 | 入围队伍向评委现场演示 |
| 8月4日 | 获奖公布 | 所有奖项正式公布 |

> **注意**: 有冲突信息称6月29日截止，以 Devpost 页面显示为准。建议按 **6月29日** 作为实际目标截止日，留出缓冲。

---

## 三、三大赛道详解

### 🛤️ Track 1: Maestro Case（动态工作流）

**一句话**: 处理路径不可预测的复杂业务流程，用 UiPath Case Management 编排。

| 维度 | 详情 |
|------|------|
| 核心理念 | Agentic Case Management |
| 流程特征 | 动态、异常密集、路径不可预测 |
| 关键要求 | 工作在各阶段流转，Agent/机器人/人之间交接，人在关键决策点保持控制 |
| 适用场景 | 保险理赔（进件→调查→理赔）、患者护理协调、贷款审批 |

**官方适用性描述**:
- 步骤顺序**不**完全确定
- 可能需要回退到早期阶段
- 异常频繁，需要复杂的人工干预
- 工作持续时间长（可能跨越数天/数周）

---

### 🛤️ Track 2: Maestro BPMN（顺序工作流）⭐ *我们的赛道*

**一句话**: 用 BPMN 2.0 建模结构化端到端流程，编排人、RPA、API、AI Agent。

| 维度 | 详情 |
|------|------|
| 核心理念 | Structured BPMN Automation |
| 流程特征 | 结构化、可预测、方向明确 |
| 关键要求 | BPMN 2.0 建模 + UiPath Maestro 编排 + 协调人/机器人/Agent/API |
| 适用场景 | 订单到现金系统、采购到付款发票验证循环 |

**官方详细要求**:
1. **编排平台**: UiPath Maestro 作为中央编排和治理层
2. **BPMN 2.0 标准**: 必须严格遵守 BPMN 2.0，使用任务/事件/网关构建流程逻辑
3. **端到端流程**: 从开始到结束建模并执行完整的结构化业务流程
4. **多角色协调**: BPMN 工作流必须无缝协调：
   - **人类** — 干预、审批、异常处理
   - **RPA 机器人** — 自动化任务执行和系统交互
   - **AI Agent** — 智能任务（数据处理、验证、决策支持）
   - **API** — 外部系统和服务集成
5. **可预测的流程逻辑**: 业务问题必须适合结构化 BPMN 自动化
6. **真实业务价值**: 解决切实的、现实世界的业务问题
7. **执行环境**: 必须在 UiPath Automation Cloud 上运行
8. **状态管理**: 展示对长时间运行流程的健壮状态管理（持久化与恢复）
9. **可审计追踪**: 提供清晰的、所有步骤和决策的可审计追踪
10. **开源提交**: 公开 GitHub 仓库 + MIT/Apache 2.0 协议

**官方适用性描述**:
- 步骤顺序已知且可重复
- 单次执行，相对短周期
- 异常不频繁，简单分支可处理
- **不需要回退到早期阶段重做**

---

### 🛤️ Track 3: Test Cloud（Agentic 测试）

**一句话**: 构建自主测试 Agent，重新定义软件质量保障。

| 维度 | 详情 |
|------|------|
| 核心理念 | Agentic QA & Testing |
| 流程特征 | AI驱动的测试设计、自动化、执行和管理 |
| 关键要求 | Agent 分析需求→写测试脚本→标记过时模块→推荐修复→验证 AI工作流 |
| 适用场景 | 测试用例生成、脆弱测试检测、变更影响分析、Agent 工作流验证 |

**具体用例**:
- 评估需求并转化为有意义的测试场景
- 在测试拖慢发布前，识别脆弱/过时测试
- 自动化中断时推荐修复方案
- 基于风险、覆盖率和变更影响编排正确的测试
- 验证复杂 AI 软件工作流
- 分析大量自动化测试运行结果
- 检测并修复不稳定测试（flaky tests）

---

## 四、提交要求

| 要求 | 说明 |
|------|------|
| 🔗 GitHub | 公开仓库，MIT 或 Apache 2.0 协议 |
| 🎥 Demo 视频 | 展示工作解决方案（编程 Agent 使用过程加分） |
| 📊 PPT 演示 | 论坛提供模板 |
| 🏗️ 架构 | **必须以 UiPath Automation Cloud 作为编排/治理层** |
| 🔌 外部框架 | LangChain / CrewAI / AutoGen / LLM 均可，鼓励使用 |
| 🚫 原创性 | 不能是 UiPath Marketplace 已有方案 |
| 📝 提交位置 | **UiPath 论坛**提交（非 Devpost） |

**提交内容清单**:
1. 项目简短描述
2. 代码（.zip / GitHub / 云盘链接，公开仓库优先）
3. Demo 视频
4. 完成填写的演示文稿（PPT模板）
5. 架构图/图表

**提交路径**: Devpost注册 → 方案表单 → UiPath Labs开发 → UiPath Forum提交

---

## 五、评判标准

### 五大维度

| 维度 | 权重 | 说明 |
|------|------|------|
| **Agentic Orchestration & Innovation** | ⭐⭐⭐⭐⭐ | Agent 编排的有效性、创新性、Agent 原则应用 |
| **Business Impact** | ⭐⭐⭐⭐ | 真实价值、ROI潜力、跨行业可行性 |
| **Technical Implementation** | ⭐⭐⭐⭐ | 可行性/可扩展性/适应性、UiPath生态利用率 |
| **Completeness** | ⭐⭐⭐ | MVP完整度、Demo质量、文档、打磨程度 |
| **Presentation** | ⭐⭐⭐ | 叙事清晰度、结构、Agent优势展示 |

### 额外加分

- ✅ **Demo/仓库中使用编程 Agent**（Claude Code, Codex, Cursor, Gemini CLI, UiPath Coding Agent 等）
- ✅ 有效使用 UiPath 生态组件（Agent Builder, Maestro, AI Center, Orchestrator, Test Suite, Automation Cloud）

### 社区投票

- 社区喜爱度投票占**决赛轮10%**
- 初评轮完全由评委打分，不受社区投票影响

---

## 六、奖金结构

### 总奖池：$50,000 — 16 个奖项

### 大奖

| 奖项 | 金额 | 说明 |
|------|------|------|
| 🥇 Agent of the Future（Grand Prize） | $10,000 | 全场最佳 |
| 🥈 1st place（Overall） | $6,000 | |
| 🥉 2nd place（Overall） | $4,000 | |
| 4th | 3rd place（Overall） | $2,500 |

### 特别奖（各 $2,000）

| 奖项 | 说明 |
|------|------|
| Business-ready agent | 最接近生产就绪 |
| Innovative agentic workflow | 最具创新性流程 |
| Impactful agent | 最具商业影响力 |
| Advanced agent | 技术最先进 |

### 跨赛道奖励（各 $1,500）

| 奖项 | 说明 |
|------|------|
| Community favorite | 社区最喜爱 |
| Rising star | 最佳新星 |
| Best use of UiPath Agent Builder | Agent Builder最佳使用 |
| Best cross-platform integration | 最佳跨平台集成 |
| Best product feedback | 最佳产品反馈 |

### 非物质奖励

- 🏅 所有决赛入围者：UiPath AgentHack 证书 + 创新卓越徽章
- 🎫 获奖者：UiPath 认证代金券
- 🌍 获奖方案：UiPath Marketplace 展示 + 全球 UiPath 活动（如 FUSION）展示机会
- 📣 优胜方案在 UiPath 社区论坛展示

---

## 七、沙盒获取流程

### 完整步骤（共4步）

| 步骤 | 操作 | 详情 |
|------|------|------|
| **1. 注册** | 打开 [uipath-agenthack.devpost.com](https://uipath-agenthack.devpost.com) | 点击 Register，创建 Devpost 账号（已有则登录） |
| **2. 提交方案** | 填写 Idea Submission 表单 | 需包含：方案描述、构建计划、所有队员邮箱 |
| **3. 等待审批** | UiPath 团队审核方案 | 审核标准：是否展示 Agent 自动化潜力、是否适合赛事 |
| **4. 获取访问** | 审批通过后2-5工作日 | 邮件邀请你加入 UiPath Organization（Staging环境），管理员权限，沙盒自带 Agentic & AI 单元 |

### 沙盒包含什么

- ✅ UiPath Automation Cloud 租户（Staging 环境）
- ✅ Agentic Units（用于 Agent Builder 等）
- ✅ AI Units（用于 AI Center、Document Understanding 等）
- ✅ UiPath Maestro（流程编排）
- ✅ UiPath Action Center（人工任务）
- ✅ UiPath Orchestrator（治理监控）
- ✅ UiPath Data Service（数据存储）
- ✅ UiPath Test Suite（测试工具）
- ✅ 管理员权限（可配置集成）

### 注意事项

- ⚠️ 必须是**新方案**，不能是 UiPath Marketplace 已有的
- ⚠️ 方案需要体现 **Agent 自动化潜力**
- 📧 如遇问题联系：**andreea.tomescu@uipath.com**
- ⚠️ 审批可能需要**最多5个工作日**，尽早提交！

---

## 八、BPMN 2.0 快速入门

### 是什么

BPMN（Business Process Model and Notation）是业务流程建模的**国际标准图形化语言**。用流程图的方式描述业务流程，所有人都能看懂。

### 核心四要素

```
┌────────────────────────────────────────────────┐
│ 1. 流程对象 (Flow Objects)                      │
│    • 事件(⭕): 开始/中间/结束                    │
│    • 活动(▭): 任务/子流程                        │
│    • 网关(◇): 决策分支/合并/并行                  │
├────────────────────────────────────────────────┤
│ 2. 连接对象 (Connecting Objects)                │
│    • 顺序流(→): 任务执行顺序                     │
│    • 消息流(⇢): 跨泳道消息传递                   │
├────────────────────────────────────────────────┤
│ 3. 泳道 (Swimlanes)                            │
│    • 池(Pool): 组织边界                          │
│    • 道(Lane): 部门/角色/系统                    │
├────────────────────────────────────────────────┤
│ 4. 辅助元素 (Artifacts)                         │
│    • 数据对象、群组、注释                         │
└────────────────────────────────────────────────┘
```

### 常见任务类型

| 任务图标 | 类型 | 用途 | 我们的映射 |
|----------|------|------|-----------|
| 👤 | User Task | 需要人工操作（通过UI） | 需求审批确认 |
| ⚙️ | Service Task | 系统自动执行（调API/Agent） | LLM Agent调用 |
| 📜 | Script Task | 执行脚本 | Schema校验 |
| ◇ | Exclusive Gateway | 二选一分支 | 审批通过/驳回 |
| ◇+ | Parallel Gateway | 并行分支 | 多角色同时评审 |

### 你的项目 → BPMN 映射

```
开始 → [Service: AI守门分析] → [Gateway: 通过?] ──是→ [Service: AI价值转化] → ...
                                    ↓否
                              [User: 人工完善后重新提交] → (回环)
```

每个 Agent 阶段 = **Service Task**（调用 LLM Agent）
每个人工确认 = **User Task**（通过 Action Center）
每个驳回判断 = **Exclusive Gateway**（条件分支）
整个流程 = **Pool**，AI Agent / 人工审核 = 不同的 **Lane**

---

## 九、IQ Relay × Track2 适配分析

### 项目概要

**项目名**: IQ Relay
**核心理念**: 两层架构——**Relay**（流转，让需求不失真）+ **IQ**（记忆，让组织越跑越聪明）

### Relay 层：6阶段审批流水线

```
自然语言需求
    ↓
┌──────────────────────────────────────────────────────────────────┐
│ S1 守门分析                                                       │
│ AI: 从自然语言提取4个结构化字段（谁、什么场景、什么问题、期望结果）      │
│ 机制: 三轮追问 → 信息仍不足则强制拒绝                                │
│ 人: 确认/修正/驳回（驳回→理由入库，回退链: 通知→修改→重提）           │
│ verdict: 通过 / 拒绝 / 需补充                                      │
│     ↓ (通过)                                                      │
│ S2 价值转化                                                       │
│ AI: 生成验收标准 + 测试用例                                        │
│ 人: PM 可编辑后确认，或驳回（理由入库）                               │
│     ↓ (通过)                                                      │
│ S3 研发评估                                                       │
│ AI: 技术方案 + 工作量预估                                          │
│ 人: RD 填写/修正，可退回 PM 并写明原因（理由入库）                    │
│     ↓ (通过)                                                      │
│ S4 发布审批（硬门禁）                                              │
│ AI: 检查客户场景验证状态                                            │
│ 硬门禁: 场景未真实验证 → 代码层面强制阻断，不可绕过                   │
│ 人: 条件满足后确认放行                                              │
│     ↓ (通过)                                                      │
│ S5 反馈收集                                                       │
│ AI: 设计用户调研问卷，收集和聚类反馈                                 │
│ 人: 确认反馈分类/优先级                                             │
│     ↓                                                              │
│ S6 流程复盘                                                       │
│ AI: 分析整条流水线全链路数据，提取规律，写入知识库                     │
│ 人: 确认复盘结论                                                    │
└──────────────────────────────────────────────────────────────────┘
```

### IQ 层：自学习知识库

| 机制 | 说明 |
|------|------|
| 自动沉淀 | 每次流转输出 + 每次拒绝原因 + 每次回退理由 → 全量自动入库 |
| 无需人工 | 不依赖人写文档，不需要重新训练模型 |
| 主动推送 | 新需求进入流水线前，语义检索历史，弹出"历史坑"警告 |
| 语义搜索 | `?关键词` 直接查历史经验 |
| 写入密度 | 每次完整流转至少写入 **13个知识点** |
| 统一 Schema | 阶段输出 / 人工修改 / 拒绝原因 / 复盘结论 分类归档 |

### 交互层

- 可编辑表单卡片：AI 预填 + 人工修改，所有阶段可交互
- 回退通知卡：显示被退回原因、回退次数、可选操作（**重试** / **上退** / **放弃**）
- Session TTL：15 分钟无操作自动过期

### 当前技术栈（全部可替换）

| 层 | 当前实现 | 设计上可替换为 |
|----|----------|---------------|
| LLM | DeepSeek（OpenAI 兼容协议） | GPT-4 / Claude / Gemini / Ollama |
| 知识库 | Azure AI Search | Elasticsearch / Pinecone / Weaviate / pgvector |
| 消息层 | Bot Framework（Teams） | Slack Bolt / Discord / Telegram / REST API |
| 卡片层 | Adaptive Cards | Slack Block Kit / Discord Embeds / Web UI |
| 编排层 | Python Pipeline Orchestrator | **→ UiPath Maestro（本次迁移目标）** |
| 用户查询 | Microsoft Graph | 任意 LDAP / 企业通讯录 API |

---

### 逐条对照 Track2 官方要求

| # | Track2 要求 | 匹配度 | 客观分析 |
|---|------------|--------|----------|
| 1 | BPMN 2.0 建模 | ⚠️ 需补 | 当前 Python 编排。但逻辑天然可映射：6阶段→6个 BPMN Task；S1三轮追问→Loop Gateway；S4门禁→Exclusive Gateway；回退链→Loopback。逻辑与 BPMN 同构，"画出来"即可。 |
| 2 | UiPath Maestro 编排 | ⚠️ 需补 | 当前自研 Pipeline Orchestrator。需迁移到 Maestro 上作为 BPMN 图执行。这是本次参赛的核心改造工作。 |
| 3 | 协调人类 | ✅ 完全匹配 | 每阶段都是 "AI 预填 → 人确认或驳回"模式。S1 三轮追问、S3 RD 可退回 PM——人类在关键决策点保持控制，正是 Track2 描述的 human-in-the-loop。 |
| 4 | 协调 AI Agent | ✅ 完全匹配 | 6个阶段 = 6个独立 AI Agent，各有独立 system prompt、职责边界、输出 Schema。是真正的 Multi-Agent 协作，不是单 LLM 调用。 |
| 5 | 协调 RPA 机器人 | ⚠️ 未覆盖 | 当前流程以"人 + AI Agent"为主，没有显式的 RPA 机器人。但 Track2 要求的是"协调这些角色"，不要求全部出现。Schema 校验、CSV 解析等脚本任务可包装为 RPA Bot/ Script Task 补充。 |
| 6 | 协调 API | ✅ 已覆盖 | LLM API（DeepSeek）+ 知识库 API（Azure AI Search）+ 用户查询 API（Microsoft Graph）+ 消息 API（Bot Framework）。多外部系统集成，满足 Track2 的 API 协调要求。 |
| 7 | 可预测流程 | ✅ 完全匹配 | 6阶段固定顺序、固定 Schema、不可跳过任何阶段——是高度确定性的 "known and repeatable" 流程，Track2 的精准描述。 |
| 8 | 端到端流程 | ✅ 完全匹配 | 从自然语言需求输入到 S6 复盘报告输出，完整闭环。Track2 要求 "complete, structured business process from start to finish"。 |
| 9 | 状态管理 | ⚠️ 需补 | 当前：per-user session + Schema 级联透传 + Session TTL 15min。缺少：流程中断后的持久化与恢复。需借助 UiPath Orchestrator 的长流程状态管理补齐。 |
| 10 | 可审计追踪 | ✅ 超额匹配 | 知识库本身就是完整的审计追踪——每阶段谁做了什么决策、修正了什么、因何被驳回，全链路可回溯。超过 Track2 的基本审计要求。 |
| 11 | 开源 | ⚠️ 需补 | PoC 阶段未公开。提交时需创建 GitHub 公开仓库 + MIT 或 Apache 2.0 协议。 |

### 匹配度总评

| 类别 | 数量 | 明细 |
|------|------|------|
| ✅ 完全匹配 | 7/11 | 协调人类、AI Agent、API、可预测流程、端到端、状态管理基础、审计追踪 |
| ⚠️ 需补（低成本） | 4/11 | BPMN 建模、Maestro 编排、RPA 补充、开源 |
| ❌ 冲突 | 0/11 | 无 |

> **结论：IQ Relay 的核心架构与 Track2 本质上同构。** 缺失的4项全部是"载体替换"——把 Python 编排换成 BPMN 图、把 Teams 换成 Action Center、把 Azure AI Search 换成 Data Service。核心的 6 Agent 流水线逻辑和自学习知识库机制完全不动。

---

### 关键质疑：Track1 还是 Track2？

Track2 官方描述中有一条约束：

> "there is no need to return to earlier phases for rework"

IQ Relay 有驳回/回退机制，是否存在冲突？

**逐场景拆解**:

| 场景 | 行为 | BPMN 兼容性 | 分析 |
|------|------|------------|------|
| S1 三轮追问后强制拒绝 | 在当前阶段内循环（追问→补充→再评估，最多3轮） | ✅ 标准 BPMN Loopback | 不跨阶段，属于同一 Task 内的重试 |
| 各阶段人驳回 | 走回退链：通知→修改→**重提同一阶段** | ✅ 标准 BPMN Loopback | 驳回后回到当前阶段起点，不往回跳 |
| 回退通知卡 → "重试" | 修改后重新提交当前阶段 | ✅ 标准 BPMN Loopback | 单阶段内重试 |
| 回退通知卡 → "放弃" | 终止流水线 | ✅ BPMN End Event | 正常终止路径 |
| 回退通知卡 → "上退" | 含义待确认 | ⚠️ 需明确 | 如果指"向上级汇报/升级决策"→ ✅ 正常分支。如果指"退回上一阶段"→ ❌ 进入 Track1领地 |

> **上退** 的确切含义需要在你的代码中确认。但从设计逻辑看，更可能是"升级/上报"而非"退到上一阶段"——因为各阶段有独立职责边界，跨阶段回退不具备业务合理性。

**结论**: 只要"上退"的含义不是跨阶段回退，IQ Relay 就**完全适合 Track2**。否则需考虑 Track1 或在 Track2 中简化回退选项。

---

### 需要改什么

#### 保留不动（核心资产）

| 资产 | 说明 |
|------|------|
| `agents/01-06` 的 Agent Prompt | 每个阶段的 Agent 职责定义、输出 Schema 不变 |
| `agent_runner.py` 的 tool_use 循环 | LLM 调用 + JSON 提取 + Schema 验证逻辑不变 |
| `schemas.md` 的 6 个 Schema 契约 | 阶段间数据接口不变 |
| 知识库统一 Schema | 13+知识点的分类归档结构不变 |

#### 替换（飞书/Teams → UiPath 原生）

| 当前 | 迁移为 | 复杂度 |
|------|--------|--------|
| 消息路由层（Bot Framework + `?`命令） | UiPath Orchestrator 队列 + Action Center 触发器 | ⭐⭐ |
| 可编辑表单卡片（Adaptive Cards） | UiPath Action Center Form | ⭐⭐ |
| 回退通知卡 | UiPath Action Center Task 状态通知 | ⭐ |
| 状态管理（per-user session） | UiPath Orchestrator Job 状态 + Data Service 持久化 | ⭐⭐ |
| 知识库读写（Azure AI Search） | UiPath Data Service + 可选 AI Center/外部向量库 | ⭐⭐ |

#### 新增

| 产出 | 说明 |
|------|------|
| BPMN 2.0 流程图 | 在 UiPath Maestro Studio 中绘制 6 阶段 + Gateway + Loopback |
| GitHub 公开仓库 | MIT License |
| Demo 视频 | 展示完整流转 + 知识库自学习 + 编程 Agent 使用过程 |
| PPT 演示 | 使用论坛模板 |

#### 架构迁移对比

```
当前架构                          迁移后架构
─────────────────────────────────────────────────────
消息层: Bot Framework (Teams)  →  Action Center / Orchestrator
卡片层: Adaptive Cards         →  Action Center Forms
编排层: Python Orchestrator    →  UiPath Maestro (BPMN)
知识库: Azure AI Search        →  UiPath Data Service
───────────────────────────────────────────────────── (不变)
Agent层: 6个Agent Prompt        →  完全保留
LLM调用: DeepSeek (OpenAI兼容)  →  完全保留（或按需切换）
Schema层: 6个JSON Schema        →  完全保留
规则引擎: schema_builder.py     →  包装为 BPMN Script Task
```

---

### 差异化亮点

**1. "会学习的 BPMN"——组织知识不丢失**

> 传统 BPMN：画流程图 → 执行 → 结束。下次同样错误继续犯。
> IQ Relay：每次驳回原因、每次人工修正、每个阶段决策 → **自动结构化沉淀**。下次类似需求进来 → 知识库主动推送历史教训。
>
> 每次完整流转写入至少 13 个知识点，无需人工归档。

这是 Track2 中的降维打击——别人的 BPMN 是**静态流程图**，你的是**越跑越聪明的 BPMN**。

**2. 两层架构叙事清晰**

> Relay（流转）解决当下——信息不失真、不浪费资源。
> IQ（记忆）解决未来——员工离职知识不丢失，组织越跑越快。
>
> 两条主线各自清晰，合在一起形成完整竞争力。评委和 Demo 观众一眼就能理解。

**3. 硬门禁展示 BPMN 决策能力**

> S4 Exclusive Gateway：客户场景未真实验证 → 代码级阻断。
> 不是软提醒，不是"建议回头补"——是真阻断。展示了 BPMN Gateway 不只是路由工具，而是**执行治理规则**。

**4. 全栈可替换设计 = 架构成熟度**

> LLM、知识库、消息层、卡片层均可独立替换。这不是为了比赛造的"一次性代码"，而是有真实工程考量的产品级设计。展示给评委看的就是"我们的系统有完整的分层架构"。

**5. 编程 Agent 加分**

> Demo 中展示用 Claude Code 编写 UiPath 测试脚本、生成 BPMN XML——直接命中加分项。

---

### 项目叙事结构（用于方案表单和 PPT）

**一句话 Pitch**:
> Jira 和 Linear 管理需求。我们不管理需求——我们管理**需求流转过程中的决策**，并把每次决策变成组织的永久记忆。

**三段式叙事**:
1. **痛点** — 信息磨损、无效需求消耗研发、员工离职知识归零
2. **解法** — Relay 切断磨损 + IQ 沉淀经验
3. **为什么 Track2** — 这是确定性的多阶段人机协同流水线，BPMN 是其天然建模语言

---

### 风险与应对

| 风险 | 等级 | 应对 |
|------|------|------|
| 沙盒审批延迟 | ⚠️ 中 | 今天提交方案；同时领 60 天免费试用 Automation Cloud 做备选 |
| Maestro BPMN 学习 | ⭐ 低 | 可视化拖拽，核心逻辑已跑通，只需"画"出来 |
| Action Center Form 布局迁移 | ⭐⭐ 中 | Adaptive Cards → Action Center Form，布局逻辑平移 |
| "上退"含义不清晰 | ⚠️ 中 | 先在你的代码中确认。如是"升级"则无问题；如是"退上一阶段"则 Demo中简化为此选项不触发实际跳回 |
| 知识库检索如何嵌进 BPMN 流程 | ⭐⭐ 中 | 在 S1 入口处作为 Service Task 调用知识库 API，结果回显到 User Task 表单 |
| Python Agent 循环嵌入 BPMN | ⭐⭐ 中 | 包装为 HTTP endpoint Service Task。BPMN 标准支持，非 hack

---

## 十、参考链接

| 资源 | 链接 |
|------|------|
| Devpost 主页 | https://uipath-agenthack.devpost.com |
| UiPath 社区论坛 | https://forum.uipath.com |
| UiPath Maestro 文档 | https://docs.uipath.com/maestro |
| UiPath BPMN 指南 | https://docs.uipath.com/maestro/bpmn |
| UiPath Action Center | https://docs.uipath.com/action-center |
| UiPath Data Service | https://docs.uipath.com/data-service |
| 联系我们 | andreea.tomescu@uipath.com |

---

> 📌 **下一步行动**: 1) 注册 Devpost → 2) 提交方案表单 → 3) 领沙盒 → 4) 画 BPMN 图 → 5) 改造交互层 → 6) 集成测试 → 7) 录 Demo + PPT → 8) 论坛提交
