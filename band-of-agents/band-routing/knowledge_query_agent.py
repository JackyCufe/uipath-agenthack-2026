"""
knowledge_query_agent.py — 新员工知识查询 Agent

新员工输入关键词（如"9100响应慢"），Agent 从 Bitable 检索历史需求档案，
用 LLM 生成自然语言回答，通过飞书卡片发送给提问者。

复用现有 bitable_reader.py 的 search_bitable_history + get_requirement_chain。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from openai import OpenAI

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
from i18n import t, get_lang

# 工具
_tools_dir = os.path.join(_routing_dir, "tools")
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)
from bitable_reader import search_bitable_history, get_requirement_chain
from lark_notifier import send_card_to_open_id

# DeepSeek API
_DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
_DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
_DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

_llm_client = OpenAI(api_key=_DEEPSEEK_API_KEY, base_url=_DEEPSEEK_BASE_URL)


def query_knowledge(keyword: str, sender_open_id: str = "") -> dict[str, Any]:
    """
    新员工知识查询入口。

    Args:
        keyword: 搜索关键词（如"9100响应慢"）
        sender_open_id: 提问者的飞书 open_id（卡片发给他）

    Returns:
        {"ok": True/False, "message": "...", "card_sent": True/False}
    """
    print(f"\n{'='*60}")
    print(f"  Knowledge Query Agent")
    print(f"  Keyword: {keyword}")
    print(f"{'='*60}")

    # Step 1: 搜索 Bitable 历史
    print("\n[Step 1] Searching Bitable history...")
    results = search_bitable_history(keyword, top_k=5)
    print(f"  → Found {len(results)} matches")

    if not results:
        print("  → No matches found")
        card = _build_no_result_card(keyword)
        open_id = sender_open_id or os.environ.get("JACKY_OPEN_ID", "")
        send_card_to_open_id(open_id, card)
        return {"ok": True, "message": "No results", "card_sent": True}

    # Step 2: 拉取最佳匹配的完整链路
    best_match = results[0]
    req_id = best_match.get("requirement_id", "")
    print(f"\n[Step 2] Fetching full chain for {req_id}...")
    full_chain = get_requirement_chain(req_id)
    if full_chain:
        best_match = full_chain
        print(f"  → Full chain fetched, stages: {list(best_match.get('stage_data', {}).keys())}")

    # Step 3: AI 生成自然语言回答
    print("\n[Step 3] Generating AI summary...")
    ai_summary = _generate_answer(keyword, best_match)
    print(f"  → Summary generated ({len(ai_summary)} chars)")

    # Step 4: 构建并发送知识卡片
    print("\n[Step 4] Sending knowledge card...")
    card = _build_knowledge_card(keyword, best_match, ai_summary)
    open_id = sender_open_id or os.environ.get("JACKY_OPEN_ID", "")
    result = send_card_to_open_id(open_id, card)

    if result.get("ok"):
        print(f"  → Card sent successfully")
    else:
        print(f"  → Card send failed: {result.get('error')}")

    # 如果有多个匹配，也提一下
    if len(results) > 1:
        print(f"\n  Other matches:")
        for r in results[1:3]:
            print(f"    - {r.get('requirement_id')}: {r.get('title', '')[:60]}")

    print(f"\n{'='*60}")
    print(f"  Knowledge query complete ✅")
    print(f"{'='*60}")

    return {"ok": True, "message": "Query complete", "card_sent": result.get("ok", False)}


def _generate_answer(keyword: str, requirement: dict) -> str:
    """用 LLM 生成自然语言回答。"""
    stage_data = requirement.get("stage_data", {})

    # 收集关键信息
    info = {
        "requirement_id": requirement.get("requirement_id", ""),
        "title": requirement.get("title", ""),
        "stages": {},
    }
    for stage, data in stage_data.items():
        # 每个阶段提取关键文本
        stage_info = {}
        for k, v in data.items():
            if isinstance(v, str) and v:
                stage_info[k] = v[:200]
            elif isinstance(v, list) and v:
                # 人员类型
                for item in v:
                    if isinstance(item, dict):
                        stage_info[k] = item.get("en_name", item.get("name", ""))
                        break
            elif isinstance(v, (int, float)) and v:
                stage_info[k] = str(v)
        if stage_info:
            info["stages"][stage] = stage_info

    if get_lang() == "en":
        prompt = f"""You are a knowledge base assistant for a new employee. A colleague asks: "{keyword}"
