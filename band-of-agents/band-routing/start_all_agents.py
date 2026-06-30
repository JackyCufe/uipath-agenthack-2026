#!/usr/bin/env python3
"""
start_all_agents.py — Band Demo 主脚本

1. 创建Band Chat Room
2. 加入engineering-agent和knowledge-agent
3. 脚本发送客户反馈消息触发路由
4. routing-agent诊断→@mention engineering-agent→发飞书卡片
5. 同时支持?查询→@mention knowledge-agent→发知识卡片

Demo时：启动脚本→脚本自动跑完→去Band网页看协作记录→去飞书看卡片

用法:
  DEMO_BITABLE_TABLE_ID=tblHOdKIhmPe9l3d LANG=en python band-routing/start_all_agents.py
  DEMO_BITABLE_TABLE_ID=tblHOdKIhmPe9l3d LANG=en python band-routing/start_all_agents.py --feedback "9100 robot responds slowly"
  DEMO_BITABLE_TABLE_ID=tblHOdKIhmPe9l3d LANG=en python band-routing/start_all_agents.py --query "9100 response slow"
"""
from __future__ import annotations

import os
import sys
import asyncio
import argparse

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

from i18n import t, get_lang


async def main():
    from thenvoi_rest import AsyncRestClient, ChatRoomRequest, ChatMessageRequest, ParticipantRequest
    from thenvoi_rest.types import ChatMessageRequestMentionsItem

    parser = argparse.ArgumentParser()
    parser.add_argument("--feedback", "-f", type=str, default="9100 robot responds too slowly at hotel lobby, guests waiting too long")
    parser.add_argument("--query", "-q", type=str, default="")
    args, _ = parser.parse_known_args()

    routing_key = os.environ.get("BAND_ROUTING_API_KEY", "")
    routing_id = os.environ.get("BAND_ROUTING_AGENT_ID", "")
    eng_id = os.environ.get("BAND_ENGINEERING_AGENT_ID", "")
    kq_id = os.environ.get("BAND_KNOWLEDGE_AGENT_ID", "")

    print(f"\n{'='*60}")
    print(f"  🚀 Band Demo — Multi-Agent Collaboration")
    print(f"  Lang: {get_lang()}")
    print(f"{'='*60}")

    client = AsyncRestClient(api_key=routing_key, base_url="https://app.band.ai")

    # 1. 创建chat
    print("\n📦 Step 1: Creating chat room...")
    resp = await client.agent_api_chats.create_agent_chat(chat=ChatRoomRequest())
    chat_id = resp.data.id
    print(f"  ✅ Chat: {chat_id}")

    # 2. 加入engineering和knowledge
    print("\n👥 Step 2: Adding participants...")
    for pid, name in [(eng_id, "engineering-agent"), (kq_id, "knowledge-agent")]:
        try:
            await client.agent_api_participants.add_agent_chat_participant(
                chat_id=chat_id,
                participant=ParticipantRequest(participant_id=pid),
            )
            print(f"  ✅ {name} added")
        except Exception as e:
            err = str(e)
            if "already" in err.lower():
                print(f"  ✅ {name} already in room")
            else:
                print(f"  ⚠️ {name}: {err[:80]}")

    # 3. 发送消息触发路由（@mention routing-agent）
    if args.query:
        # 查询模式
        print(f"\n📤 Step 3: Sending query '{args.query}'...")
        # @mention routing-agent来触发
        mention = ChatMessageRequestMentionsItem(id=routing_id)
        # 不能@mention自己，用eng_id作为发送者mention routing
        # 实际上：用routing-agent自己发消息，不@mention任何人
        # 但Band要求mentions至少1个——@mention engineering-agent作为"请协助"
        # 不对，应该用另一个agent的身份发消息@mention routing
        # 最简单：routing-agent自己发消息，@mention eng（触发后续路由）
        # 但routing-agent需要先收到消息才能处理
        #
        # 换思路：routing-agent直接处理，不通过@mention触发
        # routing-agent发一条消息说"收到查询"，然后处理
        await client.agent_api_messages.create_agent_chat_message(
            chat_id=chat_id,
            message=ChatMessageRequest(content=f"?{args.query}", mentions=[ChatMessageRequestMentionsItem(id=eng_id)]),
        )
        print(f"  ✅ Query sent")

        # 直接执行路由逻辑
        print(f"\n⏳ Processing...")
        await _poll_and_route(client, chat_id, eng_id, kq_id, is_query=True, query_keyword=args.query)

    else:
        # 反馈模式
        print(f"\n📤 Step 3: Sending feedback '{args.feedback[:60]}...'...")
        await client.agent_api_messages.create_agent_chat_message(
            chat_id=chat_id,
            message=ChatMessageRequest(content=args.feedback, mentions=[ChatMessageRequestMentionsItem(id=eng_id)]),
        )
        print(f"  ✅ Feedback sent")

        # 直接执行路由逻辑
        print(f"\n⏳ Processing...")
        await _poll_and_route(client, chat_id, eng_id, kq_id, is_query=False, feedback=args.feedback)

    print(f"\n{'='*60}")
    print(f"  🎬 Demo complete!")
    print(f"  Chat ID: {chat_id}")
    print(f"  Check Band web UI for collaboration records")
    print(f"  Check Feishu for cards")
    print(f"{'='*60}")


