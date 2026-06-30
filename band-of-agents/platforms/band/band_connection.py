"""
band_connection.py — Band SDK 连接管理器

3个Agent共用这个模块连接Band平台。
每个Agent用SimpleAdapter监听Band Room消息，收到@mention时触发处理。
"""
from __future__ import annotations

import os
import sys
import asyncio
import threading
from typing import Any, Callable

# 确保band-routing在path中
_routing_dir = os.path.dirname(os.path.abspath(__file__))
if _routing_dir not in sys.path:
    sys.path.insert(0, _routing_dir)

from i18n import t, get_lang

# 加载飞书环境
_pipeline_dir = os.path.join(_routing_dir, "..", "ai-requirement-pipeline", "pipeline")
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

# 加载Band环境
_band_env = os.path.join(_routing_dir, ".env.band")
if os.path.exists(_band_env):
    with open(_band_env) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def create_band_agent(
    agent_id: str,
    api_key: str,
    on_message_handler: Callable,
) -> Any:
    """
    创建一个Band Agent，连接Band Room，监听@mention。

    Args:
        agent_id: Band Agent ID
        api_key: Band API Key
        on_message_handler: 收到消息时的回调函数
            async def handler(msg_content, sender, tools, room_id) -> str | None
            返回值：要发送的回复消息（None=不回复）

    Returns:
        Band Agent实例（调用 .run() 启动）
    """
    from band import Agent
    from band.core.simple_adapter import SimpleAdapter
    from band.core.types import PlatformMessage, AgentInput
    from band.core.protocols import AgentToolsProtocol

    class CustomAdapter(SimpleAdapter):
        """自定义适配器，收到消息时调用handler。"""

        async def on_message(
            self,
            msg: PlatformMessage,
            tools: AgentToolsProtocol,
            history,
            participants_msg,
            contacts_msg,
            *,
            is_session_bootstrap: bool,
            room_id: str,
        ) -> None:
            """收到Band Room消息时触发。"""
            content = msg.content or ""
            sender = msg.sender_name or msg.sender_id or "unknown"

            # 打印收到的消息
            print(f"\n{'='*60}")
            print(f"  [Band] Message from {sender}:")
            print(f"  {content[:200]}")
            print(f"{'='*60}")

            # 调用handler处理
            try:
                reply = await on_message_handler(content, sender, tools, room_id)
                if reply:
                    print(f"  [Band] Sending reply: {reply[:100]}...")
                    await tools.send_message(content=reply)
            except Exception as e:
                print(f"  [Band] Handler error: {e}")
                import traceback
                traceback.print_exc()

    adapter = CustomAdapter()

    agent = Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
    )

    return agent


def start_agent_in_thread(agent):
    """在后台线程启动Agent（非阻塞）。"""
    def _run():
        try:
            asyncio.run(agent.run())
        except Exception as e:
            print(f"  [Band] Agent error: {e}")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


def start_agent_blocking(agent):
    """阻塞启动Agent（前台）。"""
    asyncio.run(agent.run())
