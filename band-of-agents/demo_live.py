#!/usr/bin/env python3
"""
demo_live.py — 全自动 Demo 脚本（飞书卡片驱动）

脚本启动后：
1. 发蓝色确认卡片 → 等你在飞书点 [Confirm & Submit]
2. 收到回调 → 触发路由 → 发黄色路由卡片 → 等你点 [Resolved]
3. 收到回调 → 发绿色处理通知 → 发蓝色知识查询卡片
4. Done

全程不需要碰终端，只在飞书点按钮。

用法:
  DEMO_BITABLE_TABLE_ID=tblHOdKIhmPe9l3d LANG=en python demo_live.py
"""
from __future__ import annotations

import os
import sys
import time
import threading

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


def log(msg: str):
    """带时间戳的日志。"""
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def main():
    import lark_oapi as lark

    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")

    if not app_id or not app_secret:
        print("⚠️ FEISHU_APP_ID / FEISHU_APP_SECRET not configured")
        return

    log("=" * 60)
    log("🎬 Demo Live — Feishu Card Driven")
    log(f"  Lang: {get_lang()}")
    log("=" * 60)

    # ── 状态机 ──
    state = {"phase": "init", "result": None}

    def _on_card_action(data):
        """飞书卡片按钮回调。"""
        try:
            from lark_oapi.event.callback.model.p2_card_action_trigger import (
                P2CardActionTriggerResponse, CallBackToast, CallBackCard
            )
        except ImportError:
            log("⚠️ Cannot import P2CardActionTriggerResponse")
            return None

        try:
            event = getattr(data, "event", None) or data
            action_obj = getattr(event, "action", None)
            value = getattr(action_obj, "value", {}) or {} if action_obj else {}
            form_value = getattr(action_obj, "form_value", {}) or {} if action_obj else {}
            operator = getattr(event, "operator", None)
            operator_open_id = getattr(operator, "open_id", "") if operator else ""

            action = value.get("action", "") if isinstance(value, dict) else ""
            log(f"📩 Card action received: {action}")

            callback_data = {
                "value": value if isinstance(value, dict) else {},
                "form_data": form_value if isinstance(form_value, dict) else {},
                "operator": {"open_id": operator_open_id},
            }

            from card_callback_handler import handle_card_callback
            result = handle_card_callback(callback_data)

            # 构建响应
            resp = P2CardActionTriggerResponse()
            if result.get("ok"):
                toast = CallBackToast()
                toast.type = "success"
                toast.content = result.get("message", "OK")
                resp.toast = toast
            else:
                toast = CallBackToast()
                toast.type = "error"
                toast.content = result.get("message", "Error")
                resp.toast = toast

            if result.get("card"):
                cb_card = CallBackCard()
                cb_card.type = "raw"
                cb_card.data = result["card"]
                resp.card = cb_card

            # 根据action推进状态机
            if action == "customer_confirm":
                state["phase"] = "routed"
                state["result"] = result
                log("✅ Customer confirmed — routing triggered")
                decision = result.get("decision", {})
                log(f"   Diagnosis: {decision.get('diagnosis_type', '')}")
                log(f"   Matched: {decision.get('matched_requirement_id', '')}")
                log(f"   Target: {decision.get('target_agent', '')}")
                log("📨 Routing notification card sent to Feishu")

            elif action == "resolved":
                state["phase"] = "resolved"
                log("✅ Engineer resolved — customer notification sent")
                log("📨 Green notification card sent to Feishu")

                # 自动触发知识查询
                log("📨 Sending knowledge query card...")
                time.sleep(2)
                from knowledge_query_agent import query_knowledge
                kq_result = query_knowledge("9100 response slow")
                if kq_result.get("card_sent"):
                    log("✅ Knowledge query card sent to Feishu")
                    log("🎬 Demo complete! All 4 cards sent.")
                    log("   1. Blue confirmation card")
                    log("   2. Yellow routing notification card")
                    log("   3. Green resolved notification card")
                    log("   4. Blue knowledge query card")
                    state["phase"] = "done"
                else:
                    log(f"❌ Knowledge query failed: {kq_result.get('message')}")

            elif action == "escalate":
                state["phase"] = "escalated"
                log("✅ Escalated to full pipeline")

            elif action == "transfer":
                log("📤 Transfer card requested")

            return resp

        except Exception as exc:
            log(f"❌ Callback error: {exc}")
            import traceback
            traceback.print_exc()
            try:
                return P2CardActionTriggerResponse()
            except Exception:
                return None

    def _on_message(data):
        pass

    def _on_read(data):
        pass

    # ── 注册事件处理器 ──
    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_card_action_trigger(_on_card_action)
        .register_p2_im_message_receive_v1(_on_message)
        .register_p2_im_message_message_read_v1(_on_read)
        .build()
    )

    # ── 启动 WebSocket（后台线程）──
    ws_client = lark.ws.Client(
        app_id,
        app_secret,
        event_handler=event_handler,
        log_level=lark.LogLevel.WARNING,
    )

    ws_thread = threading.Thread(target=ws_client.start, daemon=True)
    ws_thread.start()
    log("🔌 WebSocket connected — listening for card actions")

    # ── 等待连接就绪 ──
    time.sleep(3)

    # ══════════════════════════════════════════════════════
    # Step 1: 发送客户确认卡片
    # ══════════════════════════════════════════════════════
    log("📨 Step 1: Sending customer confirmation card...")

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
    send_result = send_card_to_open_id(open_id, card)

    if send_result.get("ok"):
        log("✅ Blue confirmation card sent to Feishu")
        log("")
        log("━" * 60)
        log("  🎬 NOW: Go to Feishu and click [✅ Confirm & Submit]")
        log("  The system will automatically:")
        log("    1. Trigger routing diagnosis")
        log("    2. Send yellow routing card to engineer")
        log("    3. Wait for engineer to click [✅ Resolved]")
        log("    4. Send green notification to customer")
        log("    5. Send blue knowledge query card")
        log("━" * 60)
        log("")
    else:
        log(f"❌ Failed to send confirmation card: {send_result.get('error')}")
        return

    # ══════════════════════════════════════════════════════
    # 等待飞书交互完成（状态机自动推进）
    # ══════════════════════════════════════════════════════
    log("⏳ Waiting for Feishu interaction...")

    while state["phase"] != "done":
        time.sleep(1)

    log("")
    log("=" * 60)
    log("  🎬 Demo Complete — all cards sent successfully")
    log("=" * 60)
    log("  Press Ctrl+C to exit.")


if __name__ == "__main__":
    main()
