#!/usr/bin/env python3
"""
run.py — harness 入口

用法:
  python harness/run.py --scenario happy_path
  python harness/run.py --scenario no_match_fallback
  python harness/run.py --scenario regression_bug_route
  python harness/run.py --all
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import os

# 确保项目根目录在 path 中
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# 确保用 Python 3.12（band-sdk 需要）
_PYTHON_MIN = (3, 10)
if sys.version_info < _PYTHON_MIN:
    print(f"⚠️ Python {_PYTHON_MIN[0]}.{_PYTHON_MIN[1]}+ required, got {sys.version_info[0]}.{sys.version_info[1]}")
    # 不退出，尝试继续


SCENARIOS = {
    "happy_path": "harness.scenarios.happy_path",
    "no_match_fallback": "harness.scenarios.no_match_fallback",
    "regression_bug_route": "harness.scenarios.regression_bug_route",
}


async def run_scenario(name: str) -> bool:
    """导入并运行一个场景，返回是否通过。"""
    module_path = SCENARIOS.get(name)
    if not module_path:
        print(f"❌ Unknown scenario: {name}")
        print(f"   Available: {', '.join(SCENARIOS.keys())}")
        return False

    # 动态导入
    import importlib
    module = importlib.import_module(module_path)
    return await module.run()


async def main():
    parser = argparse.ArgumentParser(description="Band Routing Harness — Test Runner")
    parser.add_argument("--scenario", "-s", type=str, help="场景名称")
    parser.add_argument("--all", "-a", action="store_true", help="运行所有场景")
    args = parser.parse_args()

    if args.all:
        results = {}
        for name in SCENARIOS:
            print(f"\n{'='*60}")
            print(f"  Running: {name}")
            print(f"{'='*60}")
            try:
                results[name] = await run_scenario(name)
            except Exception as e:
                print(f"❌ EXCEPTION in {name}: {e}")
                import traceback
                traceback.print_exc()
                results[name] = False

        print(f"\n{'='*60}")
        print("  SUMMARY")
        print(f"{'='*60}")
        for name, passed in results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"  {status} — {name}")
        all_passed = all(results.values())
        print(f"\n  Overall: {'✅ ALL PASS' if all_passed else '❌ SOME FAILED'}")
        sys.exit(0 if all_passed else 1)

    elif args.scenario:
        passed = await run_scenario(args.scenario)
        sys.exit(0 if passed else 1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
