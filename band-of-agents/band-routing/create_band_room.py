"""
create_band_room.py — 创建Band Room并拉3个Agent进去

用routing-agent的身份创建Room，然后把engineering和knowledge拉进来。
创建后打印Room ID，后续3个Agent都在这个Room里协作。
"""
from __future__ import annotations

import os
import sys
import asyncio

_routing_dir = os.path.dirname(os.path.abspath(__file__))
if _routing_dir not in sys.path:
    sys.path.insert(0, _routing_dir)

# 加载环境
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

_band_env = os.path.join(_routing_dir, ".env.band")
if os.path.exists(_band_env):
    with open(_band_env) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


async def main():
    from band import Agent
    from band.core.simple_adapter import SimpleAdapter
    from band.core.types import PlatformMessage

    routing_id = os.environ.get("BAND_ROUTING_AGENT_ID", "")
    routing_key = os.environ.get("BAND_ROUTING_API_KEY", "")
    eng_handle = "@jacky231609/engineering-agent"
    kq_handle = "@jacky231609/knowledge-agent"

    print(f"\n{'='*60}")
    print(f"  Creating Band Room")
    print(f"{'='*60}")

    room_id_holder = {"id": None}

    class SetupAdapter(SimpleAdapter):
        async def on_message(self, msg, tools, history, participants_msg, contacts_msg, *, is_session_bootstrap, room_id):
            print(f"  [message] {msg.content[:100] if msg.content else '(empty)'}")

    agent = Agent.create(
        adapter=SetupAdapter(),
        agent_id=routing_id,
        api_key=routing_key,
    )

    # Agent.run() 是阻塞的，用on_started回调来创建Room
    class RoomSetupAdapter(SimpleAdapter):
        async def on_started(self, tools, room_id):
            print(f"\n✅ Connected to Band! Room ID: {room_id}")

            # 拉engineering-agent进来
            print(f"\n📨 Adding engineering-agent...")
            try:
                result = await tools.add_participant(eng_handle)
                print(f"  → {result}")
            except Exception as e:
                print(f"  → Error: {e}")

            # 拉knowledge-agent进来
            print(f"\n📨 Adding knowledge-agent...")
            try:
                result = await tools.add_participant(kq_handle)
                print(f"  → {result}")
            except Exception as e:
                print(f"  → Error: {e}")

            # 列出参与者
            print(f"\n📋 Participants:")
            try:
                participants = await tools.get_participants()
                print(f"  → {participants}")
            except Exception as e:
                print(f"  → Error: {e}")

            print(f"\n{'='*60}")
            print(f"  Room setup complete!")
            print(f"  Room ID: {room_id}")
            print(f"  Save this to .env.band as BAND_ROOM_ID")
            print(f"{'='*60}")

            # 写入.env.band
            env_path = os.path.join(_routing_dir, ".env.band")
            with open(env_path, "r") as f:
                content = f.read()
            if "BAND_ROOM_ID=" in content:
                content = content.replace("BAND_ROOM_ID=", f"BAND_ROOM_ID={room_id}")
            else:
                content += f"\nBAND_ROOM_ID={room_id}\n"
            with open(env_path, "w") as f:
                f.write(content)
            print(f"  ✅ BAND_ROOM_ID saved to .env.band")

        async def on_message(self, msg, tools, history, participants_msg, contacts_msg, *, is_session_bootstrap, room_id):
            pass

    # 重新创建agent
    agent = Agent.create(
        adapter=RoomSetupAdapter(),
        agent_id=routing_id,
        api_key=routing_key,
    )

    print("Starting agent (will auto-create room on connect)...")
    await agent.run(shutdown_timeout=30.0)


if __name__ == "__main__":
    asyncio.run(main())
