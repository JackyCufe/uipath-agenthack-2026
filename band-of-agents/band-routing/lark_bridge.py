"""
lark_bridge.py — 飞书消息→Band Room 桥接层

监听飞书群消息，收到客户后续反馈后转发到 Band Room，@routing-agent。

单向转发，不做任何判断。
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

# 加载飞书配置
_PIPELINE_DIR = os.path.join(os.path.dirname(__file__), "..", "ai-requirement-pipeline", "pipeline")
_PIPELINE_DIR = os.path.abspath(_PIPELINE_DIR)
if _PIPELINE_DIR not in sys.path:
    sys.path.insert(0, _PIPELINE_DIR)

_env_name = os.environ.get("FEISHU_ENV", "team-testing")
_env_file = os.path.join(_PIPELINE_DIR, f".env.{_env_name}")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


class LarkBridge:
    """
    飞书消息桥接器。

    监听飞书群消息 → 转发到 Band Room → @routing-agent

    在真实模式下：连接飞书 WebSocket + Band SDK
    在测试模式下：harness 直接调用 forward_message()
    """

    def __init__(self, band_room=None):
        """
        Args:
            band_room: Band Room 接口（用于发消息）
        """
        self.band_room = band_room

    def forward_message(self, customer_id: str, feedback_text: str) -> dict[str, Any]:
        """
        转发飞书消息到 Band Room。

        Args:
            customer_id: 客户标识
            feedback_text: 客户反馈原文

        Returns:
            {"ok": True/False, "message": "..."}
        """
        # 格式化消息
        message = f"[FEEDBACK] {customer_id}: {feedback_text}"

        print(f"[LarkBridge] 转发消息到 Band Room:")
        print(f"  客户: {customer_id}")
        print(f"  反馈: {feedback_text[:80]}...")

        # 发送到 Band Room
        if self.band_room:
            self.band_room.send_message(
                content=message,
                mentions=["@routing-agent"],
            )
            return {"ok": True, "message": "forwarded to Band Room"}
        else:
            print("[LarkBridge] ⚠️ 未连接 Band Room，消息未转发")
            return {"ok": False, "message": "no band_room connected"}

    async def start(self):
        """启动飞书 WebSocket 监听。"""
        try:
            import lark_oapi as lark
            from lark_oapi.api.im.v1 import (
                ReceiveMessageEvent,
                ReceiveMessageRequest,
            )
        except ImportError:
            print("[LarkBridge] ⚠️ lark_oapi 未安装")
            print("[LarkBridge] 请安装: pip install lark-oapi")
            return

        app_id = os.environ.get("FEISHU_APP_ID", "")
        app_secret = os.environ.get("FEISHU_APP_SECRET", "")

        if not app_id or not app_secret:
            print("[LarkBridge] ⚠️ FEISHU_APP_ID/FEISHU_APP_SECRET 未配置")
            return

        # 创建飞书 App
        app = lark.Client.builder() \
            .app_id(app_id) \
            .app_secret(app_secret) \
            .build()

        # 注册事件处理器
        async def handle_message(event: ReceiveMessageEvent):
            """收到飞书群消息时触发。"""
            try:
                msg_content = json.loads(event.event.message.content)
                text = msg_content.get("text", "")

                # 获取发送者信息
                sender_id = event.event.sender.sender_id.open_id

                # 获取群聊ID
                chat_id = event.event.message.chat_id

                print(f"[LarkBridge] 收到飞书消息: {text[:80]}...")

                # 转发到 Band Room
                self.forward_message(
                    customer_id=sender_id,
                    feedback_text=text,
                )

            except Exception as e:
                print(f"[LarkBridge] 处理消息异常: {e}")

        # 启动 WebSocket 监听
        print("[LarkBridge] 启动飞书 WebSocket 监听...")
        print(f"[LarkBridge] App ID: {app_id}")

        # TODO: 接入真实 lark_oapi WebSocket
        # 当前是占位，需要根据 lark_oapi 版本调整
        # 参考：ai-requirement-pipeline/pipeline/card_handler.py 中的 WebSocket 实现
        print("[LarkBridge] ⚠️ WebSocket 监听需要根据 lark_oapi 版本配置")
        print("[LarkBridge] 参考 card_handler.py 的实现")


def main():
    """命令行入口。"""
    import asyncio

    bridge = LarkBridge()
    asyncio.run(bridge.start())


if __name__ == "__main__":
    main()
