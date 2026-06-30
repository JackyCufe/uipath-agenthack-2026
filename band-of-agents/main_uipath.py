#!/usr/bin/env python3
"""
main_uipath.py — UiPath platform entry point.

Injects UiPath + DeepSeek implementations into core business logic.
This is the UiPath equivalent of main_feishu.py.

用法:
  UIPATH_ORCHESTRATOR_URL=... UIPATH_CLIENT_ID=... python main_uipath.py
  python main_uipath.py --feedback "9100 robot responds too slowly" --customer "Liming Hotel"
"""
from __future__ import annotations

import os
import sys
import json

# Ensure project root is in path
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.config import get_settings
from core.i18n import t, get_lang
from core.routing_logic import RoutingLogic
from core.knowledge_logic import KnowledgeLogic
from core.pipeline_rules import PipelineRules

from platforms.uipath.uipath_llm import UiPathLLM
from platforms.uipath.uipath_kb import UiPathKnowledgeBase
from platforms.uipath.uipath_card import UiPathCard
from platforms.uipath.uipath_messaging import UiPathMessaging


def create_routing_logic() -> RoutingLogic:
    """Create RoutingLogic with UiPath + DeepSeek implementations."""
    return RoutingLogic(
        llm=UiPathLLM(),
        kb=UiPathKnowledgeBase(),
        card=UiPathCard(),
        messaging=UiPathMessaging(),
    )


def create_knowledge_logic() -> KnowledgeLogic:
    """Create KnowledgeLogic with UiPath + DeepSeek implementations."""
    return KnowledgeLogic(
        llm=UiPathLLM(),
        kb=UiPathKnowledgeBase(),
        card=UiPathCard(),
        messaging=UiPathMessaging(),
    )


def main():
    """Demo entry: process a feedback and send Action Center task."""
    import argparse
    parser = argparse.ArgumentParser(description="MindTheGap — UiPath Platform")
    parser.add_argument("feedback", nargs="?",
                        default="9100 robot responds too slowly at hotel lobby")
    parser.add_argument("customer", nargs="?", default="Liming Hotel")
    parser.add_argument("product", nargs="?", default="9100")
    parser.add_argument("--lang", "-l", default="zh", choices=["zh", "en"])
    args, _ = parser.parse_known_args()

    os.environ["LANG"] = args.lang

    settings = get_settings()
    print(f"\n{'='*60}")
    print(f"  MindTheGap — UiPath Platform")
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
    print(json.dumps(decision.to_dict(), ensure_ascii=False, indent=2))

    # Send notification card as Action Center task
    owner_id = settings.uipath_folder_id or "default"
    owner_name = "Engineering Lead" if get_lang() == "en" else "研发负责人"

    # Try to extract owner from history
    history = routing.kb.search(args.feedback, top_k=1, product_model=args.product)
    if history:
        chain = routing.kb.get_chain(history[0].get("requirement_id", ""))
        if chain:
            owner_id, owner_name = PipelineRules.extract_stage_owner(
                chain, decision.entry_stage, owner_id, owner_name
            )

    result = routing.notify_handler(
        decision=decision,
        feedback_text=args.feedback,
        customer_id=args.customer,
        owner_open_id=owner_id,
        owner_name=owner_name,
    )

    if result.get("ok"):
        print(f"\n✅ Action Center task created for {owner_name}")
        print(f"   Task ID: {result.get('message_id', '')}")
    else:
        print(f"\n❌ Task creation failed: {result.get('error')}")
        print(f"   (UiPath sandbox not configured? Check .env settings)")


if __name__ == "__main__":
    main()
