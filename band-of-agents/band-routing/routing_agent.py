"""
routing_agent.py — 路由分诊 Agent

核心逻辑：
1. 收到客户反馈
2. 查 Bitable 历史
3. AI 诊断问题类型
4. 判断切入阶段
5. 输出路由决策 JSON
6. @mention 对应 Pipeline Agent（通过 Band Room）
7. 发飞书卡片通知负责人

支持两种运行模式：
- 真实模式：连接 Band Room，常驻监听 @mention
- 测试模式：harness 注入 mock，直接调用 process_feedback()
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from openai import OpenAI

# i18n
from i18n import t, get_lang

# ── 配置 ──────────────────────────────────────────────

def _load_env():
    """加载飞书 .env 配置（复用 pipeline 的 .env 文件）。"""
    _env_name = os.environ.get("FEISHU_ENV", "team-testing")
    _pipeline_dir = os.path.join(os.path.dirname(__file__), "..", "ai-requirement-pipeline", "pipeline")
    _pipeline_dir = os.path.abspath(_pipeline_dir)
    _env_file = os.path.join(_pipeline_dir, f".env.{_env_name}")
    if os.path.exists(_env_file):
        with open(_env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())
        print(f"[routing_agent] {t('log.loading_env', name=_env_name)} ({os.path.basename(_env_file)})")

_load_env()

# DeepSeek API（OpenAI 兼容）
_DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
_DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
_DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

_llm_client = OpenAI(
    api_key=_DEEPSEEK_API_KEY,
    base_url=_DEEPSEEK_BASE_URL,
)

# 路由提示词（按语言选择）
if get_lang() == "en":
    _PROMPT_PATH = Path(__file__).parent / "prompts" / "routing_prompt_en.md"
else:
    _PROMPT_PATH = Path(__file__).parent / "prompts" / "routing_prompt.md"
_ROUTING_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

# ── 路由规则（确定性映射，不依赖 LLM）──

_DIAGNOSIS_TO_STAGE = {
    "tech_bug":        {"entry_stage": 3, "target_agent": "@s3-agent"},
    "service_issue":   {"entry_stage": 2, "target_agent": "@s2-agent"},
    "new_requirement": {"entry_stage": 1, "target_agent": "@s1-agent"},
    "complaint":       {"entry_stage": 5, "target_agent": "@s5-agent"},
}


# ── RoutingAgent 类 ───────────────────────────────────

class RoutingAgent:
    """
    路由分诊 Agent。

    在真实模式下：连接 Band Room，监听 @mention，自动处理反馈。
    在测试模式下：接受 mock 组件，直接调用 process_feedback()。
    """

    def __init__(
        self,
        band_room=None,
        lark_card=None,
        bitable_reader=None,
        trace_writer=None,
    ):
        """
        Args:
            band_room: Band Room 接口（真实 Band SDK 或 MockBandRoom）
            lark_card: 飞书卡片接口（真实 lark_notifier 或 MockLarkCard）
            bitable_reader: Bitable 读取接口（真实 bitable_reader 或 MockBitableReader）
            trace_writer: feedback_trace 写入接口
        """
        self.band_room = band_room
        self.lark_card = lark_card
        self.bitable_reader = bitable_reader
        self.trace_writer = trace_writer

        # 如果没有注入 bitable_reader，用真实实现
        if self.bitable_reader is None:
            from bitable_reader import search_bitable_history, get_requirement_chain
            self.bitable_reader = _RealBitableReader(search_bitable_history, get_requirement_chain)

        # 如果没有注入 lark_card，用真实实现
        if self.lark_card is None:
            from lark_notifier import notify_via_lark
            self.lark_card = _RealLarkCard(notify_via_lark)

    def pre_confirm(
        self,
        feedback_text: str,
        product_model: str = "",
        customer_id: str = "",
        customer_open_id: str = "",
    ) -> dict[str, Any]:
        """
        第一步：发确认卡片给客户，等客户确认后才触发路由。

        Args:
            feedback_text: 客户反馈原文
            product_model: 产品型号
            customer_id: 客户标识
            customer_open_id: 客户的飞书 open_id

        Returns:
            {"ok": True, "message": "确认卡片已发送"}
        """
        print(f"\n{'='*60}")
        print(f"  RoutingAgent — {t('log.sending_confirm_card')}")
        print(f"  Customer: {customer_id}")
        print(f"  Product: {product_model}")
        print(f"  Feedback: {feedback_text[:100]}...")
        print(f"{'='*60}")

        # AI 生成反馈摘要
        ai_summary = self._generate_feedback_summary(feedback_text)

        # 构建确认卡片
        from lark_notifier import build_customer_confirm_card, send_card_to_open_id

        card = build_customer_confirm_card(
            feedback_text=feedback_text,
            product_model=product_model,
            customer_id=customer_id,
            ai_summary=ai_summary,
        )

        # 发给客户
        open_id = customer_open_id or os.environ.get("JACKY_OPEN_ID", "")
        result = send_card_to_open_id(open_id, card)

        if result.get("ok"):
            print(f"  → {t('log.confirm_card_sent')}")
        else:
            print(f"  → {t('log.confirm_card_failed', error=result.get('error'))}")

        return result

    def _generate_feedback_summary(self, feedback_text: str) -> str:
        """用 LLM 生成反馈摘要，供客户确认卡片展示。"""
        try:
            response = _llm_client.chat.completions.create(
                model=_DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": t('log.summary_failed', error='') if False else "你是一个客服助手。用一句话总结客户的反馈内容，不超过50字。" if get_lang() == 'zh' else "You are a customer service assistant. Summarize the customer's feedback in one sentence, under 50 words."},
                    {"role": "user", "content": f"客户反馈：{feedback_text}\n\n请用一句话总结。"},
                ],
                max_tokens=128,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            print(f"  ⚠️ {t('log.summary_failed', error=e)}")
            return ""

    def process_feedback(
        self,
        feedback_text: str,
        customer_id: str = "",
        product_model: str = "",
    ) -> dict[str, Any]:
        """
        处理客户后续反馈，返回路由决策。

        这是核心方法，harness 直接调用它测试。

        Args:
            feedback_text: 客户反馈原文
            customer_id: 客户标识
            product_model: 产品型号（如 9100/8200/X1），用于精准匹配历史需求

        Returns:
            路由决策 JSON（见 routing_prompt.md 中的输出格式）
        """
        print(f"\n{'='*60}")
        print(f"  RoutingAgent — {t('log.processing_feedback')}")
        print(f"  Customer: {customer_id}")
        if product_model:
            print(f"  Product Model: {product_model}")
        print(f"  Feedback: {feedback_text[:100]}...")
        print(f"{'='*60}")

        # Step 1: 查 Bitable 历史（带产品型号筛选）
        print(f"\n[Step 1] {t('log.searching_bitable')}...")
        history_results = self.bitable_reader.search(feedback_text, top_k=5, product_model=product_model)
        print(f"  → {t('log.found_matches', count=len(history_results))}")

        matched_requirement = None
        if history_results:
            # 取相似度最高的（第一个）
            matched_requirement = history_results[0]
            print(f"  → {t('log.best_match', req_id=matched_requirement['requirement_id'], title=matched_requirement.get('title', '')[:60])}")

            # Step 2: 拉取完整链路
            print(f"\n[Step 2] {t('log.fetching_chain', req_id=matched_requirement['requirement_id'])}...")
            full_chain = self.bitable_reader.get_chain(matched_requirement["requirement_id"])
            if full_chain:
                matched_requirement = full_chain
                print(f"  → {t('log.chain_success', stages=list(matched_requirement.get('stage_data', {}).keys()))}")
            else:
                print(f"  → {t('log.chain_failed')}")
        else:
            print(f"  → {t('log.no_match')}")

        # Step 3: AI 诊断
        print(f"\n[Step 3] {t('log.ai_diagnosing')}...")
        diagnosis = self._diagnose(feedback_text, matched_requirement)
        print(f"  → {t('log.diagnosis_result', type=diagnosis.get('diagnosis_type', 'unknown'))}")
        print(f"  → {t('log.severity_result', severity=diagnosis.get('severity', 'unknown'))}")

        # Step 4: 确定切入阶段
        diag_type = diagnosis.get("diagnosis_type", "new_requirement")
        stage_info = _DIAGNOSIS_TO_STAGE.get(diag_type, _DIAGNOSIS_TO_STAGE["new_requirement"])
        diagnosis["entry_stage"] = stage_info["entry_stage"]
        diagnosis["target_agent"] = stage_info["target_agent"]

        if matched_requirement:
            diagnosis["matched_requirement_id"] = matched_requirement.get("requirement_id", "")
            diagnosis["matched_requirement_title"] = matched_requirement.get("title", "")
        else:
            diagnosis["matched_requirement_id"] = None
            diagnosis["matched_requirement_title"] = None

        # 补充上下文摘要
        diagnosis["context_summary"] = self._build_context_summary(feedback_text, matched_requirement, diagnosis)

        print(f"\n[Step 4] {t('log.routing_decision')}:")
        print(f"  → {t('log.entry_stage', stage=diagnosis['entry_stage'])}")
        print(f"  → {t('log.target_agent', agent=diagnosis['target_agent'])}")
        print(f"  → {t('log.matched_req', req_id=diagnosis.get('matched_requirement_id', t('placeholder.dash')))}")

        # Step 5: @mention 对应 Agent（通过 Band Room）
        if self.band_room:
            print(f"\n[Step 5] {t('log.sending_band_msg')}...")
            routing_message = self._format_routing_message(diagnosis)
            self.band_room.send_message(
                content=routing_message,
                mentions=[diagnosis["target_agent"]],
            )
            print(f"  → {t('log.mention', agent=diagnosis['target_agent'])}")

        # Step 6: 发飞书卡片通知负责人
        if self.lark_card:
            print(f"\n[Step 6] {t('log.sending_lark_card')}...")
            owner_open_id, owner_name = self._get_stage_owner(
                diagnosis["entry_stage"], matched_requirement
            )
            print(f"  → {t('log.owner', name=owner_name)}")
            if hasattr(self.lark_card, '_notify_fn') and self.lark_card._notify_fn:
                # 真实 _RealLarkCard
                result = self.lark_card._notify_fn(
                    diagnosis,
                    feedback_text=feedback_text,
                    customer_id=customer_id,
                    owner_open_id=owner_open_id,
                    owner_name=owner_name,
                )
                if result.get("ok", False):
                    print(f"  → {t('log.card_sent_ok')}")
                else:
                    print(f"  → {t('log.card_sent_fail', error=result.get('error', 'unknown'))}")
            else:
                # mock MockLarkCard
                card_result = self.lark_card.send_card(
                    open_id=owner_open_id,
                    card_json=diagnosis,
                )
                if card_result.get("ok", False) or card_result.get("card"):
                    print(f"  → {t('log.card_sent_ok')}")
                else:
                    print(f"  → {t('log.card_sent_fail', error=card_result.get('error', 'unknown'))}")

        # Step 7: 写入 feedback_trace
        if self.trace_writer:
            print(f"\n[Step 7] {t('log.writing_trace')}...")
            trace = {
                "original_feedback": feedback_text,
                "customer_id": customer_id,
                "diagnosis_type": diagnosis.get("diagnosis_type"),
                "matched_requirement_id": diagnosis.get("matched_requirement_id"),
                "entry_stage": diagnosis.get("entry_stage"),
                "severity": diagnosis.get("severity"),
                "routing_target": diagnosis.get("target_agent"),
                "resolution": None,
            }
            self.trace_writer.write(trace)
            print(f"  → {t('log.trace_written')}")

        print(f"\n{'='*60}")
        print(f"  {t('log.routing_complete')}")
        print(f"{'='*60}")

        return diagnosis

    def _diagnose(self, feedback_text: str, matched_requirement: dict | None) -> dict[str, Any]:
        """调用 LLM 诊断问题类型。"""
        # 构建上下文
        context = ""
        if matched_requirement:
            stage_data = matched_requirement.get("stage_data", {})
            context = f"\n\n{"历史需求档案:" if get_lang() == 'zh' else 'Historical Requirement Archive:'}\n"
            context += f"{"需求ID" if get_lang() == 'zh' else 'Requirement ID'}: {matched_requirement.get('requirement_id', '')}\n"
            context += f"标题: {matched_requirement.get('title', '')}\n"
            for stage, data in stage_data.items():
                context += f"{stage}: {json.dumps(data, ensure_ascii=False)[:200]}\n"
        else:
            context = f"\n\n{"无匹配的历史需求档案（全新需求）。" if get_lang() == 'zh' else 'No matching historical requirement (new requirement).'}\n"

        user_message = f"{'客户反馈' if get_lang() == 'zh' else 'Customer feedback'}: {feedback_text}\n{'客户标识' if get_lang() == 'zh' else 'Customer ID'}: {matched_requirement.get('requirement_id', 'unknown') if matched_requirement else 'unknown'}{context}\n\n{'请诊断问题类型并返回路由决策 JSON。' if get_lang() == 'zh' else 'Please diagnose the issue type and return a routing decision JSON.'}"

        try:
            response = _llm_client.chat.completions.create(
                model=_DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": _ROUTING_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=1024,
            )
            raw_text = response.choices[0].message.content or ""

            # 提取 JSON
            diagnosis = self._extract_json(raw_text)
            if diagnosis:
                return diagnosis

            # 兜底：无法解析 LLM 输出，默认新需求
            print(f"  ⚠️ LLM 输出解析失败，降级为 new_requirement")
            print(f"  raw: {raw_text[:200]}")
            return {
                "diagnosis_type": "new_requirement",
                "severity": "normal",
                "entry_reason": "LLM诊断失败，降级为全新需求",
            }

        except Exception as e:
            print(f"  ⚠️ LLM 调用失败: {e}")
            return {
                "diagnosis_type": "new_requirement",
                "severity": "normal",
                "entry_reason": f"LLM调用异常，降级为全新需求: {e}",
            }

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        """从 LLM 输出文本中提取 JSON 对象。"""
        # 先找 ```json 块
        blocks = re.findall(r'```json\s*([\s\S]*?)\s*```', text)
        for block in blocks:
            try:
                return json.loads(block.strip())
            except json.JSONDecodeError:
                pass

        # 再找裸 JSON 对象
        matches = re.findall(r'\{[\s\S]*\}', text)
        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                # 尝试修复
                repaired = self._repair_json(match)
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    pass

        return None

    def _repair_json(self, text: str) -> str:
        """简单 JSON 修复：处理常见 LLM 输出问题。"""
        # 替换 null 为 None 再转回 null（处理 Python None 的问题）
        text = text.replace("None", "null")
        # 去除尾部逗号
        text = re.sub(r',\s*}', '}', text)
        text = re.sub(r',\s*]', ']', text)
        return text

    def _build_context_summary(
        self,
        feedback_text: str,
        matched_requirement: dict | None,
        diagnosis: dict[str, Any],
    ) -> str:
        """用 LLM 生成针对性的上下文摘要，根据路由目标突出不同信息。"""
        entry_stage = diagnosis.get("entry_stage", 1)
        diag_type = diagnosis.get("diagnosis_type", "unknown")

        # 收集原始数据
        raw_data = {"feedback": feedback_text}
        if matched_requirement:
            raw_data["requirement_id"] = matched_requirement.get("requirement_id", "")
            raw_data["title"] = matched_requirement.get("title", "")
            raw_data["stage_data"] = matched_requirement.get("stage_data", {})
        else:
            raw_data["requirement_id"] = None
            raw_data["stage_data"] = {}

        # 按路由目标定制提示
        if get_lang() == "en":
            role_hints = {
                1: "Highlight: who is the customer, what scenario, what problem, what expected outcome",
                2: "Highlight: acceptance criteria, priority, core value",
                3: "Highlight: technical solution, workload, test cases, how it was implemented",
                4: "Highlight: release version, release date, scenario verification",
                5: "Highlight: customer satisfaction, historical feedback summary",
            }
            role_hint = role_hints.get(entry_stage, "Highlight key information")

            prompt = f"""You are a requirement management assistant. Based on the following data, generate a concise context summary for a {diag_type} type issue.

