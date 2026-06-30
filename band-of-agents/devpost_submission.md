# Devpost Submission Content

## Elevator Pitch (Tagline)

6 AI agents coordinated by BPMN to close the information gap, knowledge gap, and workflow gap in enterprise product teams — every requirement structured, every gate enforced, every lesson remembered.

---

## About the Project

### Inspiration

In enterprise product teams, we kept seeing the same pattern: sales captures a vague requirement, PM adds their interpretation, engineering builds something, and by the time it reaches the customer — it's not what they asked for. **40% of features are never used.** The root cause isn't bad people — it's three structural gaps:

1. **Information Gap**: Requirements arrive as free text. Nobody structures them into "who, what scenario, what problem, what outcome."
2. **Knowledge Gap**: Every project starts from scratch. Lessons from last time die in Slack threads nobody reads.
3. **Workflow Gap**: "P0 must pass before release" exists in the wiki. But in practice? "P0 mostly passed" ships to production.

We built MindTheGap to close all three — mechanically, not with policy documents.

### What It Does

MindTheGap is a **6-stage AI-powered requirement pipeline** orchestrated by UiPath Maestro BPMN. Each stage pairs an **AI Agent** (Service Task) with a **Human Confirmation** (User Task):

| Stage | AI Agent Does | Human Confirms | Gateway |
|-------|--------------|----------------|---------|
| **S0** KB Search | Retrieves similar historical requirements from knowledge base | — | — |
| **S1** Gatekeeping | Extracts 4 structured fields (who, scenario, problem, expected), gives verdict | Sales reviews & confirms | approved / info_needed (loop max 3) / rejected |
| **S2** Value Transform | Structures PM acceptance criteria with P0/P1/P2 priorities, generates test cases | PM reviews & confirms | approved / escalate / rejected |
| **S3** Test Cases | Generates customer-perspective test cases | Dev Lead reviews, Test Lead fills results | approved / escalate / rejected |
| **S4** Release Review | Applies P0/P1/P2 rubric across all test results, **hard gate** enforcement | Product Lead confirms release | verified / blocked |
| **S5** Feedback | Analyzes customer satisfaction from structured surveys | — | — |
| **S6** Retrospective | Calculates ROI, generates next-version suggestions, **writes to knowledge base** | — | — |

### Key Innovations

**Hard Gate Enforcement** — Customer scenarios must be verified. Any P0 failure = blocked. No exceptions, no bypass. This isn't a policy document — it's a BPMN gateway with a mechanical condition.

**Escalation, Not Rollback** — Rejected items don't roll back (which violates BPMN 2.0). Instead, they escalate to a Team Lead for arbitration: approve to next stage, reject to end, or request more info. Clean BPMN forward flows only.

**Knowledge Feedback Loop** — S6 writes lessons learned to the knowledge base. When the next requirement comes in, S0 retrieves them. The pipeline gets smarter with every cycle. This is self-improving organizational memory.

**AI-Human Pairing** — Every stage: AI pre-fills structured data, humans confirm or correct. AI does the heavy lifting (extraction, structuring, test generation, rubric evaluation). Humans make the decisions. Augmented intelligence, not replacement.

### How We Built It

**Architecture (4 layers):**

```
UiPath Maestro BPMN (process orchestration, gateways, Action Center)
        ↓ HTTP via ngrok tunnel
FastAPI Server (6 REST endpoints, one per AI agent)
        ↓
AI Agent Engine (DeepSeek LLM, tool-use loop, 6 agent prompts)
        ↓
Data Layer (embedding search, schema builder, dual-layer storage)
```

1. **UiPath Studio Web** — We modeled the entire pipeline as BPMN 2.0 with 31 sequence flows, 5 exclusive gateways, 7 service tasks (HTTP requests), and 3 user tasks (Action Center queue items). Each Service Task calls our API; each User Task creates a queue item for human confirmation.

2. **FastAPI Bridge** — A Python server exposing 6 endpoints (`/api/s1/gatekeep` through `/api/s6/retrospective`). Each endpoint invokes the corresponding AI agent and returns structured JSON (Schema 1-6) that flows through the BPMN pipeline.

3. **AI Agent Engine** — 6 agent prompts powered by DeepSeek LLM with a tool-use loop. Each agent receives the current stage's input, processes it (extraction, transformation, test generation, rubric evaluation), and outputs a structured schema. The schema builder validates and repairs outputs.

4. **ngrok Tunnel** — Connects UiPath Automation Cloud to our local FastAPI server, enabling real-time AI agent calls during BPMN execution.

### Challenges We Ran Into

**BPMN 2.0 Compliance** — Our original design used "rollback" for rejected items (flowing backwards). After researching BPMN 2.0 spec, we discovered this violates the standard. We redesigned to use "escalation to Team Lead" instead — a forward-only flow that achieves the same outcome while being BPMN-compliant.

**Diagram Layout** — A 31-flow BPMN diagram with multiple escalation branches gets messy fast. We spent significant time on the DI (Diagram Interchange) coordinates, designing a 3-row layout (end events on top, main flow in middle, escalation paths on bottom) with dedicated routing channels to prevent arrow crossings.

**AI Agent Output Parsing** — LLMs don't always call tools when they should. We built a 3-path extraction system: (1) extract from tool_calls, (2) extract JSON from text output, (3) regex-parse fields from free-text analysis. This ensures every agent response produces a valid schema.

**Variable Mapping** — In UiPath, passing data between BPMN nodes required careful SpecificContent configuration on queue items and Output variable mapping on HTTP tasks. Each stage's output schema had to be available to downstream gateways for condition evaluation.

### Accomplishments We're Proud Of

- **31 sequence flows, zero broken connections** — Every flow in the BPMN diagram has a matching edge with correct coordinates.
- **Hard gate that actually works** — Not a checkbox, not a policy. A mechanical BPMN gateway with `verdict == "blocked"` that terminates the process.
- **Knowledge feedback loop** — S6 writes to KB, S0 reads from KB. The pipeline literally learns from itself.
- **Platform-agnostic architecture** — The `interfaces/` layer (4 ABCs) means the same pipeline can run on Feishu, Slack, or UiPath with only platform adapter changes.

### What We Learned

- BPMN 2.0 is more nuanced than it looks — gateway conditions, flow directions, and DI coordinates each have strict rules.
- UiPath Studio Web's Maestro BPMN designer is powerful but has a learning curve for complex flows.
- AI agents need robust fallback parsing — you can't assume the LLM will always format output correctly.
- The gap between "process diagram on paper" and "executable BPMN with real API calls" is enormous.

### What's Next

- **Data Service Entity** — Replace in-memory schema storage with UiPath Data Service for persistent requirement tracking.
- **Action Center Forms** — Build rich form UIs with field-level validation for each User Task.
- **Multi-tenant KB** — Separate knowledge bases per customer segment for more targeted S0 retrieval.
- **Streaming AI** — Switch from request-response to streaming for faster agent feedback during long-running analyses.

### Built With

`UiPath Studio Web` `BPMN 2.0` `Maestro` `Action Center` `Python` `FastAPI` `DeepSeek LLM` `ngrok` `Embedding Search` `Tool-Use Agents`
