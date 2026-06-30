"""
test_routing_logic.py — Unit tests for core routing logic.

Tests the platform-agnostic business logic with mock interfaces.
"""
import pytest
import os
import sys

# Ensure project root in path
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("LANG", "zh")

from core.routing_logic import RoutingLogic
from core.data_models import RoutingDecision, FeedbackTrace, DIAGNOSIS_TO_STAGE
from interfaces.llm import LLMInterface, LLMResponse
from interfaces.knowledge_base import KnowledgeBaseInterface
from interfaces.card import CardInterface, CardAction
from interfaces.messaging import MessagingInterface, MessageCallback
from typing import Any, Callable, Awaitable


# ── Mock implementations ──

class MockLLM(LLMInterface):
    def __init__(self, json_output: dict[str, Any] | None = None):
        self._json_output = json_output or {"diagnosis_type": "tech_bug", "severity": "normal", "entry_reason": "test"}
        self.calls: list[tuple[str, str]] = []

    def chat(self, system_prompt: str, user_message: str, max_tokens: int = 1024,
             tools: list[dict[str, Any]] | None = None, tool_handler: Any = None) -> LLMResponse:
        self.calls.append((system_prompt, user_message))
        return LLMResponse(text="mock summary")

    def chat_with_json_output(self, system_prompt: str, user_message: str,
                              max_tokens: int = 1024) -> dict[str, Any] | None:
        self.calls.append((system_prompt, user_message))
        return self._json_output


class MockKB(KnowledgeBaseInterface):
    def __init__(self, history: list[dict[str, Any]] | None = None):
        self.history = history or []
        self.traces: list[dict[str, Any]] = []

    def search(self, keyword: str, top_k: int = 5, product_model: str = "") -> list[dict[str, Any]]:
        records = self.history
        if product_model:
            records = [r for r in records if r.get("product_model") == product_model]
        return records[:top_k]

    def get_chain(self, requirement_id: str) -> dict[str, Any] | None:
        for r in self.history:
            if r.get("requirement_id") == requirement_id:
                return r
        return None

    def update_record(self, requirement_id: str, fields: dict[str, Any]) -> bool:
        return True

    def write_trace(self, trace: dict[str, Any]) -> bool:
        self.traces.append(trace)
        return True


class MockCard(CardInterface):
    def build_routing_card(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "routing", "data": kwargs}

    def build_confirm_card(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "confirm", "data": kwargs}

    def build_resolved_card(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "resolved", "data": kwargs}

    def build_knowledge_card(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "knowledge", "data": kwargs}

    def build_transfer_card(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "transfer", "data": kwargs}


class MockMessaging(MessagingInterface):
    def __init__(self):
        self.sent: list[dict[str, Any]] = []

    def send_message(self, recipient_id: str, content: str, **kwargs: Any) -> dict[str, Any]:
        self.sent.append({"type": "text", "recipient": recipient_id, "content": content})
        return {"ok": True, "message_id": "msg_1", "error": None}

    def send_card(self, recipient_id: str, card: dict[str, Any]) -> dict[str, Any]:
        self.sent.append({"type": "card", "recipient": recipient_id, "card": card})
        return {"ok": True, "message_id": "msg_2", "error": None}

    def start_listening(self, callback_handler: Callable[[MessageCallback], Awaitable[dict[str, Any]]]) -> None:
        pass


# ── Fixtures ──

@pytest.fixture
def mock_llm():
    return MockLLM()


@pytest.fixture
def mock_kb():
    return MockKB(history=[
        {
            "requirement_id": "DEMO-001",
            "title": "Robot first-response latency exceeds 5s",
            "product_model": "9100",
            "stage_data": {
                "S1": {"S1_problem": "Robot takes 20+ seconds", "S1_expected": "< 5s"},
                "S2": {"S2_acceptance": "First response < 5s in 10 tests", "S2_priority": "P0"},
                "S3": {"S3_tech_plan": "Optimized interaction chain", "S3_owner": [{"id": "ou_test", "name": "Jacky"}]},
            },
            "searchable_text": "Robot latency response slow 9100 hotel lobby",
        },
        {
            "requirement_id": "DEMO-002",
            "title": "Voice recognition accuracy drops",
            "product_model": "8200",
            "stage_data": {},
            "searchable_text": "Voice recognition accuracy noisy 8200",
        },
    ])


@pytest.fixture
def mock_card():
    return MockCard()


@pytest.fixture
def mock_messaging():
    return MockMessaging()


@pytest.fixture
def routing(mock_llm, mock_kb, mock_card, mock_messaging):
    return RoutingLogic(llm=mock_llm, kb=mock_kb, card=mock_card, messaging=mock_messaging)


# ── Tests: Intent identification ──

class TestIntentIdentification:
    def test_query_intent(self, routing):
        assert routing.identify_intent("?9100 response slow") == "query"

    def test_feedback_intent(self, routing):
        assert routing.identify_intent("9100 robot is slow") == "feedback"

    def test_empty_string(self, routing):
        assert routing.identify_intent("") == "feedback"

    def test_question_mark_only(self, routing):
        assert routing.identify_intent("?") == "query"

    def test_question_mark_with_space(self, routing):
        assert routing.identify_intent("? 9100 slow") == "query"


# ── Tests: Diagnosis type mapping ──

