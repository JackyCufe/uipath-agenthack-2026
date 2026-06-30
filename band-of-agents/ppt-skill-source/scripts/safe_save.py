"""
safe_save.py — PPTX 安全保存工具
用法（在编辑脚本中导入）：

    from safe_save import safe_save_pptx
    safe_save_pptx(prs, output_path)

功能：
  1. 保存前检测目标文件是否被占用（PowerPoint 打开中）
  2. 被占用时给出清晰提示，不抛出难以理解的 PermissionError
  3. 路径含中文时自动用 UTF-8 安全处理，避免乱码
  4. 保存成功后打印确认信息
"""

import sys
import io
import os
from pathlib import Path

# ── 中文输出不乱码 ─────────────────────────────────────────────────
# 设环境变量对子进程和后续 Python 调用也生效；_force_utf8 双保险覆盖管道场景。
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")

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

# 仅命令行直接运行时立即重包装；被 import 时不干扰调用方的 stdout
def _setup_utf8_stdout():
    sys.stdout = _force_utf8(sys.stdout)
    sys.stderr = _force_utf8(sys.stderr)
# ──────────────────────────────────────────────────────────────────


def check_file_locked(path: str) -> bool:
    """
    检测文件是否被其他进程锁定（如 PowerPoint 打开中）。
    返回 True 表示被锁定，False 表示可以写入。

    跨平台实现：
    - Windows：Office 会对文件加排他写锁，尝试以 r+b 打开即可检测
    - macOS/Linux：Office 使用 advisory lock，直接尝试写入临时副本来检测
    """
    import platform
    p = Path(path)
    if not p.exists():
        return False  # 文件不存在，不存在锁定问题

    system = platform.system()

    if system == "Windows":
        # Windows：尝试以写模式打开，若失败说明被排他锁定
        try:
            fd = open(str(p), 'r+b')
            fd.close()
            return False
        except (PermissionError, OSError):
            return True
    else:
        # macOS / Linux：Office 使用 advisory lock，无法通过 open 检测
        # 改为检测 Office 的临时锁文件（~$filename.pptx）
        lock_file = p.parent / f"~${p.name}"
        if lock_file.exists():
            return True
        # 兜底：尝试重命名再还原（非破坏性，能检测写权限）
        try:
            tmp = str(p) + ".__lock_test__"
            os.rename(str(p), tmp)
            os.rename(tmp, str(p))
            return False
        except (PermissionError, OSError):
            return True


def safe_save_pptx(prs, output_path: str, auto_rename: bool = False) -> str:
    """
    安全保存 PPTX。

    参数：
      prs          — python-pptx Presentation 对象
      output_path  — 目标保存路径（字符串或 Path）
      auto_rename  — 若文件被占用，是否自动改名保存（默认 False，直接报错）

    返回：
      实际保存的路径字符串

    异常：
      若 auto_rename=False 且文件被占用，打印提示并 sys.exit(1)
    """
    from datetime import datetime

    output_path = str(output_path)
    p = Path(output_path)

    # 确保目标目录存在
    p.parent.mkdir(parents=True, exist_ok=True)

    if check_file_locked(output_path):
        if auto_rename:
            # 自动在文件名后加时间戳
            ts = datetime.now().strftime("%H%M%S")
            new_path = str(p.parent / f"{p.stem}_{ts}{p.suffix}")
            print(f"⚠️  目标文件被占用（可能在 PowerPoint 中打开）")
            print(f"   已自动改名保存到：{new_path}")
            output_path = new_path
        else:
            print(f"❌ 保存失败：目标文件正被占用")
            print(f"   文件路径：{output_path}")
            print(f"   请先关闭 PowerPoint 中的该文件，然后重试。")
            print(f"   或使用 safe_save_pptx(prs, path, auto_rename=True) 自动改名保存。")
            sys.exit(1)

    try:
        prs.save(output_path)
        print(f"✅ 文件已保存：{output_path}")
        return output_path
    except PermissionError:
        # 极少数情况：检测时未锁但保存时被锁（竞争窗口）
        print(f"❌ 保存失败：写入时文件被锁定")
        print(f"   请关闭 PowerPoint 后重试，或使用 auto_rename=True。")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 保存失败：{e}")
        sys.exit(1)


# ── 命令行直接调用（验证用） ───────────────────────────────────────
if __name__ == "__main__":
    _setup_utf8_stdout()
    import argparse
    parser = argparse.ArgumentParser(description="检测 PPTX 文件是否被占用")
    parser.add_argument("file", help="PPTX 文件路径")
    args = parser.parse_args()

    if check_file_locked(args.file):
        print(f"⚠️  文件被占用（PowerPoint 可能正在打开）：{args.file}")
        sys.exit(1)
    else:
        print(f"✅ 文件未被占用，可以安全写入：{args.file}")
