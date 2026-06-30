from __future__ import annotations
import json
import os
import sys
from pathlib import Path

# -- LLM Client：根据 LLM_PROVIDER 选择 Anthropic 或 DeepSeek(OpenAI) --
from openai import OpenAI

# 延迟导入 anthropic，避免未安装时崩溃
_anthropic_available = False
try:
    import anthropic
    _anthropic_available = True
except ImportError:
    pass

_PARENT = Path(__file__).resolve().parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

from config import (
    LLM_PROVIDER, MODEL,
    LITELLM_BASE_URL, LITELLM_API_KEY,
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    AGENTS_DIR,
)
from tools import TOOL_DEFINITIONS, TOOL_DISPATCH

# -- 客户端工厂 ----------------------------------------------------------------

_client = None  # type: ignore
_client_type = ""  # "anthropic" | "openai"

if LLM_PROVIDER == "deepseek" and DEEPSEEK_API_KEY:
    _client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    _client_type = "openai"
    print(f"[agent_runner] LLM: DeepSeek ({DEEPSEEK_MODEL}) @ {DEEPSEEK_BASE_URL}")
elif _anthropic_available:
    _client = anthropic.Anthropic(api_key=LITELLM_API_KEY, base_url=LITELLM_BASE_URL)
    _client_type = "anthropic"
    print(f"[agent_runner] LLM: Anthropic via LiteLLM ({MODEL})")
else:
    print("[agent_runner] ⚠️ 无可用 LLM 客户端（设置 DEEPSEEK_API_KEY 或安装 anthropic）")

# ── 工具白名单：按 Agent 过滤，防止跨角色误调用 ──────────
# 01 守门：只需要 submit_gatekeeping_result
# 02 价值转化 + 06 复盘：纯 text 输出，禁止所有工具
# 03/04/05：需要飞书消息 + 多维表格写入能力
_COMMON_TOOLS = {"resolve_feishu_user_id", "send_feishu_message", "write_bitable_record"}
_AGENT_TOOL_WHITELIST: dict[str, set[str]] = {
    "01-gatekeeper.md":       {"submit_gatekeeping_result"},
    "02-value-transform.md":  set(),
    "03-scenario-test.md":    _COMMON_TOOLS,
    "04-release-review.md":   _COMMON_TOOLS,
    "05-feedback-collect.md": set(),          # demo.py 模式：纯 text 输出，Pipeline 自行写入
    "06-retrospective.md":    set(),
}


def _get_tools_for_agent(agent_file: str) -> list[dict]:
    """根据 Agent 文件名返回该 Agent 可用的工具定义列表。"""
    allowed = _AGENT_TOOL_WHITELIST.get(agent_file)
    if allowed is None:
        # 未知 Agent：返回全部工具（向后兼容）
        return TOOL_DEFINITIONS
    return [t for t in TOOL_DEFINITIONS if t["name"] in allowed]


def _load_system_prompt(agent_file: str) -> str:
    path = Path(AGENTS_DIR) / agent_file
    text = path.read_text(encoding="utf-8")
    # Strip YAML frontmatter
    if text.startswith("---"):
        end = text.index("---", 3)
        text = text[end + 3:].strip()
    return text


# ── 各 Agent 差异化 max_tokens ────────────────────────────
# 按实际输出需求设置，避免简单任务浪费输出配额
_AGENT_MAX_TOKENS: dict[str, int] = {
    "01-gatekeeper.md":       1500,   # 判断题：通过/拒绝/追问，输出短
    "02-value-transform.md": 8192,   # 需要完整 JSON（含多轮分析文本），提高上限防截断
    "03-scenario-test.md":   4096,   # 中等：测试用例生成
    "04-release-review.md":  2048,   # 中等：发版审批结论
    "05-feedback-collect.md":2048,   # 中等：反馈分析
    "06-retrospective.md":   6000,   # 最长：复盘报告需详细文本
}
_DEFAULT_MAX_TOKENS = 4096  # 降低全局默认值（原来 8192）


def run_agent(agent_file: str, user_message: str, extra_context: dict | None = None) -> dict:
    """Run agent — delegates to provider-specific implementation."""
    if _client_type == "openai":
        return _run_openai(agent_file, user_message, extra_context)
    return _run_anthropic(agent_file, user_message, extra_context)


