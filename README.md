# MindTheGap — Agentic Requirement Pipeline for UiPath

> Closing the information gap, knowledge gap, and workflow gap in enterprise product teams through 6 AI agents coordinated by BPMN.

## 🎯 Problem

Enterprise requirement management suffers from three gaps:

1. **Information Gap** — Sales captures vague requirements; engineers build the wrong thing
2. **Knowledge Gap** — Hard-won lessons from past projects don't feed back into future requirements
3. **Workflow Gap** — Approval gates exist on paper but aren't enforced mechanically

## 🏗️ Solution

A 6-stage AI-powered requirement pipeline where each stage pairs an **AI Agent** (Service Task) with a **Human Confirmation** (User Task):

| Stage | AI Agent (Service Task) | Human (User Task) | Gateway |
|-------|------------------------|-------------------|---------|
| **S0** | KB Search History | — | — |
| **S1** | AI Gatekeeping — extracts 4 structured fields, verdict | Sales Confirm | approved / info_needed (loop max 3) / rejected |
| **S2** | AI Value Transform — structures PM acceptance criteria | PM Confirm | approved / escalate / rejected |
| **S3** | AI Test Case Generation — customer-perspective test cases | Dev Confirm | approved / escalate / rejected |
| **S4** | AI Release Review — P0/P1/P2 rubric, hard gate | Product Lead Confirm | verified / blocked |
| **S5** | AI Feedback Analysis — customer satisfaction | — | — |
| **S6** | AI Retrospective + KB Write — ROI, next version, knowledge base | — | — |

### Key Innovations

- **Hard Gate Enforcement**: Customer scenario must be verified. Any P0 failure = blocked, no exceptions.
- **Escalation, not Rollback**: Rejected items escalate to Team Lead (BPMN-compatible), not roll back (BPMN-violating).
- **Knowledge Feedback Loop**: S6 writes lessons to KB → S0 retrieves them for next requirement.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│              UiPath Maestro BPMN                     │
│  (Process orchestration, gateways, human tasks)      │
└──────────────┬──────────────────────────────────────┘
               │ HTTP (ngrok tunnel)
               ▼
┌─────────────────────────────────────────────────────┐
│           FastAPI Server (Python)                    │
│  6 endpoints → 6 AI Agents                           │
└──────────────┬──────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────┐
│         AI Agent Engine (agent_runner.py)            │
│  Tool-use loop with DeepSeek LLM                     │
│  6 agent prompts (01-gatekeeper ~ 06-retrospective)  │
└──────────────┬──────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────┐
│    Schema Builder + Embedding Search + Storage       │
│  Structured data handoff between stages              │
└─────────────────────────────────────────────────────┘
```

## 📁 Project Structure

```
band-of-agents/
├── ai-requirement-pipeline/
│   ├── agents/                    # 6 AI Agent system prompts
│   │   ├── 01-gatekeeper.md
│   │   ├── 02-value-transform.md
│   │   ├── 03-scenario-test.md
│   │   ├── 04-release-review.md
│   │   ├── 05-feedback-collect.md
│   │   └── 06-retrospective.md
│   ├── pipeline/
│   │   ├── api_server.py          # FastAPI — 6 endpoints for BPMN
│   │   ├── agent_runner.py        # LLM tool-use loop
│   │   ├── schema_builder.py      # Schema assembly + validation
│   │   ├── config.py              # LLM provider config
│   │   ├── tools.py               # Agent tools (gatekeeping, transform)
│   │   ├── people_map.py          # Role mapping
│   │   ├── requirement_pipeline_en.bpmn  # BPMN 2.0 XML for UiPath
│   │   └── search/
│   │       └── embedding_search.py # Semantic KB search
│   └── pipeline_config.yaml       # 6-stage configuration
├── interfaces/                    # Platform-agnostic ABCs
│   ├── llm.py
│   ├── card.py
│   ├── messaging.py
│   └── knowledge_base.py
└── core/
    ├── pipeline_rules.py          # Hard gate, escalation logic
    └── routing_logic.py           # Feedback routing
```

## 🚀 Quick Start

### 1. Install dependencies

```bash
pip install fastapi uvicorn pydantic openai
```

### 2. Configure LLM

Create `band-of-agents/ai-requirement-pipeline/pipeline/.env`:

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
```

### 3. Start the API server

```bash
cd band-of-agents/ai-requirement-pipeline/pipeline
uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Expose to internet (for UiPath Cloud)

```bash
ngrok http 8000
```

### 5. Import BPMN into UiPath Studio

1. Open UiPath Studio Web → Maestro BPMN
2. Open XML tab → paste contents of `requirement_pipeline_en.bpmn`
3. Configure each Service Task: Action = Execute HTTP request, Method = POST, URL = `https://<your-ngrok>/api/<endpoint>`
4. Configure each Gateway with condition expressions (e.g., `verdict == "approved"`)
5. Configure each User Task with SpecificContent (form data for Action Center)
6. Publish → Debug → Run

## 📊 Demo Scenario

The pipeline processes a real-world requirement:

> **Customer**: Acme Corp (IT director James Park)
> **Need**: Reception bot multi-language auto-detection (EN/CN/JP/KR/ES)
> **Expected**: 30% satisfaction increase, 50% less escalation tickets

The demo walks through all 6 stages with structured data handoff, showing:
- S1 AI extracting 4 fields from raw text → Sales confirms
- S2 AI structuring acceptance criteria → PM confirms
- S3 AI generating test cases → Dev confirms (5/5 passed)
- S4 AI applying hard gate (P0 all passed → approved)
- S5 AI analyzing customer feedback (93% satisfaction)
- S6 AI retrospective with KB write (ROI, next version suggestions)

## 🛠️ Tech Stack

- **UiPath Studio Web** — BPMN 2.0 process orchestration, Action Center for human tasks
- **Python + FastAPI** — API bridge between BPMN and AI agents
- **DeepSeek LLM** — AI agent reasoning with tool-use
- **ngrok** — Public tunnel for UiPath Cloud → local API

## 📄 License

MIT License — see [LICENSE](LICENSE)
