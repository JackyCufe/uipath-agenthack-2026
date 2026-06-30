# MindTheGap — AI Requirement Pipeline for UiPath AgentHack 2026

> **Agentic Case Management for Enterprise Requirement Pipeline** — 6 AI Agents that close the information gap, knowledge gap, and workflow gap in product teams.

## 🎯 Problem

Enterprise product teams suffer from three gaps:
- **Information Gap**: Sales collects vague requirements → engineering builds the wrong thing
- **Knowledge Gap**: Lessons learned are lost between projects → same mistakes repeat
- **Workflow Gap**: No structured approval flow → ad-hoc decisions, no traceability

## 💡 Solution

MindTheGap is a 6-stage AI-powered requirement pipeline where each stage pairs an **AI Agent** with a **human confirmation** step:

| Stage | AI Agent | Human Confirm | Gate |
|-------|----------|---------------|------|
| S1 | Gatekeeping Agent — extracts 4 structured fields from raw text | Sales confirms | Verdict: approved / info_needed / rejected |
| S2 | Value Transform Agent — structures PM acceptance criteria + test cases | PM confirms | Verdict: approved / escalate / rejected |
| S3 | Scenario Test Agent — generates customer-perspective test cases | Dev confirms | Verdict: approved / escalate / rejected |
| S4 | Release Review Agent — applies P0/P1/P2 rubric | Product Lead confirms | Hard Gate: verified / blocked |
| S5 | Feedback Analysis Agent — collects & analyzes customer feedback | — | — |
| S6 | Retrospective Agent — calculates ROI, writes to knowledge base | — | — |

### Key Innovation: Hard Gate
Stage 4 enforces a **hard gate** — customer scenarios must be verified. Any P0 failure blocks release, no exceptions. This prevents shipping features that work in theory but fail in real customer scenarios.

### Knowledge Loop
Stage 6 writes lessons learned back to the knowledge base. Stage 1 of the next requirement searches this KB — creating a **self-improving organizational memory**.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   UiPath Maestro BPMN                     │
│  (Orchestration: Service Tasks → HTTP, User Tasks →       │
│   Action Center, Gateways → Conditional Routing)          │
└──────────────┬──────────────────────────┬────────────────┘
               │                          │
    HTTP POST  │                          │  Action Center
               ▼                          ▼
┌──────────────────────┐    ┌─────────────────────────┐
│  FastAPI Server       │    │  UiPath Action Center    │
│  (api_server.py)      │    │  (Human confirmation      │
│                       │    │   forms for S1/S2/S3)     │
│  6 endpoints:         │    └─────────────────────────┘
│  /api/kb-search       │
│  /api/s1/gatekeep     │
│  /api/s2/transform    │
│  /api/s3/test-cases   │
│  /api/s4/release      │
│  /api/s5/feedback     │
│  /api/s6/retrospective│
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  AI Agent Runner      │
│  (agent_runner.py)    │
│                       │
│  DeepSeek LLM +       │
│  Tool Use Loop        │
│  6 Agent Prompts      │
│  Schema Builder       │
│  Embedding Search     │
└──────────────────────┘
```

### Three-Layer Decoupled Architecture

1. **Interface Layer** (`interfaces/`) — 4 abstract base classes (LLM, Card, Messaging, KnowledgeBase)
2. **Platform Layer** (`platforms/uipath/`) — UiPath-specific implementations
3. **Core Layer** (`pipeline/`) — Agent runner, schema builder, config — platform-agnostic

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- UiPath Automation Cloud account
- DeepSeek API key (or any OpenAI-compatible LLM)

### 1. Start the API Server

```bash
cd band-of-agents/ai-requirement-pipeline/pipeline

# Set your LLM API key
export DEEPSEEK_API_KEY=your_key_here

# Install dependencies
pip install fastapi uvicorn pydantic openai

# Start the server
uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Expose to Internet (for UiPath Cloud)

```bash
ngrok http 8000
```

### 3. Import BPMN to UiPath Studio

1. Open UiPath Studio Web → Maestro BPMN
2. Import `requirement_pipeline_en.bpmn`
3. Configure each Service Task with HTTP Request to your ngrok URL
4. Configure User Tasks with Action Center forms
5. Configure Gateway conditions
6. Publish

### 4. Debug

Use Debug step-by-step in UiPath Studio to walk through the pipeline.

## 📁 Project Structure

```
band-of-agents/
├── ai-requirement-pipeline/
│   ├── agents/                 # 6 AI Agent system prompts
│   │   ├── 01-gatekeeper.md
│   │   ├── 02-value-transform.md
│   │   ├── 03-scenario-test.md
│   │   ├── 04-release-review.md
│   │   ├── 05-feedback-collect.md
│   │   └── 06-retrospective.md
│   ├── pipeline/
│   │   ├── api_server.py       # FastAPI bridge for UiPath
│   │   ├── agent_runner.py     # LLM + tool use loop
│   │   ├── schema_builder.py   # Schema assembly + validation
│   │   ├── config.py           # LLM & pipeline config
│   │   ├── tools.py            # Agent tool definitions
│   │   ├── people_map.py       # Role mapping
│   │   ├── pipeline_config.yaml
│   │   └── requirement_pipeline_en.bpmn  # BPMN 2.0 XML
│   ├── interfaces/             # 4 abstract base classes
│   ├── platforms/uipath/       # UiPath platform implementations
│   └── docs/                   # Documentation
├── core/                       # Business logic (routing, rules, i18n)
└── harness/                    # Test scenarios
```

## 🧪 Test Scenarios

- **Happy Path**: Start → S1 approved → S2 approved → S3 approved → S4 verified → S5 → S6 → End
- **Info Loop**: S1 info_needed → sales provides more info → S1 approved
- **Escalation**: S2 rejected → Team Lead decision → approve to S3
- **Hard Gate Block**: S4 P0 failure → blocked → End

## 🏆 UiPath AgentHack 2026

**Track**: Agentic Case Management (Track 2)

**Key Features for Judges**:
- ✅ BPMN 2.0 process modeled in UiPath Maestro
- ✅ 6 AI Agents with tool-use capability
- ✅ Human-in-the-loop via Action Center
- ✅ Hard gate enforcement (no P0 bypass)
- ✅ Knowledge base write-back loop
- ✅ Three-layer decoupled architecture

## 📄 License

MIT License — see [LICENSE](LICENSE)

## Team

Built for UiPath Global AgentHack 2026.
