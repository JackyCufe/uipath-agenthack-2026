"""
card_callback_server.py — 飞书 WebSocket 卡片回调监听服务

启动后监听飞书卡片按钮回调，接 card_callback_handler.handle_card_callback。
解决"目标回调服务不在线"问题。

用法:
  python band-routing/card_callback_server.py

参考: ai-requirement-pipeline/pipeline/card_handler.py 的 WebSocket 实现
"""
from __future__ import annotations

import os
import sys
import threading
import time

# 加载飞书环境
_pipeline_dir = os.path.join(os.path.dirname(__file__), "..", "ai-requirement-pipeline", "pipeline")
_pipeline_dir = os.path.abspath(_pipeline_dir)
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

# i18n
_routing_dir = os.path.dirname(os.path.abspath(__file__))
if _routing_dir not in sys.path:
    sys.path.insert(0, _routing_dir)
from i18n import t

# 导入回调处理器
_tools_dir = os.path.join(_routing_dir, "tools")
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)
from card_callback_handler import handle_card_callback


def start_server():
    """启动飞书 WebSocket 长连接，监听卡片按钮回调。"""
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")

    if not app_id or not app_secret:
        print("⚠️ FEISHU_APP_ID / FEISHU_APP_SECRET not configured")
        return

    try:
        import lark_oapi as lark
    except ImportError:
        print("⚠️ lark_oapi not installed. Install with: pip install lark-oapi")
        return

    def card_callback_handler_fn(data):
        """lark_oapi 触发 card.action.trigger 时调用。"""
        try:
            from lark_oapi.event.callback.model.p2_card_action_trigger import (
                P2CardActionTriggerResponse, CallBackToast, CallBackCard
            )
        except ImportError:
            print("[callback_server] ⚠️ Cannot import P2CardActionTriggerResponse")
            return None

        try:
            event = getattr(data, "event", None) or data
            action_obj = getattr(event, "action", None)
            value = getattr(action_obj, "value", {}) or {} if action_obj else {}
            form_value = getattr(action_obj, "form_value", {}) or {} if action_obj else {}
            operator = getattr(event, "operator", None)
            operator_open_id = getattr(operator, "open_id", "") if operator else ""

            print(f"\n[callback_server] Card action received: value={str(value)[:200]}")

            # 构建回调数据
            callback_data = {
                "value": value if isinstance(value, dict) else {},
                "form_data": form_value if isinstance(form_value, dict) else {},
                "operator": {"open_id": operator_open_id},
            }

            # 调用统一处理器
            result = handle_card_callback(callback_data)

            # 构建响应
            resp = P2CardActionTriggerResponse()

            # Toast 提示
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

            # 如果有新卡片，替换原卡片
            if result.get("card"):
                cb_card = CallBackCard()
                cb_card.type = "raw"
                cb_card.data = result["card"]
                resp.card = cb_card

            return resp

        except Exception as exc:
            print(f"[callback_server] Handler error: {exc}")
            import traceback
            traceback.print_exc()
            try:
                return P2CardActionTriggerResponse()
            except Exception:
                return None

    def message_receive_handler(data):
        """接收飞书用户消息（可选，用于未来扩展客户群消息监听）。"""
        try:
            import json as _json
            msg = getattr(data, "event", None)
            if msg is None:
                return
            message = getattr(msg, "message", None)
            if message is None:
                return
            msg_type = getattr(message, "message_type", "") or ""
            if msg_type != "text":
                return
            content_raw = getattr(message, "content", "{}") or "{}"
            text = _json.loads(content_raw).get("text", "").strip()
            if text:
                print(f"[callback_server] Message received: {text[:80]}")
        except Exception as exc:
            print(f"[callback_server] Message parse error: {exc}")

    def message_read_handler(data):
        """静默忽略消息已读回执。"""
        pass

    # 注册事件处理器
    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_card_action_trigger(card_callback_handler_fn)
        .register_p2_im_message_receive_v1(message_receive_handler)
        .register_p2_im_message_message_read_v1(message_read_handler)
        .build()
    )

    # 启动 WebSocket
    ws_client = lark.ws.Client(
        app_id,
        app_secret,
        event_handler=event_handler,
        log_level=lark.LogLevel.WARNING,
    )

    print("=" * 55)
    print("  Card Callback Server — Feishu WebSocket")
    print(f"  App ID: {app_id}")
    print(f"  Env: {_env_name}")
    print(f"  Lang: {t('card.routing_title') and os.environ.get('LANG', 'zh')}")
    print("  Listening for card button callbacks...")
    print("=" * 55)

    ws_client.start()


def main():
    start_server()


if __name__ == "__main__":
    main()
