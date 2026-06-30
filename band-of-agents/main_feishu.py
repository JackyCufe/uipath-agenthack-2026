#!/usr/bin/env python3
"""
main_feishu.py — Feishu platform entry point.

Injects Feishu + DeepSeek implementations into core business logic.
This is the only file that needs to change when switching platforms.

用法:
  DEMO_BITABLE_TABLE_ID=tblHOdKIhmPe9l3d LANG=en python main_feishu.py
"""
from __future__ import annotations

import os
import sys

# Ensure project root is in path
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.config import get_settings
from core.i18n import t, get_lang
from core.routing_logic import RoutingLogic
from core.knowledge_logic import KnowledgeLogic
from core.pipeline_rules import PipelineRules

from platforms.feishu.feishu_llm import DeepSeekLLM
from platforms.feishu.feishu_kb import FeishuKnowledgeBase
from platforms.feishu.feishu_card import FeishuCard
from platforms.feishu.feishu_messaging import FeishuMessaging


def create_routing_logic() -> RoutingLogic:
    """Create RoutingLogic with Feishu + DeepSeek implementations."""
    return RoutingLogic(
        llm=DeepSeekLLM(),
        kb=FeishuKnowledgeBase(),
        card=FeishuCard(),
        messaging=FeishuMessaging(),
    )


def create_knowledge_logic() -> KnowledgeLogic:
    """Create KnowledgeLogic with Feishu + DeepSeek implementations."""
    return KnowledgeLogic(
        llm=DeepSeekLLM(),
        kb=FeishuKnowledgeBase(),
        card=FeishuCard(),
        messaging=FeishuMessaging(),
    )


def main():
    """Demo entry: process a feedback and send card."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("feedback", nargs="?", default="9100 robot responds too slowly at hotel lobby")
    parser.add_argument("customer", nargs="?", default="Liming Hotel")
    parser.add_argument("product", nargs="?", default="9100")
    parser.add_argument("--lang", "-l", default="zh", choices=["zh", "en"])
    args, _ = parser.parse_known_args()

    os.environ["LANG"] = args.lang

    settings = get_settings()
    print(f"\n{'='*60}")
    print(f"  IQ Relay + Band Routing — Feishu Platform")
    print(f"  Lang: {get_lang()}")
    print(f"{'='*60}")

    routing = create_routing_logic()

    # Process feedback
    decision = routing.process_feedback(
        feedback_text=args.feedback,
        customer_id=args.customer,
        product_model=args.product,
    )

    print(f"\n{'='*60}")
    print(f"  Routing Decision:")
    print(f"{'='*60}")
    import json
    print(json.dumps(decision.to_dict(), ensure_ascii=False, indent=2))

    # Send notification card
    owner_open_id = settings.jacky_open_id
    owner_name = "Engineering Lead" if get_lang() == "en" else "研发负责人"

    # Try to extract owner from history
    from core.pipeline_rules import PipelineRules
    history = routing.kb.search(args.feedback, top_k=1, product_model=args.product)
    if history:
        chain = routing.kb.get_chain(history[0].get("requirement_id", ""))
        if chain:
            owner_open_id, owner_name = PipelineRules.extract_stage_owner(
                chain, decision.entry_stage, owner_open_id, owner_name
            )

    result = routing.notify_handler(
        decision=decision,
        feedback_text=args.feedback,
        customer_id=args.customer,
        owner_open_id=owner_open_id,
        owner_name=owner_name,
    )

    if result.get("ok"):
        print(f"\n✅ Card sent to {owner_name}")
    else:
        print(f"\n❌ Card send failed: {result.get('error')}")


if __name__ == "__main__":
    main()
