#!/usr/bin/env python3
"""
verify_real_feishu.py — 真实飞书环境验证（支持 i18n）

不使用 mock，直接调用真实 Bitable API 查历史 + 真实飞书 API 发卡片。

用法:
  python verify_real_feishu.py "搜索功能最近结果不准"
  python verify_real_feishu.py "9100 robot responds slowly" "Liming Intl" "9100" --lang en
  python verify_real_feishu.py "9100机器人响应慢" "黎明国际" "9100" --lang zh
"""
import sys
import os
import asyncio
import argparse

# 解析 --lang 参数（必须在 import routing_agent 之前设置 LANG）
_parser = argparse.ArgumentParser()
_parser.add_argument("feedback", nargs="?", default="搜索功能最近结果不准")
_parser.add_argument("customer", nargs="?", default="测试客户")
_parser.add_argument("product", nargs="?", default="")
_parser.add_argument("--lang", "-l", default="zh", choices=["zh", "en"])
_args, _unknown = _parser.parse_known_args()

# 设置语言环境变量
os.environ["LANG"] = _args.lang

# 加载飞书环境
_pipeline_dir = os.path.join(os.path.dirname(__file__), "ai-requirement-pipeline", "pipeline")
_pipeline_dir = os.path.abspath(_pipeline_dir)
_env_name = os.environ.get("FEISHU_ENV", "team-testing")
_env_file = os.path.join(_pipeline_dir, f".env.{_env_name}")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
    print(f"[verify] Env: {_env_name}, Lang: {_args.lang}")

# 确保 band-routing 在 path
_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_root, "band-routing"))
sys.path.insert(0, os.path.join(_root, "band-routing", "tools"))

from routing_agent import RoutingAgent
from i18n import t, get_lang


async def main():
    feedback = _args.feedback
    customer_id = _args.customer
    product_model = _args.product

    print(f"\n{'='*60}")
    print(f"  {'Real Feishu Verification' if get_lang() == 'en' else '真实飞书环境验证'}")
    print(f"  {'Feedback' if get_lang() == 'en' else '反馈'}: {feedback}")
    print(f"  {'Customer' if get_lang() == 'en' else '客户'}: {customer_id}")
    if product_model:
        print(f"  {'Product' if get_lang() == 'en' else '产品型号'}: {product_model}")
    print(f"  Lang: {get_lang()}")
    print(f"{'='*60}")

    # 创建 routing-agent，不注入任何 mock → 用真实实现
    agent = RoutingAgent()

    # 真实调用：查 Bitable + AI 诊断 + 发飞书卡片
    decision = agent.process_feedback(
        feedback_text=feedback,
        customer_id=customer_id,
        product_model=product_model,
    )

    print(f"\n{'='*60}")
    print(f"  {'Routing Decision' if get_lang() == 'en' else '路由决策结果'}:")
    print(f"{'='*60}")
    import json
    print(json.dumps(decision, ensure_ascii=False, indent=2))

    if decision and decision.get("target_agent"):
        print(f"\n✅ {'Verification complete — check Feishu for card' if get_lang() == 'en' else '验证完成 — 请检查飞书是否收到卡片'}")
    else:
        print(f"\n❌ {'Routing decision is empty' if get_lang() == 'en' else '路由决策为空'}")


if __name__ == "__main__":
    asyncio.run(main())