Requirements:
- {role_hint}
- Write in natural language, no pipe-delimited fields
- Keep under 100 words
- Help the handler quickly understand the background

Data:
{json.dumps(raw_data, ensure_ascii=False, indent=2)[:2000]}

Output the summary text directly, no markers."""
        else:
            role_hints = {
                1: "突出：客户是谁、什么场景、遇到什么问题、期望什么结果",
                2: "突出：验收标准是什么、优先级如何、核心价值是什么",
                3: "突出：技术方案是什么、工作量多少、测试用例是什么、当时怎么实现的",
                4: "突出：发版版本、发版日期、场景验证情况",
                5: "突出：客户满意度、历史反馈摘要",
            }
            role_hint = role_hints.get(entry_stage, "突出关键信息")

            prompt = f"""你是一个需求管理系统的助手。请根据以下信息，为{diag_type}类型的问题生成一段简洁的上下文摘要。

要求：
- {role_hint}
- 用自然语言写，不要用竖线拼接
- 控制在100字以内
- 让接手的人快速了解背景

数据：
{json.dumps(raw_data, ensure_ascii=False, indent=2)[:2000]}

直接输出摘要文本，不要加任何标记。"""

        try:
            response = _llm_client.chat.completions.create(
                model=_DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": "You are a requirement management assistant skilled at generating concise context summaries." if get_lang() == "en" else "你是一个需求管理助手，擅长生成简洁的上下文摘要。"},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=256,
            )
            summary = (response.choices[0].message.content or "").strip()
            if summary:
                return summary
        except Exception as e:
            print(f"  ⚠️ 上下文摘要 LLM 调用失败: {e}")

        # 兜底：用原来的机械拼接
        parts = [f"客户反馈：{feedback_text[:100]}"]
        if matched_requirement:
            parts.append(f"匹配需求：{matched_requirement.get('requirement_id', '')}")
            stage_data = matched_requirement.get("stage_data", {})
            if "S2" in stage_data:
                for k, v in stage_data["S2"].items():
                    if "验收" in k or "标准" in k:
                        parts.append(f"验收标准：{str(v)}")
                        break
        parts.append(f"诊断：{diag_type}")
        return " | ".join(parts)

    def _format_routing_message(self, decision: dict[str, Any]) -> str:
        """格式化 Band Room 路由消息。"""
        return (
            f"[ROUTING] {json.dumps(decision, ensure_ascii=False)}\n\n"
            f"路由决策：{decision.get('diagnosis_type', 'unknown')} → "
            f"S{decision.get('entry_stage', 1)}\n"
            f"匹配需求：{decision.get('matched_requirement_id', '无')}\n"
            f"严重程度：{decision.get('severity', 'normal')}\n"
            f"上下文：{decision.get('context_summary', '')}"
        )

    def _get_stage_owner(self, stage: int, matched_requirement: dict | None = None) -> tuple[str, str]:
        """
        获取阶段负责人。

        优先从 Bitable 历史记录中提取做过这个需求的人（matched_requirement）。
        如果没有历史记录，降级为环境变量配置的默认人。

        Returns:
            (open_id, role_name)
        """
        # 优先从历史记录提取
        if matched_requirement:
            stage_data = matched_requirement.get("stage_data", {})
            stage_key = f"S{stage}"
            stage_fields = stage_data.get(stage_key, {})
            # 找负责人字段
            owner_key = f"S{stage}_负责人"
            owner_data = stage_fields.get(owner_key, [])
            if not owner_data:
                # 在所有字段里找带"负责人"的
                for k, v in stage_fields.items():
                    if "负责人" in k and isinstance(v, list) and v:
                        owner_data = v
                        break
            if owner_data and isinstance(owner_data, list):
                person = owner_data[0]
                open_id = person.get("id", "")
                name = person.get("en_name", person.get("name", ""))
                if open_id:
                    print(f"  → {t('log.owner_extracted', name=name, oid=open_id[:12]+'...')}")
                    return open_id, name

        # 降级：环境变量
        role_names = {1: t("role.presales"), 2: t("role.pm"), 3: t("role.rd"), 4: t("role.product_owner"), 5: t("role.after_sales"), 6: t("role.all")}
        role = role_names.get(stage, t("role.default"))
        env_key = f"STAGE{stage}_OWNER_OPEN_ID"
        open_id = os.environ.get(env_key, "")
        if not open_id:
            open_id = os.environ.get("JACKY_OPEN_ID", "")
        return open_id, role


# ── 真实实现包装器 ─────────────────────────────────────

class _RealBitableReader:
    """真实 Bitable 读取实现。"""
    def __init__(self, search_fn, get_chain_fn):
        self._search_fn = search_fn
        self._get_chain_fn = get_chain_fn

    def search(self, keyword: str, top_k: int = 5, product_model: str = "") -> list[dict[str, Any]]:
        return self._search_fn(keyword, top_k, product_model) if product_model else self._search_fn(keyword, top_k)

    def get_chain(self, requirement_id: str) -> dict[str, Any] | None:
        return self._get_chain_fn(requirement_id)


class _RealLarkCard:
    """真实飞书卡片发送实现。"""
    def __init__(self, notify_fn):
        self._notify_fn = notify_fn

    def send_card(self, open_id: str, card_json: dict[str, Any]) -> dict[str, Any]:
        # notify_via_lark 接收 routing_decision + feedback_text + customer_id
        # card_json 就是 routing_decision，open_id 在 notify_via_lark 内部解析
        result = self._notify_fn(card_json)
        return result


# ── Band Room 真实适配器 ───────────────────────────────

class BandRoomAdapter:
    """
    Band Room 适配器。

    在真实模式下，通过 Band SDK 连接 Band Room。
    Agent 被 @mention 时，调用 process_feedback()。

    用法:
        adapter = BandRoomAdapter(agent_id="...", api_key="...")
        adapter.start()  # 阻塞运行
    """

    def __init__(self, agent_id: str = "", api_key: str = ""):
        self.agent_id = agent_id or os.environ.get("BAND_AGENT_ID", "")
        self.api_key = api_key or os.environ.get("BAND_API_KEY", "")
        self.routing_agent = RoutingAgent(band_room=self)
        self._agent = None

    def send_message(self, content: str, mentions: list[str] | None = None) -> dict[str, Any]:
        """发送消息到 Band Room（@mention 其他 Agent）。

        TODO: 接入真实 Band SDK 的 tools.send_message。
        当前是占位实现，真实运行时由 Band SDK 的 AgentTools 接管。
        """
        print(f"[BandRoom] 发送消息: {content[:80]}... mentions={mentions}")
        return {"ok": True, "content": content, "mentions": mentions}

    async def start(self):
        """启动 Band Agent，常驻监听 @mention。"""
        try:
            from band import Agent
            from band.core.simple_adapter import SimpleAdapter
            from band.core.types import PlatformMessage, AgentInput
            from band.core.protocols import AgentToolsProtocol
        except ImportError:
            print(f"[{t('log.band_not_installed') if False else t('log.band_not_installed')}]")
            print(f"{t('log.band_install_hint')}")
            return

        # 创建自定义 SimpleAdapter
        class RoutingAdapter(SimpleAdapter):
            """Band SDK 适配器：收到消息时识别意图，@mention对应Agent。"""

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
                """收到 Band Room 消息时触发。"""
                content = (msg.content or "").strip()
                sender = msg.sender_name or msg.sender_id or "unknown"

                print(f"\n{'='*60}")
                print(f"  [Routing Agent] Message from {sender}:")
                print(f"  {content[:150]}")
                print(f"{'='*60}")

                # 提取实际内容（去掉 [FEEDBACK] 标记）
                if content.startswith("[FEEDBACK]"):
                    content = content.replace("[FEEDBACK]", "").strip()
                    # 解析客户ID和反馈文本
                    customer_id = ""
                    if ":" in content:
                        parts = content.split(":", 1)
                        customer_id = parts[0].strip()
                        content = parts[1].strip()

                    # ── 意图识别 ──
                    if content.startswith("?"):
                        # 查询意图 → @mention knowledge-agent
                        keyword = content[1:].strip()
                        print(f"  → Intent: QUERY → @knowledge-agent")
                        query_msg = f"[QUERY] {keyword}"
                        await tools.send_message(
                            content=query_msg,
                            mentions=["@jacky231609/knowledge-agent"],
                        )
                        return

                    # 反馈意图 → 诊断 → @mention engineering-agent
                    print(f"  → Intent: FEEDBACK → diagnosing...")
                    product_model = ""
                    # 尝试从内容中提取产品型号
                    for model in ["9100", "8200", "X1"]:
                        if model in content:
                            product_model = model
                            break

                    decision = self._routing_agent.process_feedback(
                        feedback_text=content,
                        customer_id=customer_id,
                        product_model=product_model,
                    )

                    if decision:
                        # 通过Band @mention engineering-agent
                        routing_msg = self._routing_agent._format_routing_message(decision)
                        # 补充feedback_text到消息中
                        routing_msg += f"\n\nfeedback_text: {content}"
                        routing_msg += f"\ncustomer_id: {customer_id}"

                        target = "@jacky231609/engineering-agent"
                        print(f"  → Routing to: {target}")
                        await tools.send_message(
                            content=routing_msg,
                            mentions=[target],
                        )
                    else:
                        print(f"  ⚠️ Routing decision is empty")

        # 创建适配器实例
        adapter = RoutingAdapter()
        adapter._routing_agent = self.routing_agent

        # 创建并启动 Band Agent
        self._agent = Agent.create(
            adapter=adapter,
            agent_id=self.agent_id,
            api_key=self.api_key,
        )

        print(f"[{t('log.band_started')}]")
        print(f"{t('log.band_agent_id', id=self.agent_id)}")
        await self._agent.run()


# ── 入口 ──────────────────────────────────────────────

def main():
    """命令行入口：启动真实 Band Agent。"""
    import asyncio

    agent_id = os.environ.get("BAND_ROUTING_AGENT_ID", os.environ.get("BAND_AGENT_ID", ""))
    api_key = os.environ.get("BAND_ROUTING_API_KEY", os.environ.get("BAND_API_KEY", ""))

    if not agent_id or not api_key:
        print(t('env.set_band_id'))
        print(t('env.export_hint1'))
        print(t('env.export_hint2'))
        sys.exit(1)

    adapter = BandRoomAdapter(agent_id=agent_id, api_key=api_key)
    asyncio.run(adapter.start())


if __name__ == "__main__":
    main()
