"""
test_i18n.py — Unit tests for i18n text lookup.
"""
import pytest
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class TestI18nZh:
    def setup_method(self):
        os.environ["LANG"] = "zh"
        import importlib
        import core.i18n
        importlib.reload(core.i18n)
        self.i18n = core.i18n

    def test_basic_lookup_zh(self):
        assert self.i18n.t("card.routing_title") == "客户反馈路由通知"

    def test_missing_key_returns_key(self):
        assert self.i18n.t("nonexistent.key") == "nonexistent.key"

    def test_template_substitution(self):
        result = self.i18n.t("log.found_matches", count=5)
        assert "5" in result

    def test_get_lang(self):
        assert self.i18n.get_lang() == "zh"


class TestI18nEn:
    def setup_method(self):
        os.environ["LANG"] = "en"
        import importlib
        import core.i18n
        importlib.reload(core.i18n)
        self.i18n = core.i18n

    def test_basic_lookup_en(self):
        assert self.i18n.t("card.routing_title") == "Customer Feedback Routing Notice"

    def test_diagnosis_labels_en(self):
        assert self.i18n.t("diagnosis.tech_bug") == "Tech Bug (Regression)"
        assert self.i18n.t("diagnosis.new_requirement") == "New Requirement"

    def test_field_names_en(self):
        assert self.i18n.t("field.requirement_id") == "requirement_id"
        assert self.i18n.t("field.product_model") == "product_model"

    def test_get_lang(self):
        assert self.i18n.get_lang() == "en"

    def teardown_method(self):
        os.environ["LANG"] = "zh"
