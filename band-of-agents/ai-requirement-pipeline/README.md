# AI需求链

> 傅盛AI战队·青少年黑客松 2026
> Demo 页面：https://hackathon-ai-team.pages.dev
> 提交截止：2026-05-10 24:00（已提交）

---

## 背景

猎户星空产研团队的真实痛点：需求从销售口头描述进来，经过产品、研发、测试，到最终发版，每个环节都在信息衰减——测试不知道客户场景，PM 不清楚验收标准，版本发完没有闭环。

灵感来源：2026-04-27 公司产品规划会议原文。

---

## 系统架构

```
原始需求输入（飞书消息触发）
    │
    ▼
01 守门 Agent        → 结构化四问表单，缺一不可，拦截伪需求
    │ 飞书卡片 ← 售前/PM 审批
    ▼
02 价值转化 Agent    → 定义可交付验收标准，明确交付价值
    │ 飞书卡片 ← PM 确认
    ▼
03 研发自测 Agent    → 生成自测检查清单，高质量提测
    │ 飞书卡片 ← 研发自测确认
    ▼
04 测试发版 Agent    → 基于客户场景验证，评估发版标准
    │ 飞书卡片 ← 测试/负责人发版决策
    ▼
05 反馈收集 Agent    → 结构化问卷收集客户真实反馈
    ▼
06 复盘分析 Agent    → AI 分析全链路数据，识别瓶颈，生成复盘报告
    ▼
飞书多维表格归档（全链路可追溯）
```

---

## 技术栈

| 层次 | 技术 |
|------|------|
| LLM | Claude Sonnet (via LiteLLM Proxy → Vertex AI) |
| Agent 框架 | 原生 Anthropic SDK tool_use 循环 |
| 人机交互 | 飞书交互卡片 + lark-oapi WebSocket 长连接 |
| 数据归档 | 飞书多维表格 Bitable |
| Demo 展示 | 静态 HTML（Cloudflare Pages） |

---

## 项目结构

```
hackathon-ai-team/
├── agents/                      # 6 个 Agent 的 system prompt
│   ├── 01-gatekeeper.md
│   ├── 02-value-transform.md
│   ├── 03-scenario-test.md
│   ├── 04-release-review.md
│   ├── 05-feedback-collect.md
│   └── 06-retrospective.md
├── pipeline/                    # Python 执行层
│   ├── pipeline.py              # 主流程编排
│   ├── agent_runner.py          # Agent 执行 + tool_use 循环
│   ├── tools.py                 # 飞书 API 工具（发消息/写 Bitable）
│   ├── card_templates.py        # 飞书交互卡片模板
│   ├── card_handler.py          # WebSocket 长连接，等待卡片点击
│   ├── config.py                # 环境配置
│   ├── people_map.py            # 角色 → 飞书 open_id 映射
│   ├── demo.py                  # Demo 入口（3条示例需求）
│   └── requirements.txt
├── demo/
│   ├── index.html               # 展示页（Cloudflare Pages 部署）
│   └── demo.mp4                 # 演示视频（21MB，已压缩）
├── data/
│   └── demo_output.json         # 真实 Pipeline 运行输出
├── docs/                        # 过程文档（参考用）
│   ├── build-log-2026-05-08.md
│   ├── session-recap-2026-05-08.md
│   ├── demo-inputs.md
│   ├── feishu-permissions-checklist.md
│   ├── requirement-table-analysis.md
│   ├── rubrics.md
│   └── hackathon-ai-enterprise-efficiency-team.md
├── schemas.md                   # Agent 间 JSON 数据契约
├── pipeline.zip                 # 参赛提交压缩包
└── README.md
```

---

## 运行方式

### 依赖安装

```bash
cd pipeline
pip install -r requirements.txt
```

### 前置条件

1. **LiteLLM Proxy** 在本地 `http://127.0.0.1:4000` 运行，路由到 Vertex AI Claude Sonnet
2. **飞书机器人** 已配置 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`（见 `config.py`）

### 运行

```bash
# DEMO 模式（无需飞书账号，终端打印验证逻辑）
DEMO_MODE=true python demo.py

# 真实模式（飞书卡片审批 + Bitable 归档）
python demo.py
```

---

## 设计原则

1. **源头质量优先**：守门不通过，需求不进系统
2. **人机协同**：AI 生成结构化建议，人类在关键节点审批
3. **结构化胜过自由发挥**：每个 Agent 输出 Schema JSON，全链路可追溯
4. **全链路闭环**：从需求录入到复盘分析，每个版本都有完整记录

---

Built by 吕嘉琪 · 傅盛AI战队 · 黑客松 2026
