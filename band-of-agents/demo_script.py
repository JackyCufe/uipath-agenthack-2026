#!/usr/bin/env python3
"""
demo_script.py — 端到端 Demo 驱动脚本

按 Demo 视频顺序执行三个场景，使用真实飞书 API。
每一步自动执行 + 输出 PASS/FAIL。

用法:
  python demo_script.py --scene pipeline_overview
  python demo_script.py --scene knowledge_query
  python demo_script.py --scene band_routing
  python demo_script.py --all
  python demo_script.py --all --lang en
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

# ── 环境加载 ──────────────────────────────────────────

_pipeline_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai-requirement-pipeline", "pipeline")
if _pipeline_dir not in sys.path:
    sys.path.insert(0, _pipeline_dir)

_env_name = os.environ.get("FEISHU_ENV", "team-testing")
_env_file = os.path.join(_pipeline_dir, f".env.{_env_name}")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

_routing_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "band-routing")
if _routing_dir not in sys.path:
    sys.path.insert(0, _routing_dir)
_tools_dir = os.path.join(_routing_dir, "tools")
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from i18n import t, get_lang
from bitable_reader import search_bitable_history, get_requirement_chain


# ── 工具函数 ──────────────────────────────────────────

class StepResult:
    def __init__(self, name: str, passed: bool, detail: str = ""):
        self.name = name
        self.passed = passed
        self.detail = detail

    def __repr__(self):
        icon = "✅" if self.passed else "❌"
        return f"{icon} {self.name}" + (f" — {self.detail}" if self.detail else "")


def run_step(name: str, fn) -> StepResult:
    """执行一个步骤，捕获异常，返回结果。"""
    print(f"\n{'─'*40}")
    print(f"  Step: {name}")
    print(f"{'─'*40}")
    try:
        result = fn()
        if isinstance(result, StepResult):
            print(f"  {result}")
            return result
        elif isinstance(result, bool):
            r = StepResult(name, result)
            print(f"  {r}")
            return r
        else:
            r = StepResult(name, True, str(result)[:100])
            print(f"  {r}")
            return r
    except Exception as e:
        r = StepResult(name, False, str(e))
        print(f"  {r}")
        import traceback
        traceback.print_exc()
        return r


def wait(seconds: int, msg: str = ""):
    """等待，显示倒计时。"""
    for i in range(seconds, 0, -1):
        print(f"\r  ⏳ {msg} ({i}s)...", end="", flush=True)
        time.sleep(1)
    print(f"\r  ✅ {msg} done.      ")


# ── 场景1：Pipeline 数据概览 ─────────────────────────

def scene_pipeline_overview() -> list[StepResult]:
    """展示 Bitable 中已沉淀的需求档案。"""
    print(f"\n{'='*60}")
    print(f"  Scene 1: Pipeline Overview")
    print(f"{'='*60}")

    results = []

    # 查 Bitable 历史（Demo表用英文字段名，直接查）
    def _search():
        records = search_bitable_history("robot", top_k=10)
        if len(records) >= 3:
            print(f"  Found {len(records)} records:")
            for r in records[:5]:
                req_id = r.get("requirement_id", "")
                title = r.get("title", "")[:40]
                model = r.get("product_model", "")
                print(f"    - {req_id}: {title} (model: {model})")
            return StepResult("Search Bitable history", True, f"{len(records)} records found")
        elif len(records) > 0:
            print(f"  Found {len(records)} records (need >= 3 for PASS)")
            return StepResult("Search Bitable history", False, f"Only {len(records)} records")
        else:
            return StepResult("Search Bitable history", False, "No records found")

    results.append(run_step("Search Bitable history", _search))

    return results


# ── 场景2：新员工知识查询 ────────────────────────────

def scene_knowledge_query() -> list[StepResult]:
    """新员工输入关键词，收到知识查询卡片。"""
    print(f"\n{'='*60}")
    print(f"  Scene 2: Knowledge Query (New Employee)")
    print(f"{'='*60}")

    results = []

    def _query():
        from knowledge_query_agent import query_knowledge
        keyword = "9100 response slow"
        print(f"  Querying: '{keyword}'")
        result = query_knowledge(keyword)
        if result.get("ok") and result.get("card_sent"):
            return StepResult("Knowledge query", True, "Card sent to Feishu")
        else:
            return StepResult("Knowledge query", False, result.get("message", "Failed"))

    results.append(run_step("Knowledge query", _query))

    return results


# ── 场景3：Band 路由完整闭环 ─────────────────────────

def scene_band_routing() -> list[StepResult]:
    """
    完整闭环：客户反馈→确认→路由→处理→通知。
    脚本自动模拟按钮点击（调 handle_card_callback）。
    """
    print(f"\n{'='*60}")
    print(f"  Scene 3: Band Routing (Full Loop)")
    print(f"{'='*60}")

    results = []

    # Step 1: 发送客户确认卡片
    def _send_confirm():
        from routing_agent import RoutingAgent
        from lark_notifier import build_customer_confirm_card, send_card_to_open_id

        agent = RoutingAgent()
        feedback = "9100 robot responds too slowly at hotel lobby, guests waiting too long"
        ai_summary = agent._generate_feedback_summary(feedback)

        card = build_customer_confirm_card(
            feedback_text=feedback,
            product_model="9100",
            customer_id="Liming International Hotel",
            ai_summary=ai_summary,
        )
        open_id = os.environ.get("JACKY_OPEN_ID", "")
        result = send_card_to_open_id(open_id, card)
        if result.get("ok"):
            return StepResult("Send confirm card", True, f"message_id={result.get('message_id', '')[:20]}")
        return StepResult("Send confirm card", False, result.get("error", "Failed"))

    results.append(run_step("Send confirm card", _send_confirm))

    # Step 2: 模拟客户点"确认提交" → 触发路由
    def _customer_confirm():
        from card_callback_handler import handle_card_callback

        callback_data = {
            "value": {
                "action": "customer_confirm",
                "feedback_text": "9100 robot responds too slowly at hotel lobby, guests waiting too long",
                "product_model": "9100",
                "customer_id": "Liming International Hotel",
            },
            "form_data": {},
            "operator": {"open_id": os.environ.get("JACKY_OPEN_ID", "")},
        }
        result = handle_card_callback(callback_data)
        if result.get("ok"):
            decision = result.get("decision", {})
            diag = decision.get("diagnosis_type", "")
            target = decision.get("target_agent", "")
            return StepResult("Customer confirm → routing", True, f"diagnosis={diag}, target={target}")
        return StepResult("Customer confirm → routing", False, result.get("message", "Failed"))

    results.append(run_step("Customer confirm → routing", _customer_confirm))

    # Step 3: 模拟研发点"已处理"
    def _resolve():
        from card_callback_handler import handle_card_callback

        callback_data = {
            "value": {
                "action": "resolved",
                "requirement_id": "DEMO-001",
                "entry_stage": 3,
                "diagnosis_type": "tech_bug",
                "customer_id": "Liming International Hotel",
            },
            "form_data": {},
            "operator": {"open_id": os.environ.get("JACKY_OPEN_ID", "")},
        }
        result = handle_card_callback(callback_data)
        if result.get("ok"):
            return StepResult("Resolve feedback", True, result.get("message", ""))
        return StepResult("Resolve feedback", False, result.get("message", "Failed"))

    results.append(run_step("Resolve feedback", _resolve))

    # Step 4: 验证 Bitable 已更新
    def _verify_bitable():
        from bitable_reader import get_requirement_chain as _get_chain
        chain = _get_chain("DEMO-001")
        if chain:
            return StepResult("Verify Bitable updated", True, "DEMO-001 record exists")
        return StepResult("Verify Bitable updated", False, "Record not found")

    results.append(run_step("Verify Bitable updated", _verify_bitable))

    return results


# ── 主函数 ────────────────────────────────────────────

SCENES = {
    "pipeline_overview": scene_pipeline_overview,
    "knowledge_query": scene_knowledge_query,
    "band_routing": scene_band_routing,
}


def main():
    parser = argparse.ArgumentParser(description="Demo Script — End-to-End")
    parser.add_argument("--scene", "-s", type=str, help="Scene name")
    parser.add_argument("--all", "-a", action="store_true", help="Run all scenes")
    parser.add_argument("--lang", "-l", default="zh", choices=["zh", "en"], help="Language")
    args = parser.parse_args()

    os.environ["LANG"] = args.lang

    if args.all:
        all_results = {}
        for name, fn in SCENES.items():
            print(f"\n{'='*60}")
            print(f"  Running: {name}")
            print(f"{'='*60}")
            try:
                all_results[name] = fn()
            except Exception as e:
                print(f"❌ EXCEPTION in {name}: {e}")
                import traceback
                traceback.print_exc()
                all_results[name] = [StepResult(name, False, str(e))]

        # 汇总
        print(f"\n{'='*60}")
        print(f"  SUMMARY")
        print(f"{'='*60}")
        total_pass = 0
        total_fail = 0
        for scene_name, step_results in all_results.items():
            for sr in step_results:
                if sr.passed:
                    total_pass += 1
                else:
                    total_fail += 1
                print(f"  {sr}")
        print(f"\n  Total: {total_pass} passed, {total_fail} failed")
        print(f"  Overall: {'✅ ALL PASS' if total_fail == 0 else '❌ SOME FAILED'}")
        sys.exit(0 if total_fail == 0 else 1)

    elif args.scene:
        fn = SCENES.get(args.scene)
        if not fn:
            print(f"Unknown scene: {args.scene}")
            print(f"Available: {', '.join(SCENES.keys())}")
            sys.exit(1)
        results = fn()
        passed = all(r.passed for r in results)
        print(f"\n{'='*60}")
        print(f"  {'✅ PASS' if passed else '❌ FAIL'} — {args.scene}")
        print(f"{'='*60}")
        sys.exit(0 if passed else 1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
