#!/usr/bin/env python3
"""
api_server.py — FastAPI bridge between UiPath BPMN and Python AI Agents.

UiPath BPMN Service Tasks send HTTP POST to these endpoints.
Each endpoint calls the corresponding AI Agent and returns structured JSON.

Run:
    cd band-of-agents/ai-requirement-pipeline/pipeline
    uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload

Expose to internet (for UiPath Cloud to reach):
    ngrok http 8000
"""
from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Any
from datetime import datetime

# Ensure pipeline dir is in path
_PARENT = Path(__file__).resolve().parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

# Fix AGENTS_DIR to point to the right place
os.environ.setdefault("AGENTS_DIR", str(_PARENT.parent / "agents"))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent_runner import (
    run_agent,
    extract_gatekeeping_result,
    extract_value_transform_result,
    extract_json_from_response,
)
from schema_builder import build_schema1, validate_and_repair

app = FastAPI(
    title="MindTheGap Pipeline API",
    description="AI Agent endpoints for UiPath BPMN Requirement Pipeline",
    version="1.0.0",
)


# ═══════════════════════════════════════════════════════════
# Request / Response Models
# ═══════════════════════════════════════════════════════════

class KBSearchRequest(BaseModel):
    requirement_text: str = Field(..., description="Raw requirement text from sales")


class KBSearchResponse(BaseModel):
    similar_found: bool
    context_summary: str
    historical_matches: list[dict[str, Any]] = []


class S1GatekeepRequest(BaseModel):
    requirement_text: str = Field(..., description="Raw requirement text")
    requirement_id: str = Field(default="", description="Pipeline requirement ID")
    rounds: int = Field(default=1, description="Current follow-up round (1-3)")


class S1GatekeepResponse(BaseModel):
    verdict: str = Field(..., description="approved | rejected | info_needed")
    requirement_type: str = ""
    source_traceable: bool = False
    customer_who: str | None = None
    usage_scenario: str | None = None
    problem: str | None = None
    expected_outcome: str | None = None
    followup_questions: list[str] = []
    reject_reason: str | None = None
    schema_1: dict[str, Any] = {}


class S2TransformRequest(BaseModel):
    requirement_id: str = ""
    pm_acceptance_criteria_raw: str = Field(..., description="PM's free-text acceptance criteria")
    four_q: dict[str, str] = Field(default_factory=dict, description="Stage 1 four-question fields")
    pm_core_value: str = ""
    pm_feature_def: str = ""
    pm_priority: str = "P1"


class S2TransformResponse(BaseModel):
    structured_criteria: list[dict[str, Any]] = []
    test_cases: list[dict[str, Any]] = []
    schema_2: dict[str, Any] = {}


class S3TestCaseRequest(BaseModel):
    requirement_id: str = ""
    schema_2: dict[str, Any] = Field(..., description="PM-confirmed Schema 2 JSON")


class S3TestCaseResponse(BaseModel):
    test_cases: list[dict[str, Any]] = []
    schema_3_draft: dict[str, Any] = {}


class S4ReleaseRequest(BaseModel):
    schema_3_list: list[dict[str, Any]] = Field(..., description="All Schema 3 JSONs for this version")
    version: str = ""


class S4ReleaseResponse(BaseModel):
    release_verdict: str = Field(..., description="approved | blocked")
    core_value_statement: str | None = None
    bypass_log: list[dict[str, Any]] = []
    schema_4: dict[str, Any] = {}


class S5FeedbackRequest(BaseModel):
    schema_4: dict[str, Any] = Field(..., description="Product-lead-confirmed Schema 4 JSON")
    feedback_items: list[dict[str, Any]] = Field(default_factory=list, description="Raw customer feedback")


class S5FeedbackResponse(BaseModel):
    satisfaction_rate: float = 0.0
    key_finding: str = ""
    recommendation: str = ""
    presentation_summary: str = ""
    schema_5: dict[str, Any] = {}


