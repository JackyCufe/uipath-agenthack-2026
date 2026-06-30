"""
i18n.py — 统一文本映射层

纯数据 + t(key) 查找函数，无业务逻辑。
通过 LANG 环境变量切换中英文（默认 zh）。

用法:
    from i18n import t
    print(t("card.title"))          # LANG=zh → "客户反馈路由通知"
                                    # LANG=en → "Customer Feedback Routing Notice"
    print(t("field.requirement_id")) # LANG=zh → "需求ID"
                                     # LANG=en → "requirement_id"
"""
from __future__ import annotations

import os

_LANG = os.environ.get("LANG", "zh").lower()
if _LANG not in ("zh", "en"):
    _LANG = "zh"

# ── 文本映射 ──────────────────────────────────────────

_TEXTS: dict[str, dict[str, str]] = {
    # 卡片标题
    "card.routing_title": {"zh": "客户反馈路由通知", "en": "Customer Feedback Routing Notice"},
    "card.confirm_title": {"zh": "反馈确认", "en": "Feedback Confirmation"},
    "card.transfer_title": {"zh": "转交他人", "en": "Transfer to Colleague"},
    "card.resolved_title": {"zh": "反馈已处理", "en": "Feedback Resolved"},
    "card.edit_title": {"zh": "修改反馈", "en": "Edit Feedback"},
    "card.escalated_title": {"zh": "已升级", "en": "Escalated"},
    "card.transferred_title": {"zh": "已转交", "en": "Transferred"},

    # 卡片区块标题
    "card.feedback_original": {"zh": "客户反馈原文", "en": "Customer Feedback (Original)"},
    "card.routing_reason": {"zh": "路由原因", "en": "Routing Reason"},
    "card.context_summary": {"zh": "上下文摘要", "en": "Context Summary"},
    "card.confirm_prompt": {"zh": "您的反馈已收到，请确认以下信息", "en": "Your feedback has been received. Please confirm the following"},
    "card.ai_summary": {"zh": "AI 理解摘要", "en": "AI Summary"},
    "card.transfer_prompt": {"zh": "请输入转交对象的飞书姓名", "en": "Enter the Feishu/Lark name of the person to transfer to"},
    "card.resolved_prompt": {"zh": "您的反馈已处理完成", "en": "Your feedback has been resolved"},
    "card.thank_you": {"zh": "感谢您的反馈！如有其他问题请随时联系我们。", "en": "Thank you for your feedback! Feel free to reach out if you have other questions."},

    # 卡片字段标签
    "label.customer": {"zh": "客户", "en": "Customer"},
    "label.diagnosis_type": {"zh": "诊断类型", "en": "Diagnosis Type"},
    "label.matched_requirement": {"zh": "匹配需求", "en": "Matched Requirement"},
    "label.entry_stage": {"zh": "切入阶段", "en": "Entry Stage"},
    "label.severity": {"zh": "严重程度", "en": "Severity"},
    "label.product_model": {"zh": "产品型号", "en": "Product Model"},
    "label.feedback_text": {"zh": "反馈原文", "en": "Feedback"},
    "label.resolved_by": {"zh": "处理人", "en": "Resolved By"},
    "label.resolution_note": {"zh": "处理说明", "en": "Resolution Note"},
    "label.related_requirement": {"zh": "关联需求", "en": "Related Requirement"},
    "label.original_requirement": {"zh": "原需求", "en": "Original Requirement"},

    # 诊断类型标签
    "diagnosis.tech_bug": {"zh": "技术Bug（回归）", "en": "Tech Bug (Regression)"},
    "diagnosis.service_issue": {"zh": "服务/运营问题", "en": "Service / Operations Issue"},
    "diagnosis.new_requirement": {"zh": "全新需求", "en": "New Requirement"},
    "diagnosis.complaint": {"zh": "售后投诉", "en": "Post-Sales Complaint"},
    "diagnosis.transferred": {"zh": "转交处理", "en": "Transferred"},
    "diagnosis.unknown": {"zh": "未知类型", "en": "Unknown"},

    # 无匹配占位
    "placeholder.no_match": {"zh": "无（全新需求）", "en": "None (New Requirement)"},
    "placeholder.empty": {"zh": "（无）", "en": "(None)"},
    "placeholder.dash": {"zh": "—", "en": "—"},

    # 按钮
    "btn.resolved": {"zh": "✅ 已处理", "en": "✅ Resolved"},
    "btn.escalate": {"zh": "🔄 需走完整流程", "en": "🔄 Escalate to Full Pipeline"},
    "btn.transfer": {"zh": "↗️ 转交他人", "en": "↗️ Transfer"},
    "btn.confirm": {"zh": "✅ 确认提交", "en": "✅ Confirm & Submit"},
    "btn.edit": {"zh": "✏️ 补充修改", "en": "✏️ Edit"},
    "btn.search_transfer": {"zh": "🔍 搜索并转交", "en": "🔍 Search & Transfer"},

    # 处理人提示
    "prompt.handle": {"zh": "请 {role} 处理", "en": "Please handle, {role}"},

    # 角色名
    "role.presales": {"zh": "售前", "en": "Pre-sales"},
    "role.pm": {"zh": "产品经理", "en": "Product Manager"},
    "role.rd": {"zh": "研发负责人", "en": "Engineering Lead"},
    "role.product_owner": {"zh": "产品负责人", "en": "Product Owner"},
    "role.after_sales": {"zh": "售后", "en": "After-sales"},
    "role.all": {"zh": "全员", "en": "All Members"},
    "role.default": {"zh": "负责人", "en": "Owner"},

    # Bitable 字段名
    "field.requirement_id": {"zh": "需求ID", "en": "requirement_id"},
    "field.requirement_title": {"zh": "需求标题", "en": "requirement_title"},
    "field.customer_name": {"zh": "客户名称", "en": "customer_name"},
    "field.product_model": {"zh": "产品型号", "en": "product_model"},
    "field.current_stage": {"zh": "当前阶段", "en": "current_stage"},
    "field.current_owner": {"zh": "当前负责人", "en": "current_owner"},
    "field.s1_owner": {"zh": "S1_负责人", "en": "S1_owner"},
    "field.s2_owner": {"zh": "S2_负责人", "en": "S2_owner"},
    "field.s3_owner": {"zh": "S3_负责人", "en": "S3_owner"},
    "field.s4_owner": {"zh": "S4_负责人", "en": "S4_owner"},
    "field.s5_owner": {"zh": "S5_负责人", "en": "S5_owner"},
    "field.s6_owner": {"zh": "S6_负责人", "en": "S6_owner"},

    # 回调响应文本
    "callback.resolved_msg": {"zh": "已标记为已处理", "en": "Marked as resolved"},
    "callback.customer_notified": {"zh": "客户已收到处理通知", "en": "Customer has been notified"},
    "callback.escalated_msg": {"zh": "该反馈已升级为完整需求流程", "en": "This feedback has been escalated to the full requirement pipeline"},
    "callback.presales_notified": {"zh": "售前将收到通知，启动 S1 守门流程", "en": "Pre-sales will be notified to start the S1 gatekeeping process"},
    "callback.transfer_card_sent": {"zh": "转交卡片已发送", "en": "Transfer card has been sent"},
    "callback.transferred_to": {"zh": "已转交给 {name}", "en": "Transferred to {name}"},
    "callback.transfer_failed": {"zh": "转交失败: {error}", "en": "Transfer failed: {error}"},
    "callback.user_not_found": {"zh": "未找到飞书用户: {name}", "en": "Feishu/Lark user not found: {name}"},
    "callback.enter_name": {"zh": "请输入转交对象姓名", "en": "Please enter the name of the person to transfer to"},
    "callback.routed": {"zh": "路由已触发", "en": "Routing triggered"},
    "callback.routing_failed": {"zh": "路由失败", "en": "Routing failed"},
    "callback.edit_card_sent": {"zh": "编辑卡片已发送", "en": "Edit card has been sent"},
    "callback.feedback_content": {"zh": "反馈内容", "en": "Feedback content"},
    "callback.bitable_updated": {"zh": "Bitable 已更新: {req_id} → {status}", "en": "Bitable updated: {req_id} → {status}"},
    "callback.bitable_not_found": {"zh": "Bitable 中未找到 {req_id}", "en": "{req_id} not found in Bitable"},
    "callback.bitable_update_failed": {"zh": "Bitable 更新失败: {msg}", "en": "Bitable update failed: {msg}"},
    "callback.default_resolver": {"zh": "处理人", "en": "Resolver"},
    "callback.resolution_note": {"zh": "问题已修复，请验证。", "en": "Issue has been fixed. Please verify."},
    "callback.feedback_processed": {"zh": "反馈已处理-{status}", "en": "Feedback processed-{status}"},

    # 日志
    "log.loading_env": {"zh": "加载环境: {name}", "en": "Loading environment: {name}"},
    "log.processing_feedback": {"zh": "处理客户反馈", "en": "Processing customer feedback"},
    "log.sending_confirm_card": {"zh": "发送客户确认卡片", "en": "Sending customer confirmation card"},
    "log.searching_bitable": {"zh": "搜索 Bitable 历史需求", "en": "Searching Bitable history"},
    "log.found_matches": {"zh": "找到 {count} 条匹配记录", "en": "Found {count} matching records"},
    "log.no_match": {"zh": "无匹配历史需求", "en": "No matching history"},
    "log.best_match": {"zh": "最佳匹配: {req_id} — {title}", "en": "Best match: {req_id} — {title}"},
    "log.fetching_chain": {"zh": "拉取 {req_id} 完整链路", "en": "Fetching full chain for {req_id}"},
    "log.chain_success": {"zh": "完整链路获取成功，阶段数据: {stages}", "en": "Full chain fetched, stages: {stages}"},
    "log.chain_failed": {"zh": "⚠️ 完整链路获取失败，使用搜索结果", "en": "⚠️ Full chain fetch failed, using search result"},
    "log.ai_diagnosing": {"zh": "AI 诊断问题类型", "en": "AI diagnosing issue type"},
    "log.diagnosis_result": {"zh": "诊断类型: {type}", "en": "Diagnosis type: {type}"},
    "log.severity_result": {"zh": "严重程度: {severity}", "en": "Severity: {severity}"},
    "log.routing_decision": {"zh": "路由决策", "en": "Routing decision"},
    "log.entry_stage": {"zh": "切入阶段: S{stage}", "en": "Entry stage: S{stage}"},
    "log.target_agent": {"zh": "目标 Agent: {agent}", "en": "Target agent: {agent}"},
    "log.matched_req": {"zh": "匹配需求: {req_id}", "en": "Matched requirement: {req_id}"},
    "log.sending_band_msg": {"zh": "发送 Band Room 消息", "en": "Sending Band Room message"},
    "log.mention": {"zh": "@mention {agent}", "en": "@mention {agent}"},
    "log.sending_lark_card": {"zh": "发送飞书卡片通知", "en": "Sending Feishu/Lark card notification"},
    "log.owner": {"zh": "负责人: {name}", "en": "Owner: {name}"},
    "log.card_sent_ok": {"zh": "卡片发送成功", "en": "Card sent successfully"},
    "log.card_sent_fail": {"zh": "⚠️ 卡片发送失败: {error}", "en": "⚠️ Card send failed: {error}"},
    "log.writing_trace": {"zh": "写入 feedback_trace", "en": "Writing feedback_trace"},
    "log.trace_written": {"zh": "feedback_trace 已写入", "en": "feedback_trace written"},
    "log.routing_complete": {"zh": "路由完成 ✅", "en": "Routing complete ✅"},
    "log.owner_extracted": {"zh": "从历史记录提取负责人: {name} ({oid})", "en": "Owner extracted from history: {name} ({oid})"},
    "log.summary_failed": {"zh": "⚠️ 摘要生成失败: {error}", "en": "⚠️ Summary generation failed: {error}"},
    "log.confirm_card_sent": {"zh": "确认卡片已发送给客户", "en": "Confirmation card sent to customer"},
    "log.confirm_card_failed": {"zh": "⚠️ 确认卡片发送失败: {error}", "en": "⚠️ Confirmation card send failed: {error}"},
    "log.filtering_model": {"zh": "按产品型号筛选: {model}", "en": "Filtering by product model: {model}"},
    "log.token_unconfigured": {"zh": "⚠️ BITABLE_APP_TOKEN 未配置", "en": "⚠️ BITABLE_APP_TOKEN not configured"},
    "log.search_failed": {"zh": "❌ 搜索失败: {msg}", "en": "❌ Search failed: {msg}"},
    "log.chain_query_failed": {"zh": "❌ 查询失败: {msg}", "en": "❌ Query failed: {msg}"},
    "log.no_open_id": {"zh": "⚠️ 无法找到 Stage {stage} 负责人 open_id", "en": "⚠️ Cannot find open_id for Stage {stage} owner"},
    "log.card_send_fail_msg": {"zh": "❌ 发送失败: {msg}", "en": "❌ Send failed: {msg}"},
    "log.card_sent_to": {"zh": "卡片已发送给 {role} (open_id={oid})", "en": "Card sent to {role} (open_id={oid})"},
    "log.card_sent_generic": {"zh": "卡片已发送 (open_id={oid})", "en": "Card sent (open_id={oid})"},

    # Band Room 日志
    "log.band_send_msg": {"zh": "发送消息: {content}", "en": "Send message: {content}"},
    "log.band_msg_received": {"zh": "收到消息 from {sender}: {content}", "en": "Message received from {sender}: {content}"},
    "log.band_not_installed": {"zh": "⚠️ band-sdk 未安装，无法启动真实 Band Agent", "en": "⚠️ band-sdk not installed, cannot start real Band Agent"},
    "log.band_install_hint": {"zh": "请安装: pip install band-sdk", "en": "Please install: pip install band-sdk"},
    "log.band_started": {"zh": "Agent 启动，监听 @routing-agent", "en": "Agent started, listening for @routing-agent"},
    "log.band_agent_id": {"zh": "Agent ID: {id}", "en": "Agent ID: {id}"},

    # 环境提示
    "env.set_band_id": {"zh": "⚠️ 请设置 BAND_AGENT_ID 和 BAND_API_KEY 环境变量", "en": "⚠️ Please set BAND_AGENT_ID and BAND_API_KEY environment variables"},
    "env.export_hint1": {"zh": "  export BAND_AGENT_ID=your-agent-uuid", "en": "  export BAND_AGENT_ID=your-agent-uuid"},
    "env.export_hint2": {"zh": "  export BAND_API_KEY=your-api-key", "en": "  export BAND_API_KEY=your-api-key"},

    # 输入框占位
    "placeholder.transfer_name": {"zh": "例如：吕嘉琪", "en": "e.g., John Smith"},

    # 转交卡片
    "card.transfer_original_req": {"zh": "原需求：{req_id}", "en": "Original requirement: {req_id}"},
    "card.transfer_original_feedback": {"zh": "反馈原文：{text}", "en": "Original feedback: {text}"},

    # 回调状态卡片
    "card.resolved_by_marked": {"zh": "{name} 已标记为已处理", "en": "{name} marked as resolved"},
    "card.req_label": {"zh": "需求：{req_id}", "en": "Requirement: {req_id}"},
    "card.escalated_msg": {"zh": "该反馈已升级为完整需求流程", "en": "This feedback has been escalated to the full requirement pipeline"},
    "card.presales_will_start": {"zh": "售前将收到通知，启动 S1 守门流程", "en": "Pre-sales will be notified to start the S1 gatekeeping process"},
    "card.edit_prompt": {"zh": "请修改您的反馈信息", "en": "Please edit your feedback"},
}


def t(key: str, **kwargs) -> str:
    """
    查找文本。

    Args:
        key: 文本 key，如 "card.title"
        **kwargs: 模板变量，如 t("log.found_matches", count=5)

    Returns:
        当前语言的文本。如果 key 不存在，返回 key 本身。
    """
    entry = _TEXTS.get(key)
    if entry is None:
        return key

    text = entry.get(_LANG, entry.get("zh", key))

    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass

    return text


def get_lang() -> str:
    """返回当前语言。"""
    return _LANG