async def _poll_and_route(client, chat_id, eng_id, kq_id, is_query=False, query_keyword="", feedback=""):
    """routing-agent处理路由，engineering/knowledge在Band Room回复。"""
    from routing_agent import RoutingAgent
    from engineering_agent import handle_message_sync
    from knowledge_query_agent import query_knowledge
    from thenvoi_rest.types import ChatMessageRequestMentionsItem
    from thenvoi_rest import ChatMessageRequest, AsyncRestClient

    routing_id = os.environ.get("BAND_ROUTING_AGENT_ID", "")
    eng_key = os.environ.get("BAND_ENGINEERING_API_KEY", "")
    kq_key = os.environ.get("BAND_KNOWLEDGE_API_KEY", "")
    eng_client = AsyncRestClient(api_key=eng_key, base_url="https://app.band.ai")
    kq_client = AsyncRestClient(api_key=kq_key, base_url="https://app.band.ai")

    if is_query:
        print(f"\n🤖 [Routing Agent] QUERY intent: '{query_keyword}'")
        print(f"  → @mention @knowledge-agent")

        await client.agent_api_messages.create_agent_chat_message(
            chat_id=chat_id,
            message=ChatMessageRequest(
                content=f"[QUERY] {query_keyword}",
                mentions=[ChatMessageRequestMentionsItem(id=kq_id)],
            ),
        )
        print(f"  ✅ @mention sent in Band Room")

        result = query_knowledge(query_keyword)
        if result.get("card_sent"):
            print(f"  ✅ Knowledge card sent to Feishu")
            # knowledge-agent回复
            await kq_client.agent_api_messages.create_agent_chat_message(
                chat_id=chat_id,
                message=ChatMessageRequest(
                    content=f"Found DEMO-001 — full history with AI summary sent to Feishu.",
                    mentions=[ChatMessageRequestMentionsItem(id=routing_id)],
                ),
            )
            print(f"  ✅ Knowledge agent replied in Band Room")
        else:
            print(f"  ❌ Knowledge query failed")

    else:
        print(f"\n🤖 [Routing Agent] FEEDBACK intent → diagnosing...")

        product_model = ""
        for model in ["9100", "8200", "X1"]:
            if model in feedback:
                product_model = model
                break

        agent = RoutingAgent()
        decision = agent.process_feedback(
            feedback_text=feedback,
            customer_id="Liming International Hotel",
            product_model=product_model,
        )

        if decision:
            routing_msg = agent._format_routing_message(decision)
            routing_msg += f"\n\nfeedback_text: {feedback}"
            routing_msg += f"\ncustomer_id: Liming International Hotel"

            print(f"  → @mention @engineering-agent")
            await client.agent_api_messages.create_agent_chat_message(
                chat_id=chat_id,
                message=ChatMessageRequest(
                    content=routing_msg,
                    mentions=[ChatMessageRequestMentionsItem(id=eng_id)],
                ),
            )
            print(f"  ✅ @mention sent in Band Room")

            print(f"\n🔧 [Engineering Agent] Processing...")
            handle_message_sync(routing_msg, "routing-agent")
            print(f"  ✅ Engineering card sent to Feishu")

            # engineering-agent回复
            await eng_client.agent_api_messages.create_agent_chat_message(
                chat_id=chat_id,
                message=ChatMessageRequest(
                    content=f"Card sent to engineer. Waiting for resolve action.",
                    mentions=[ChatMessageRequestMentionsItem(id=routing_id)],
                ),
            )
            print(f"  ✅ Engineering agent replied in Band Room")


if __name__ == "__main__":
    asyncio.run(main())