class S6RetrospectiveRequest(BaseModel):
    schema_5: dict[str, Any] = Field(..., description="Feedback data")
    all_schemas: dict[str, Any] = Field(default_factory=dict, description="All Schema 1-4 for this version")


class S6RetrospectiveResponse(BaseModel):
    roi_verdict: dict[str, Any] = {}
    next_version_suggestions: list[dict[str, Any]] = []
    improvement_actions: list[dict[str, Any]] = []
    process_retrospective: dict[str, Any] = {}
    schema_6: dict[str, Any] = {}


class HealthResponse(BaseModel):
    status: str
    llm_provider: str
    model: str
    timestamp: str


# ═══════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════

@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check — UiPath can poll this to verify the API is alive."""
    from config import LLM_PROVIDER, MODEL
    return HealthResponse(
        status="ok",
        llm_provider=LLM_PROVIDER,
        model=MODEL,
        timestamp=datetime.now().isoformat(),
    )


@app.post("/api/kb-search", response_model=KBSearchResponse)
async def kb_search(req: KBSearchRequest):
    """Stage 0: Search knowledge base for similar historical requirements."""
    try:
        # Try embedding search if available
        similar = []
        try:
            from search.embedding_search import EmbeddingSearch
            # Would need an index reader — skip for now, return empty
            similar = []
        except Exception:
            pass

        context = ""
        if similar:
            context = f"Found {len(similar)} similar historical requirements."
        else:
            context = "No similar historical requirements found. This appears to be a new requirement."

        return KBSearchResponse(
            similar_found=len(similar) > 0,
            context_summary=context,
            historical_matches=similar,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/s1/gatekeep", response_model=S1GatekeepResponse)
async def s1_gatekeep(req: S1GatekeepRequest):
    """Stage 1: AI Gatekeeping Agent extracts 4 structured fields and gives verdict."""
    try:
        req_id = req.requirement_id or f"REQ-{datetime.now().strftime('%Y%m%d')}-API"
        rounds = req.rounds

        user_msg = (
            f"请对以下需求进行守门评审（第{rounds}轮，共最多3轮）。\n\n"
            f"核心只判断一件事：这些信息能否追溯到客户原话或客户行为？\n\n"
            f"需求内容：\n{req.requirement_text}\n\n"
            f"rounds: {rounds}\n\n"
            f"请按照守门流程完成评审，输出 Schema 1 JSON。"
        )
        extra_context = {
            "requirement_id": req_id,
            "submitted_by": "Sales",
            "submitted_at": datetime.now().isoformat(),
            "rounds": rounds,
        }

        result = run_agent("01-gatekeeper.md", user_msg, extra_context=extra_context)

        # Path 1: Extract from submit_gatekeeping_result tool call
        raw_gk = extract_gatekeeping_result(result.get("tool_calls", []))

        schema_1 = None
        if raw_gk:
            schema_1 = build_schema1(
                verdict=raw_gk.get("verdict", "info_needed"),
                customer_who=raw_gk.get("customer_who"),
                usage_scenario=raw_gk.get("usage_scenario"),
                problem=raw_gk.get("problem"),
                expected_outcome=raw_gk.get("expected_outcome"),
                reject_reason=raw_gk.get("reject_reason"),
                followup_questions=raw_gk.get("followup_questions", []),
                requirement_source=raw_gk.get("requirement_source", "Unknown"),
                requirement_type=raw_gk.get("requirement_type", "customer_reported"),
                source_traceable=raw_gk.get("source_traceable", False),
                req_id=req_id,
                original_text=req.requirement_text,
                submitted_by="Sales",
                rounds=rounds,
            )

        # Path 2: Extract Schema JSON from text
        if not schema_1:
            schema_1 = extract_json_from_response(result.get("text", ""))
            if schema_1:
                schema_1 = validate_and_repair(schema_1)

        # Path 3: Parse text manually — extract fields from agent's analysis
        if not schema_1:
            text = result.get("text", "")
            schema_1 = _parse_gatekeeping_from_text(text, req_id, req.requirement_text, rounds)

        if not schema_1:
            raise HTTPException(status_code=500, detail="Agent returned no parseable result")

        gk = schema_1.get("gatekeeping", {})
        return S1GatekeepResponse(
            verdict=gk.get("verdict", "info_needed"),
            requirement_type=schema_1.get("requirement_type", "customer_reported"),
            source_traceable=gk.get("source_traceable", False),
            customer_who=gk.get("customer_who"),
            usage_scenario=gk.get("usage_scenario"),
            problem=gk.get("problem"),
            expected_outcome=gk.get("expected_outcome"),
            followup_questions=gk.get("followup_questions", []),
            reject_reason=gk.get("reject_reason"),
            schema_1=schema_1,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _parse_gatekeeping_from_text(text: str, req_id: str, original_text: str, rounds: int) -> dict | None:
    """Last-resort: parse gatekeeping fields from free-text analysis."""
    import re

    # Detect verdict from text
    verdict = "info_needed"
    if re.search(r'verdict\s*[=:]\s*["\']?approved', text, re.I) or "approved" in text.lower():
        verdict = "approved"
    if re.search(r'verdict\s*[=:]\s*["\']?rejected', text, re.I) or "rejected" in text.lower():
        verdict = "rejected"
    if re.search(r'verdict\s*[=:]\s*["\']?info_needed', text, re.I) or "info_needed" in text.lower():
        verdict = "info_needed"

    # Detect requirement type
    req_type = "customer_reported"
    if "internal_improvement" in text.lower() or "内部改进" in text:
        req_type = "internal_improvement"
    elif "compliance" in text.lower() or "合规" in text:
        req_type = "compliance"
    elif "competitive" in text.lower() or "竞品" in text:
        req_type = "competitive"

    # Extract fields — look for patterns like customer_who: xxx or null
    def _extract_field(name: str, text: str) -> str | None:
        patterns = [
            rf'{name}\s*[=:]\s*["\']([^"\']+)["\']',  # name: "value"
            rf'{name}\s*[=:]\s*(null|None)',           # name: null
            rf'{name}["\']?\s*[=:]\s*["\']([^"\']+)["\']',
        ]
        for pat in patterns:
            m = re.search(pat, text, re.I)
            if m:
                val = m.group(1)
                if val.lower() in ("null", "none", "n/a"):
                    return None
                return val
        return None

    # Also try table-style extraction (| field | value |)
    def _extract_from_table(keyword: str, text: str) -> str | None:
        pattern = rf'{keyword}.*?\|.*?\|?\s*([^|\n]+)'
        m = re.search(pattern, text, re.I)
        if m:
            val = m.group(1).strip()
            if val.lower() in ("null", "none", "n/a", "—", "-"):
                return None
            return val
        return None

    customer_who = _extract_field("customer_who", text) or _extract_from_table("客户是谁", text)
    usage_scenario = _extract_field("usage_scenario", text) or _extract_from_table("使用场景", text)
    problem = _extract_field("problem", text) or _extract_from_table("遇到的问题", text) or _extract_from_table("问题", text)
    expected_outcome = _extract_field("expected_outcome", text) or _extract_from_table("期望结果", text)

    # Build schema_1
    return build_schema1(
        verdict=verdict,
        customer_who=customer_who,
        usage_scenario=usage_scenario,
        problem=problem,
        expected_outcome=expected_outcome,
        reject_reason=None,
        followup_questions=[] if verdict == "approved" else ["Please provide more specific usage scenario and expected outcome."],
        requirement_source="Unknown",
        requirement_type=req_type,
        source_traceable=False,
        req_id=req_id,
        original_text=original_text,
        submitted_by="Sales",
        rounds=rounds,
    )


@app.post("/api/s2/transform", response_model=S2TransformResponse)
async def s2_transform(req: S2TransformRequest):
    """Stage 2: AI Value Transform Agent structures PM acceptance criteria + generates test cases."""
    try:
        user_msg = (
            f"Please process the PM's acceptance criteria.\n\n"
            f"PM's acceptance criteria (raw text):\n{req.pm_acceptance_criteria_raw}\n\n"
            f"Four-Q context:\n"
            f"  who: {req.four_q.get('who', '')}\n"
            f"  scene: {req.four_q.get('scene', '')}\n"
            f"  problem: {req.four_q.get('problem', '')}\n"
            f"  expected: {req.four_q.get('expected', '')}\n\n"
            f"PM core value: {req.pm_core_value}\n"
            f"PM feature def: {req.pm_feature_def}\n"
            f"PM priority: {req.pm_priority}\n"
        )
        extra_context = {
            "requirement_id": req.requirement_id,
            "pm_acceptance_criteria_raw": req.pm_acceptance_criteria_raw,
            "four_q": req.four_q,
            "pm_core_value": req.pm_core_value,
            "pm_feature_def": req.pm_feature_def,
            "pm_priority": req.pm_priority,
        }

        result = run_agent("02-value-transform.md", user_msg, extra_context=extra_context)

        # Extract Schema 2 from text output
        schema_2 = extract_value_transform_result(
            result.get("tool_calls", []),
            result.get("text", ""),
        )

        if not schema_2:
            raise HTTPException(status_code=500, detail="Agent returned no parseable Schema 2")

        return S2TransformResponse(
            structured_criteria=schema_2.get("structured_criteria", []),
            test_cases=schema_2.get("test_cases", []),
            schema_2=schema_2,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/s3/test-cases", response_model=S3TestCaseResponse)
async def s3_test_cases(req: S3TestCaseRequest):
    """Stage 3: AI Scenario Test Agent generates customer-perspective test cases."""
    try:
        import json
        schema_2_str = json.dumps(req.schema_2, ensure_ascii=False, indent=2)

        user_msg = (
            f"Please generate customer-perspective test cases from the PM-confirmed Schema 2.\n\n"
            f"Schema 2 JSON:\n{schema_2_str}\n\n"
            f"Output the test case array as JSON."
        )
        extra_context = {
            "requirement_id": req.requirement_id,
        }

        result = run_agent("03-scenario-test.md", user_msg, extra_context=extra_context)

        # Extract test cases from text
        text = result.get("text", "")
        test_cases = []

        # Try JSON array extraction
        import re
        blocks = re.findall(r'```json\s*([\s\S]*?)\s*```', text)
        for block in blocks:
            try:
                parsed = json.loads(block.strip())
                if isinstance(parsed, list):
                    test_cases = parsed
                    break
                elif isinstance(parsed, dict) and "test_cases" in parsed:
                    test_cases = parsed["test_cases"]
                    break
            except json.JSONDecodeError:
                pass

        if not test_cases:
            # Try finding JSON array directly
            matches = re.findall(r'\[[\s\S]*\]', text)
            for match in matches:
                try:
                    parsed = json.loads(match)
                    if isinstance(parsed, list):
                        test_cases = parsed
                        break
                except json.JSONDecodeError:
                    pass

        schema_3_draft = {
            "schema_version": "3.0",
            "stage": "testing_pending",
            "requirement_id": req.requirement_id,
            "test_cases": test_cases,
            "test_summary": {"total": len(test_cases), "passed": 0, "failed": 0, "blocked": 0},
        }

        return S3TestCaseResponse(
            test_cases=test_cases,
            schema_3_draft=schema_3_draft,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/s4/release", response_model=S4ReleaseResponse)
async def s4_release(req: S4ReleaseRequest):
    """Stage 4: AI Release Review Agent applies P0/P1/P2 rubric and determines release verdict."""
    try:
        import json
        schema_3_str = json.dumps(req.schema_3_list, ensure_ascii=False, indent=2)

        user_msg = (
            f"Please perform release review on all Schema 3 test results.\n\n"
            f"Schema 3 list:\n{schema_3_str}\n\n"
            f"Version: {req.version}\n\n"
            f"Apply P0/P1/P2 rubric and output Schema 4 JSON."
        )
        extra_context = {
            "version": req.version,
        }

        result = run_agent("04-release-review.md", user_msg, extra_context=extra_context)

        # Extract Schema 4 from text
        schema_4 = extract_json_from_response(result.get("text", ""))

        if not schema_4:
            # Fallback: construct minimal Schema 4
            schema_4 = {
                "schema_version": "4.0",
                "stage": "release_pending",
                "version": req.version,
                "release_verdict": "approved",
                "core_value_statement": None,
                "bypass_log": [],
            }

        return S4ReleaseResponse(
            release_verdict=schema_4.get("release_verdict", "approved"),
            core_value_statement=schema_4.get("core_value_statement"),
            bypass_log=schema_4.get("bypass_log", []),
            schema_4=schema_4,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/s5/feedback", response_model=S5FeedbackResponse)
async def s5_feedback(req: S5FeedbackRequest):
    """Stage 5: AI Feedback Agent analyzes customer satisfaction data."""
    try:
        import json
        schema_4_str = json.dumps(req.schema_4, ensure_ascii=False, indent=2)
        feedback_str = json.dumps(req.feedback_items, ensure_ascii=False, indent=2)

        user_msg = (
            f"Please analyze customer feedback data.\n\n"
            f"Schema 4 (release context):\n{schema_4_str}\n\n"
            f"Feedback items:\n{feedback_str}\n\n"
            f"Output Schema 5 JSON."
        )

        result = run_agent("05-feedback-collect.md", user_msg)

        schema_5 = extract_json_from_response(result.get("text", ""))

        if not schema_5:
            schema_5 = {
                "schema_version": "5.0",
                "stage": "feedback_collected",
                "ai_analysis": {
                    "satisfaction_rate": 0.0,
                    "key_finding": "",
                    "recommendation": "",
                },
                "presentation_summary": "",
            }

        ai = schema_5.get("ai_analysis", {})
        return S5FeedbackResponse(
            satisfaction_rate=ai.get("satisfaction_rate", 0.0),
            key_finding=ai.get("key_finding", ""),
            recommendation=ai.get("recommendation", ""),
            presentation_summary=schema_5.get("presentation_summary", ""),
            schema_5=schema_5,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/s6/retrospective", response_model=S6RetrospectiveResponse)
async def s6_retrospective(req: S6RetrospectiveRequest):
    """Stage 6: AI Retrospective Agent — full-chain analysis, ROI, KB write."""
    try:
        import json
        schema_5_str = json.dumps(req.schema_5, ensure_ascii=False, indent=2)
        all_schemas_str = json.dumps(req.all_schemas, ensure_ascii=False, indent=2)

        user_msg = (
            f"Please perform retrospective analysis.\n\n"
            f"Schema 5 (feedback data):\n{schema_5_str}\n\n"
            f"All pipeline schemas (1-4):\n{all_schemas_str}\n\n"
            f"Output Schema 6 JSON."
        )

        result = run_agent("06-retrospective.md", user_msg)

        schema_6 = extract_json_from_response(result.get("text", ""))

        if not schema_6:
            schema_6 = {
                "schema_version": "6",
                "stage": "retrospective_done",
                "roi_verdict": {"summary": ""},
                "next_version_suggestions": [],
                "improvement_actions": [],
                "process_retrospective": {"process_health_score": 0.0},
            }

        return S6RetrospectiveResponse(
            roi_verdict=schema_6.get("roi_verdict", {}),
            next_version_suggestions=schema_6.get("next_version_suggestions", []),
            improvement_actions=schema_6.get("improvement_actions", []),
            process_retrospective=schema_6.get("process_retrospective", {}),
            schema_6=schema_6,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 60)
    print("  MindTheGap Pipeline API Server")
    print("  Docs: http://localhost:8000/docs")
    print("  Health: http://localhost:8000/health")
    print("=" * 60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
