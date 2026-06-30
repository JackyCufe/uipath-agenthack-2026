"""
check_deps.py — PowerPoint Editor skill 依赖自检
用法：
    python check_deps.py            # 检测所有依赖，输出报告
    python check_deps.py --json     # JSON 格式输出（供 Agent 解析）
    python check_deps.py --install  # 自动安装缺失的必需依赖

依赖分级：
    必需（任务核心，缺失则对应功能不可用）：
        - python-pptx   读取 / 编辑 PPTX、inspect.py、template_fill.py
    可选（缺失不影响主流程，降级即可）：
        - matplotlib    preview.py 布局可视化
        - markitdown    PptxGenJS 工作流 QA 验证（python -m markitdown output.pptx）
"""

import sys
import io
import json
import argparse
import importlib.util
import subprocess

# ── 中文输出不乱码 ─────────────────────────────────────────────────
# Windows CMD 默认 GBK 终端下，即便 stdout 已是 TextIOWrapper，底层编码仍是 gbk，
# 输出非 GBK 字符会抛 UnicodeEncodeError。优先用 reconfigure() 强制切到 UTF-8；
# 旧 Python 无此方法时回退到 buffer 重包装。报告正文一律用 ASCII 标记，双保险。
def _force_utf8(stream):
    reconfig = getattr(stream, "reconfigure", None)
    if callable(reconfig):
        try:
            reconfig(encoding="utf-8", errors="replace")
            return stream
        except (ValueError, OSError):
            pass
    if hasattr(stream, "buffer"):
        return io.TextIOWrapper(stream.buffer, encoding="utf-8", errors="replace")
    return stream

sys.stdout = _force_utf8(sys.stdout)
sys.stderr = _force_utf8(sys.stderr)
# ──────────────────────────────────────────────────────────────────

# (import 名, pip 包名, 是否必需, 用途说明)
DEPS = [
    ("pptx", "python-pptx", True, "读取/编辑 PPTX、结构分析（inspect.py）、模板填充（template_fill.py）"),
    ("matplotlib", "matplotlib", False, "布局可视化（preview.py，可选）"),
    ("markitdown", "markitdown", False, "PptxGenJS 工作流 QA 验证（python -m markitdown output.pptx，可选）"),
]


def _is_installed(import_name: str) -> bool:
    try:
        return importlib.util.find_spec(import_name) is not None
    except (ImportError, ValueError):
        return False


def _check_node() -> dict:
    """检测 Node.js 是否安装，返回 {installed: bool, version: str|None}"""
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return {"installed": True, "version": result.stdout.strip()}
        return {"installed": False, "version": None}
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return {"installed": False, "version": None}


def _check_pptxgenjs(node_installed: bool) -> dict:
    """检测 pptxgenjs npm 包是否可用（本地或全局）"""
    if not node_installed:
        return {"installed": False, "version": None}
    try:
        result = subprocess.run(
            ["node", "-e", "const p=require('pptxgenjs');console.log(p.version||'ok')"],
            capture_output=True, text=True, timeout=8
        )
        if result.returncode == 0:
            return {"installed": True, "version": result.stdout.strip()}
        return {"installed": False, "version": None}
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return {"installed": False, "version": None}


def check_all() -> dict:
    """检测所有依赖，返回结构化结果。"""
    results = []
    missing_required = []
    missing_optional = []
    for import_name, pip_name, required, desc in DEPS:
        ok = _is_installed(import_name)
        results.append({
            "import_name": import_name,
            "pip_name": pip_name,
            "required": required,
            "installed": ok,
            "desc": desc,
        })
        if not ok:
            (missing_required if required else missing_optional).append(pip_name)

    # Node.js + pptxgenjs 检测（Workflow 2 PptxGenJS 路线所需）
    node_info    = _check_node()
    pptxgen_info = _check_pptxgenjs(node_info["installed"])

    return {
        "interpreter": sys.executable,
        "results": results,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
        "ready": len(missing_required) == 0,
        "node": node_info,
        "pptxgenjs": pptxgen_info,
    }


def install_missing(pip_names: list[str]) -> bool:
    """用当前解释器安装指定包，返回是否全部成功。"""
    if not pip_names:
        return True
    cmd = [sys.executable, "-m", "pip", "install", *pip_names]
    print(f"▶ 执行：{' '.join(cmd)}")
    try:
        subprocess.check_call(cmd)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 安装失败（exit {e.returncode}）")
        return False


def print_report(report: dict) -> None:
    print(f"\n{'='*60}")
    print("PowerPoint Editor - 依赖自检")
    print(f"解释器：{report['interpreter']}")
    print(f"{'='*60}")
    for r in report["results"]:
        mark = "[OK]" if r["installed"] else ("[X] " if r["required"] else "[!] ")
        tag = "必需" if r["required"] else "可选"
        status = "已安装" if r["installed"] else "缺失"
        print(f"  {mark} [{tag}] {r['pip_name']:<14} {status:<5} - {r['desc']}")

    # Node.js / pptxgenjs
    n = report["node"]
    p = report["pptxgenjs"]
    node_mark    = "[OK]" if n["installed"] else "[!] "
    pptxgen_mark = "[OK]" if p["installed"] else "[!] "
    node_ver     = f"  ({n['version']})" if n.get("version") else ""
    pptxgen_ver  = f"  ({p['version']})" if p.get("version") else ""
    print(f"  {node_mark} [可选] node.js        {'已安装' if n['installed'] else '缺失':<5}{node_ver} - Workflow 2 PptxGenJS 创建PPT")
    print(f"  {pptxgen_mark} [可选] pptxgenjs      {'已安装' if p['installed'] else '缺失':<5}{pptxgen_ver} - Workflow 2 PptxGenJS（npm install pptxgenjs）")

    print(f"{'-'*60}")
    if report["ready"]:
        print("[OK] 必需依赖齐全，可以执行 PPT 任务。")
        if report["missing_optional"]:
            opt = " ".join(report["missing_optional"])
            print(f"[!]  可选依赖缺失（不影响主流程）：{opt}")
            print(f"     如需布局可视化：{report['interpreter']} -m pip install {opt}")
        if not n["installed"]:
            print("[!]  Node.js 未安装：Workflow 2（PptxGenJS）不可用")
            print("     安装：https://nodejs.org  →  然后在 powerpoint-editor/ 目录 npm install pptxgenjs")
        elif not p["installed"]:
            print("[!]  pptxgenjs 未安装：在 powerpoint-editor/ 目录执行 npm install pptxgenjs")
    else:
        req = " ".join(report["missing_required"])
        print(f"[X] 缺少必需依赖：{req}")
        print(f"    请执行：{report['interpreter']} -m pip install {req}")
        print(f"    或自动安装：python check_deps.py --install")
    print(f"{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="PowerPoint Editor 依赖自检")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--install", action="store_true", help="自动安装缺失的必需依赖")
    args = parser.parse_args()

    report = check_all()

    if args.install and report["missing_required"]:
        ok = install_missing(report["missing_required"])
        report = check_all()  # 重新检测
        report["install_attempted"] = True
        report["install_success"] = ok

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report)

    sys.exit(0 if report["ready"] else 1)


if __name__ == "__main__":
    main()