Here is the historical requirement record found:

{json.dumps(info, ensure_ascii=False, indent=2)[:3000]}

Please generate a natural language answer (under 200 words) covering:
1. What was the requirement about?
2. What was the technical solution?
3. What were the acceptance criteria?
4. What was the final result?
5. Any notes or lessons learned?

Write in English. Be concise and helpful."""
    else:
        prompt = f"""你是一个新员工知识库助手。同事问："{keyword}"
以下是找到的历史需求记录：

{json.dumps(info, ensure_ascii=False, indent=2)[:3000]}

请生成一段自然语言回答（200字以内），涵盖：
1. 这个需求是关于什么的？
2. 技术方案是什么？
3. 验收标准是什么？
4. 最终结果如何？
5. 有什么注意事项或经验教训？

用中文回答，简洁有帮助。"""

    try:
        response = _llm_client.chat.completions.create(
            model=_DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": "You are a knowledge base assistant." if get_lang() == "en" else "你是一个知识库助手。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=512,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"  ⚠️ LLM failed: {e}")
        return ""


def _build_knowledge_card(keyword: str, requirement: dict, ai_summary: str) -> dict[str, Any]:
    """构建知识查询结果卡片。"""

    def _pt(content): return {"tag": "plain_text", "content": content}
    def _md(content): return {"tag": "lark_md", "content": content}
    def _div(text): return {"tag": "div", "text": text}
    def _hr(): return {"tag": "hr"}

    def _field_row(label, value):
        return {
            "tag": "column_set", "flex_mode": "none",
            "columns": [
                {"tag": "column", "width": "weighted", "weight": 1,
                 "elements": [_div(_md(f"**{label}**"))]},
                {"tag": "column", "width": "weighted", "weight": 3,
                 "elements": [_div(_pt(str(value) if value else "—"))]},
            ],
        }

    stage_data = requirement.get("stage_data", {})
    req_id = requirement.get("requirement_id", "")
    title = requirement.get("title", "")

    # 提取关键阶段信息
    s1 = stage_data.get("S1", {})
    s2 = stage_data.get("S2", {})
    s3 = stage_data.get("S3", {})
    s4 = stage_data.get("S4", {})
    s5 = stage_data.get("S5", {})
    s6 = stage_data.get("S6", {})

    # 从阶段数据中提取关键信息
    def _extract(fields_dict, keywords):
        for k, v in fields_dict.items():
            for kw in keywords:
                if kw in k:
                    if isinstance(v, str):
                        return v
                    elif isinstance(v, list) and v:
                        for item in v:
                            if isinstance(item, dict):
                                return item.get("en_name", item.get("name", ""))
        return ""

    problem = _extract(s1, ["问题", "problem"])
    expected = _extract(s1, ["期望", "expected"])
    acceptance = _extract(s2, ["验收", "标准", "acceptance"])
    tech_plan = _extract(s3, ["技术方案", "方案", "tech"])
    workload = _extract(s3, ["工作量", "workload"])
    test_result = _extract(s3, ["结论", "result", "自测"])
    version = _extract(s4, ["版本", "version"])
    satisfaction = _extract(s5, ["满意度", "satisfaction"])
    retro = _extract(s6, ["复盘", "结论", "retro"])

    # i18n 标签
    if get_lang() == "en":
        lbl_query = "Search Keyword"
        lbl_req_id = "Requirement ID"
        lbl_title = "Title"
        lbl_problem = "Problem"
        lbl_expected = "Expected Outcome"
        lbl_acceptance = "Acceptance Criteria"
        lbl_tech = "Technical Solution"
        lbl_workload = "Workload"
        lbl_test = "Test Result"
        lbl_version = "Version"
        lbl_satisfaction = "Customer Satisfaction"
        lbl_retro = "Retrospective"
        lbl_summary = "AI Summary"
        card_title = "🔍 Knowledge Query Result"
    else:
        lbl_query = "搜索关键词"
        lbl_req_id = "需求ID"
        lbl_title = "需求标题"
        lbl_problem = "问题描述"
        lbl_expected = "期望结果"
        lbl_acceptance = "验收标准"
        lbl_tech = "技术方案"
        lbl_workload = "工作量"
        lbl_test = "测试结论"
        lbl_version = "发版版本"
        lbl_satisfaction = "客户满意度"
        lbl_retro = "复盘结论"
        lbl_summary = "AI 摘要"
        card_title = "🔍 知识查询结果"

    elements = [
        _div(_md(f"**{card_title}**")),
        _hr(),
        _field_row(lbl_query, keyword),
        _field_row(lbl_req_id, req_id),
        _field_row(lbl_title, title),
        _hr(),
    ]

    # 需求详情
    if problem:
        elements.append(_field_row(lbl_problem, problem[:100]))
    if expected:
        elements.append(_field_row(lbl_expected, expected[:100]))
    if acceptance:
        elements.append(_field_row(lbl_acceptance, acceptance[:100]))
    if tech_plan:
        elements.append(_field_row(lbl_tech, tech_plan[:100]))
    if workload:
        elements.append(_field_row(lbl_workload, workload))
    if test_result:
        elements.append(_field_row(lbl_test, test_result))
    if version:
        elements.append(_field_row(lbl_version, version))
    if satisfaction:
        elements.append(_field_row(lbl_satisfaction, satisfaction))
    if retro:
        elements.append(_field_row(lbl_retro, retro[:100]))

    # AI 摘要
    if ai_summary:
        elements.append(_hr())
        elements.append(_div(_md(f"**🤖 {lbl_summary}**")))
        elements.append(_div(_pt(ai_summary)))

    return {
        "schema": "2.0",
        "header": {"title": _pt(card_title), "template": "blue"},
        "body": {"elements": elements},
    }


def _build_no_result_card(keyword: str) -> dict[str, Any]:
    """无结果时发送的卡片。"""
    def _pt(content): return {"tag": "plain_text", "content": content}
    def _md(content): return {"tag": "lark_md", "content": content}
    def _div(text): return {"tag": "div", "text": text}

    if get_lang() == "en":
        msg = f"No records found for '{keyword}'"
        title = "🔍 Knowledge Query"
    else:
        msg = f"未找到与'{keyword}'相关的记录"
        title = "🔍 知识查询"

    return {
        "schema": "2.0",
        "header": {"title": _pt(title), "template": "grey"},
        "body": {"elements": [_div(_pt(msg))]},
    }


def main():
    """命令行入口。"""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("keyword", help="Search keyword")
    parser.add_argument("sender_open_id", nargs="?", default="", help="Sender open_id (optional)")
    args, _ = parser.parse_known_args()

    result = query_knowledge(args.keyword, args.sender_open_id)
    if result.get("ok"):
        print(f"\n✅ Done")
    else:
        print(f"\n❌ Failed: {result.get('message')}")
        sys.exit(1)


# ── Band Agent 模式 ───────────────────────────────────

async def handle_band_message(content: str, sender: str, tools, room_id: str) -> str | None:
    """收到routing-agent @mention时触发知识查询。"""
    print(f"\n[Knowledge Agent] Received query from {sender}")

    # 提取查询关键词
    keyword = content
    # 去掉[QUERY]标记
    if "[QUERY]" in keyword:
        keyword = keyword.replace("[QUERY]", "").strip()

    print(f"  → Query: {keyword}")

    # 执行知识查询
    result = query_knowledge(keyword)
    if result.get("card_sent"):
        return f"Knowledge agent: card sent for '{keyword}'"
    else:
        return f"Knowledge agent: query failed - {result.get('message', '')}"


def start_band_agent():
    """以Band Agent模式启动。"""
    from band_connection import create_band_agent, start_agent_blocking

    agent_id = os.environ.get("BAND_KNOWLEDGE_AGENT_ID", "")
    api_key = os.environ.get("BAND_KNOWLEDGE_API_KEY", "")

    if not agent_id or not api_key:
        print("⚠️ BAND_KNOWLEDGE_AGENT_ID / BAND_KNOWLEDGE_API_KEY not configured")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Knowledge Agent — Starting")
    print(f"  Agent ID: {agent_id}")
    print(f"  Lang: {get_lang()}")
    print(f"{'='*60}")

    agent = create_band_agent(agent_id, api_key, handle_band_message)
    start_agent_blocking(agent)


if __name__ == "__main__":
    main()
