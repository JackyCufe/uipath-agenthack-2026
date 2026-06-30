"""
test_pipeline_rules.py — Unit tests for pipeline rules.
"""
import pytest
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.pipeline_rules import PipelineRules
from core.data_models import DIAGNOSIS_TO_STAGE


class TestCanAdvance:
    def test_normal_advance(self):
        ok, _ = PipelineRules.can_advance(1, {})
        assert ok is True

    def test_hard_gate_blocks_without_verification(self):
        ok, reason = PipelineRules.can_advance(4, {"scenario_verified": False})
        assert ok is False
        assert "Hard gate" in reason

    def test_hard_gate_passes_with_verification(self):
        ok, _ = PipelineRules.can_advance(4, {"scenario_verified": True})
        assert ok is True

    def test_invalid_stage_low(self):
        ok, _ = PipelineRules.can_advance(0, {})
        assert ok is False

    def test_invalid_stage_high(self):
        ok, _ = PipelineRules.can_advance(7, {})
        assert ok is False


class TestNextStage:
    def test_stage_1_to_2(self):
        assert PipelineRules.get_next_stage(1) == 2

    def test_stage_6_is_final(self):
        assert PipelineRules.get_next_stage(6) is None


class TestRollback:
    def test_rollback_allowed(self):
        ok, _ = PipelineRules.can_rollback(3, 0)
        assert ok is True

    def test_rollback_from_s1_not_allowed(self):
        ok, _ = PipelineRules.can_rollback(1, 0)
        assert ok is False

    def test_rollback_target(self):
        assert PipelineRules.get_rollback_target(3) == 2
        assert PipelineRules.get_rollback_target(1) == 1


class TestS1RetryLimit:
    def test_within_limit(self):
        ok, _ = PipelineRules.check_s1_retry_limit(1)
        assert ok is True

    def test_exceeds_limit(self):
        ok, reason = PipelineRules.check_s1_retry_limit(3)
        assert ok is False
        assert "exceeded" in reason.lower()


class TestDiagnosisToStage:
    def test_all_mappings_present(self):
        assert "tech_bug" in DIAGNOSIS_TO_STAGE
        assert "service_issue" in DIAGNOSIS_TO_STAGE
        assert "new_requirement" in DIAGNOSIS_TO_STAGE
        assert "complaint" in DIAGNOSIS_TO_STAGE

    def test_entry_stage_for_diagnosis(self):
        assert PipelineRules.get_entry_stage_for_diagnosis("tech_bug") == 3
        assert PipelineRules.get_entry_stage_for_diagnosis("new_requirement") == 1
        assert PipelineRules.get_entry_stage_for_diagnosis("unknown") == 1  # fallback


class TestProductModelExtraction:
    def test_extract_9100(self):
        assert PipelineRules.extract_product_model("9100 robot slow") == "9100"

    def test_extract_8200(self):
        assert PipelineRules.extract_product_model("8200 voice issue") == "8200"

    def test_extract_x1(self):
        assert PipelineRules.extract_product_model("X1 export feature") == "X1"

    def test_no_model_found(self):
        assert PipelineRules.extract_product_model("no model here") == ""

    def test_custom_models(self):
        assert PipelineRules.extract_product_model("v3 issue", ["v3", "v4"]) == "v3"


class TestStageOwnerExtraction:
    def test_extract_from_history(self):
        req = {
            "stage_data": {
                "S3": {"S3_owner": [{"id": "ou_123", "name": "Jacky"}]}
            }
        }
        open_id, name = PipelineRules.extract_stage_owner(req, 3, "fallback_id", "fallback_name")
        assert open_id == "ou_123"
        assert name == "Jacky"

    def test_fallback_when_no_history(self):
        open_id, name = PipelineRules.extract_stage_owner(None, 3, "fallback_id", "fallback_name")
        assert open_id == "fallback_id"
        assert name == "fallback_name"

    def test_fallback_when_no_owner_field(self):
        req = {"stage_data": {"S3": {"S3_tech_plan": "some plan"}}}
        open_id, name = PipelineRules.extract_stage_owner(req, 3, "fb_id", "fb_name")
        assert open_id == "fb_id"