def _run_anthropic(agent_file: str, user_message: str, extra_context: dict | None = None) -> dict:
    """Anthropic (Claude) tool_use loop."""
    if _client is None:
        return {"text": "[无LLM客户端]", "tool_calls": []}

    system_prompt = _load_system_prompt(agent_file)
    if extra_context:
        context_block = "\n\n<pipeline_context>\n" + json.dumps(extra_context, ensure_ascii=False, indent=2) + "\n</pipeline_context>"
        system_prompt = system_prompt + context_block

    messages = [{"role": "user", "content": user_message}]
    tool_log = []
    accumulated_text = ""
    max_tokens = _AGENT_MAX_TOKENS.get(agent_file, _DEFAULT_MAX_TOKENS)
    agent_tools = _get_tools_for_agent(agent_file)

    print(f"\n{'='*60}")
    print(f"  Agent: {agent_file} (Anthropic, max_tokens={max_tokens})")
    print(f"{'='*60}")

    max_tool_rounds = 5  # 防止无限工具循环
    tool_round = 0

    while True:
        if tool_round >= max_tool_rounds:
            print(f"  [agent] 达到最大工具循环次数 {max_tool_rounds}，终止")
            return {"text": accumulated_text, "tool_calls": tool_log}
        response = _client.messages.create(
            model=MODEL, max_tokens=max_tokens,
            system=system_prompt, tools=agent_tools,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            text = accumulated_text
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text
            return {"text": text, "tool_calls": tool_log}

        if response.stop_reason == "tool_use":
            tool_round += 1
            tool_results = []
            for block in response.content:
                if hasattr(block, "text"):
                    accumulated_text += block.text
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    print(f"  → tool_use: {tool_name}({json.dumps(tool_input, ensure_ascii=False)[:120]})")
                    handler = TOOL_DISPATCH.get(tool_name)
                    result = handler(tool_input) if handler else {"error": f"unknown: {tool_name}"}
                    tool_log.append({"tool": tool_name, "input": tool_input, "result": result})
                    tool_results.append({
                        "type": "tool_result", "tool_use_id": block.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            text = accumulated_text
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text
            return {"text": text, "tool_calls": tool_log}


def _run_openai(agent_file: str, user_message: str, extra_context: dict | None = None) -> dict:
    """DeepSeek/OpenAI-compatible tool_use loop."""
    if _client is None:
        return {"text": "[无LLM客户端]", "tool_calls": []}

    system_prompt = _load_system_prompt(agent_file)
    if extra_context:
        context_block = "\n\n<pipeline_context>\n" + json.dumps(extra_context, ensure_ascii=False, indent=2) + "\n</pipeline_context>"
        system_prompt = system_prompt + context_block

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    tool_log = []
    accumulated_text = ""
    max_tokens = _AGENT_MAX_TOKENS.get(agent_file, _DEFAULT_MAX_TOKENS)
    agent_tools_anthropic = _get_tools_for_agent(agent_file)
    agent_tools = _convert_tools_to_openai(agent_tools_anthropic)

    print(f"\n{'='*60}")
    print(f"  Agent: {agent_file} (DeepSeek, max_tokens={max_tokens})")
    print(f"{'='*60}")

    max_tool_rounds = 5
    tool_round = 0

    while True:
        if tool_round >= max_tool_rounds:
            print(f"  [agent] 达到最大工具循环次数 {max_tool_rounds}，终止")
            return {"text": accumulated_text, "tool_calls": tool_log}
        kwargs = {"model": MODEL, "max_tokens": max_tokens, "messages": messages}
        if agent_tools:
            kwargs["tools"] = agent_tools

        response = _client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        finish = response.choices[0].finish_reason

        if msg.content:
            accumulated_text += msg.content

        if finish == "stop" or (finish != "tool_calls" and not msg.tool_calls):
            return {"text": accumulated_text, "tool_calls": tool_log}

        if finish == "tool_calls" and msg.tool_calls:
            tool_round += 1
            tool_results = []
            messages.append({"role": "assistant", "content": msg.content, "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]})

            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_input = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_input = {"raw": tc.function.arguments}
                print(f"  → tool_call: {tool_name}({json.dumps(tool_input, ensure_ascii=False)[:120]})")
                handler = TOOL_DISPATCH.get(tool_name)
                result = handler(tool_input) if handler else {"error": f"unknown: {tool_name}"}
                tool_log.append({"tool": tool_name, "input": tool_input, "result": result})
                tool_results.append({
                    "role": "tool", "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

            messages.extend(tool_results)
        else:
            return {"text": accumulated_text, "tool_calls": tool_log}


def _convert_tools_to_openai(anthropic_tools: list[dict]) -> list[dict]:
    """Anthropic tool format → OpenAI tool format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in anthropic_tools
    ] if anthropic_tools else []


def _repair_json_text(text: str) -> str:
    """修复 AI 输出的 JSON 文本中的常见问题。

    处理（按优先级）：
    1. 字符串值内未转义的双引号（如中文引号 "你好"） → \\"
    2. 字符串值内裸反斜杠（如 C:\\test） → \\\\
    3. 字符串值内真实换行/制表 → \\n \\t
    4. 其他控制字符 → \\uXXXX
    """
    chars = list(text)
    i = 0
    n = len(chars)
    result = []
    in_string = False
    escape_next = False

    def _next_non_space(start: int) -> str:
        """从 start 开始跳过空白，返回下一个有效字符；越界返回 ''"""
        k = start
        while k < n and chars[k] in (" ", "\t", "\n", "\r"):
            k += 1
        return chars[k] if k < n else ""

    while i < n:
        ch = chars[i]

        if escape_next:
            result.append(ch)
            escape_next = False
            i += 1
            continue

        if ch == "\\":
            result.append(ch)
            escape_next = True
            i += 1
            continue

        if ch == '"':
            if not in_string:
                # 进入字符串
                in_string = True
                result.append(ch)
                i += 1
                continue
            else:
                # 在字符串内遇到 '"'：判断是结构结束还是内容引号
                nxt = _next_non_space(i + 1)
                if nxt in (",", ":", "]", "}", ""):
                    # 字符串结束
                    in_string = False
                    result.append(ch)
                else:
                    # 内容中的引号 → 转义
                    result.append("\\\"")
                i += 1
                continue

        if in_string:
            if ch == "\n":
                result.append("\\n")
            elif ch == "\r":
                result.append("\\r")
            elif ch == "\t":
                result.append("\\t")
            elif ord(ch) < 32:
                result.append(f"\\u{ord(ch):04x}")
            else:
                result.append(ch)
            i += 1
            continue

        # 不在字符串内：原样输出
        result.append(ch)
        i += 1

    return "".join(result)


def _extract_all_json_objects(text: str) -> list[dict]:
    """Extract all top-level JSON objects from text, stripping markdown code fences first."""
    import re
    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = cleaned.replace("```", "")

    results = []
    i = 0
    while i < len(cleaned):
        if cleaned[i] != "{":
            i += 1
            continue
        depth = 0
        for j in range(i, len(cleaned)):
            if cleaned[j] == "{":
                depth += 1
            elif cleaned[j] == "}":
                depth -= 1
                if depth == 0:
                    candidate = cleaned[i:j+1]
                    try:
                        repaired = _repair_json_text(candidate)
                        obj = json.loads(repaired)
                        if isinstance(obj, dict):
                            results.append(obj)
                    except json.JSONDecodeError as _je:
                        print(f"  [_extract_all] ⚠️ JSON解析失败 pos={_je.pos}: {_je.msg} | len={len(candidate)}")
                        pass
                    i = j + 1
                    break
        else:
            break
    return results


def extract_json_from_response(text: str) -> dict | None:
    """Extract the Schema 1 JSON object from agent response text.

    Preference order:
    1. Any JSON object containing 'schema_version' key (the canonical Schema JSON)
    2. First JSON object found (fallback)

    Handles markdown code fences and explanation text before/after JSON.
    """
    candidates = _extract_all_json_objects(text)
    if not candidates:
        return None
    # Prefer the object that looks like a Schema JSON
    for obj in candidates:
        if "schema_version" in obj:
            return obj
    # Fallback: return first object found
    return candidates[0]


def extract_gatekeeping_result(tool_calls: list) -> dict | None:
    """Extract the atomic fields from submit_gatekeeping_result tool call.

    Returns the raw input dict (verdict, customer_who, ...) for schema_builder.build_schema1().
    Pipeline calls this instead of parsing Schema JSON from text.
    """
    for call in tool_calls:
        if call.get("tool") == "submit_gatekeeping_result":
            inp = call.get("input", {})
            if isinstance(inp, dict) and "verdict" in inp:
                return inp
    return None


def _coerce_list(val) -> list:
    """Coerce a value to list. Handles JSON string / Python repr string from Agent."""
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        import ast as _ast
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            parsed = _ast.literal_eval(val)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
    return []


def extract_value_transform_result(tool_calls: list, text: str = "") -> dict | None:
    """从 Agent 02 的 text 输出中提取 Schema 2 JSON。

    优先顺序：
    1. 尝试解析 text 中的 ```json 代码块
    2. 若失败，回退到 extract_json_from_response(text) 的通用 JSON 提取
    3. 最后再看 tool_calls 里的 submit_value_transform_result
    """
    import re as _re

    # ── 优先：从 text 提取 ```json 块 ──
    if text:
        blocks = _re.findall(r'```json\s*([\s\S]*?)\s*```', text)
        if not blocks:
            blocks = [text]  # 无 fenced block，整段当 JSON
        for block in blocks:
            raw = block.strip()
            repaired = _repair_json_text(raw)
            try:
                parsed = json.loads(repaired)
                if isinstance(parsed, dict) and ("structured_criteria" in parsed or "test_cases" in parsed):
                    print(f"  [extract_value_transform] ✅ 从 text JSON 块提取成功")
                    return {
                        **parsed,
                        "structured_criteria": _coerce_list(parsed.get("structured_criteria", [])),
                        "test_cases": _coerce_list(parsed.get("test_cases", [])),
                    }
            except json.JSONDecodeError as _je:
                pos = _je.pos
                snippet = repaired[max(0, pos - 50):pos + 50]
                print(f"  [extract_value_transform] ⚠️ JSON解析失败 pos={pos}: {_je.msg}")
                print(f"    错误上下文: ...{repr(snippet)}...")
            except Exception as _e:
                print(f"  [extract_value_transform] ⚠️ 异常: {type(_e).__name__}: {_e}")

        # ── 兜底：使用通用 JSON 提取器，兼容不规范 markdown fence / 说明文字 ──
        parsed = extract_json_from_response(text)
        if isinstance(parsed, dict) and ("structured_criteria" in parsed or "test_cases" in parsed):
            print(f"  [extract_value_transform] ✅ 从通用 JSON 提取器兜底成功")
            return {
                **parsed,
                "structured_criteria": _coerce_list(parsed.get("structured_criteria", [])),
                "test_cases": _coerce_list(parsed.get("test_cases", [])),
            }

        print(f"  [extract_value_transform] ⚠️ text 存在但未解析出 Schema2，text长度={len(text)}")

    # ── 降级：tool_calls 里的 submit_value_transform_result ──
    for call in tool_calls:
        if call.get("tool") == "submit_value_transform_result":
            inp = call.get("input", {})
            if isinstance(inp, dict) and "structured_criteria" in inp:
                print(f"  [extract_value_transform] ⚠️ 降级到 tool_calls 提取")
                return {
                    **inp,
                    "structured_criteria": _coerce_list(inp.get("structured_criteria", [])),
                    "test_cases": _coerce_list(inp.get("test_cases", [])),
                }

    print(f"  [extract_value_transform] ❌ 最终未提取到 Schema2")
    return None
def extract_json_from_tool_calls(tool_calls: list) -> dict | None:
    """Fallback: extract Schema JSON from tool_use blocks when text is empty.

    Prefer submit_gatekeeping_result / submit_value_transform_result (new path).
    Falls back to write_bitable_record record parsing (legacy path, kept for safety).

    Preference order:
    1. submit_gatekeeping_result / submit_value_transform_result input (new)
    2. write_bitable_record whose input contains 'record' with 'schema_version' (legacy)
    3. Any tool call whose input contains 'schema_version' directly
    """
    def _try_parse_record(record):
        """Parse record that may be a dict, a JSON string, or a Python repr string."""
        if isinstance(record, dict):
            return record
        if isinstance(record, str):
            import ast as _ast
            # Try standard JSON first
            try:
                parsed = json.loads(record)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
            # Fallback: Python repr format (single-quoted) — Agent sometimes emits this
            try:
                parsed = _ast.literal_eval(record)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        return None

    for call in tool_calls:
        if call.get("tool") == "write_bitable_record":
            record = _try_parse_record(call.get("input", {}).get("record", {}))
            if isinstance(record, dict) and "schema_version" in record:
                return record
    # Broader fallback: any tool input that looks like a schema
    for call in tool_calls:
        inp = call.get("input", {})
        if isinstance(inp, dict) and "schema_version" in inp:
            return inp
        record = _try_parse_record(inp.get("record", {}))
        if isinstance(record, dict) and "schema_version" in record:
            return record
    return None