class TestDiagnosisMapping:
    def test_tech_bug_maps_to_s3(self):
        assert DIAGNOSIS_TO_STAGE["tech_bug"]["entry_stage"] == 3
        assert DIAGNOSIS_TO_STAGE["tech_bug"]["target_agent"] == "@s3-agent"

    def test_service_issue_maps_to_s2(self):
        assert DIAGNOSIS_TO_STAGE["service_issue"]["entry_stage"] == 2

    def test_new_requirement_maps_to_s1(self):
        assert DIAGNOSIS_TO_STAGE["new_requirement"]["entry_stage"] == 1

    def test_complaint_maps_to_s5(self):
        assert DIAGNOSIS_TO_STAGE["complaint"]["entry_stage"] == 5

    def test_unknown_diagnosis_fallback(self, routing):
        """Unknown diagnosis type should fallback to new_requirement."""
        mock_llm_unknown = MockLLM(json_output={"diagnosis_type": "unknown_type", "severity": "normal"})
        routing._routing_prompt = "test"
        routing.llm = mock_llm_unknown
        decision = routing.process_feedback("test feedback", "customer")
        # Should fallback to new_requirement → S1
        assert decision.entry_stage == 1
        assert decision.target_agent == "@s1-agent"


# ── Tests: Product model filtering ──

class TestProductModelFilter:
    def test_9100_filter_excludes_8200(self, mock_kb):
        results_9100 = mock_kb.search("robot", product_model="9100")
        results_8200 = mock_kb.search("robot", product_model="8200")
        assert all(r["product_model"] == "9100" for r in results_9100)
        assert all(r["product_model"] == "8200" for r in results_8200)
        assert results_9100[0]["requirement_id"] == "DEMO-001"
        assert results_8200[0]["requirement_id"] == "DEMO-002"

    def test_no_product_model_returns_all(self, mock_kb):
        results = mock_kb.search("robot", product_model="")
        assert len(results) == 2

    def test_nonexistent_product_model_returns_empty(self, mock_kb):
        results = mock_kb.search("robot", product_model="9999")
        assert len(results) == 0


# ── Tests: Process feedback full flow ──

class TestProcessFeedback:
    def test_matched_feedback_routes_correctly(self, routing, mock_kb):
        decision = routing.process_feedback(
            feedback_text="9100 robot responds slowly",
            customer_id="Liming Hotel",
            product_model="9100",
        )
        assert decision.diagnosis_type == "tech_bug"
        assert decision.entry_stage == 3
        assert decision.target_agent == "@s3-agent"
        assert decision.matched_requirement_id == "DEMO-001"

    def test_no_match_routes_to_s1(self, mock_llm, mock_card, mock_messaging):
        empty_kb = MockKB(history=[])
        llm = MockLLM(json_output={"diagnosis_type": "new_requirement", "severity": "normal", "entry_reason": "no match"})
        routing = RoutingLogic(llm=llm, kb=empty_kb, card=mock_card, messaging=mock_messaging)
        decision = routing.process_feedback("totally new feature", "NewClient")
        assert decision.entry_stage == 1
        assert decision.matched_requirement_id is None

    def test_feedback_trace_written(self, routing, mock_kb):
        routing.process_feedback("9100 slow", "Liming", "9100")
        assert len(mock_kb.traces) == 1
        trace = mock_kb.traces[0]
        assert trace["original_feedback"] == "9100 slow"
        assert trace["customer_id"] == "Liming"
        assert trace["diagnosis_type"] == "tech_bug"

    def test_severity_from_llm(self, mock_kb, mock_card, mock_messaging):
        llm = MockLLM(json_output={"diagnosis_type": "tech_bug", "severity": "urgent", "entry_reason": "critical"})
        routing = RoutingLogic(llm=llm, kb=mock_kb, card=mock_card, messaging=mock_messaging)
        decision = routing.process_feedback("9100 urgent issue", "customer", "9100")
        assert decision.severity == "urgent"


# ── Tests: Notify handler ──

class TestNotifyHandler:
    def test_card_sent_to_owner(self, routing, mock_messaging):
        decision = RoutingDecision(
            diagnosis_type="tech_bug", entry_stage=3, severity="normal",
            entry_reason="test", context_summary="test summary", target_agent="@s3-agent",
        )
        result = routing.notify_handler(decision, "feedback", "customer", "ou_test", "Jacky")
        assert result["ok"] is True
        assert len(mock_messaging.sent) == 1
        assert mock_messaging.sent[0]["recipient"] == "ou_test"

    def test_confirm_card_sent(self, routing, mock_messaging):
        result = routing.send_confirm_card("feedback text", "9100", "customer", "ou_test")
        assert result["ok"] is True
        assert len(mock_messaging.sent) == 1


# ── Tests: FeedbackTrace data structure ──

class TestFeedbackTrace:
    def test_to_dict(self):
        trace = FeedbackTrace(
            original_feedback="test",
            customer_id="cust",
            diagnosis_type="tech_bug",
            entry_stage=3,
            severity="normal",
            routing_target="@s3-agent",
        )
        d = trace.to_dict()
        assert d["original_feedback"] == "test"
        assert d["diagnosis_type"] == "tech_bug"
        assert d["entry_stage"] == 3
        assert d["resolution"] is None

    def test_routing_decision_to_dict(self):
        decision = RoutingDecision(
            diagnosis_type="tech_bug",
            matched_requirement_id="DEMO-001",
            entry_stage=3,
            severity="urgent",
            target_agent="@s3-agent",
        )
        d = decision.to_dict()
        assert d["diagnosis_type"] == "tech_bug"
        assert d["matched_requirement_id"] == "DEMO-001"
        assert d["severity"] == "urgent"
