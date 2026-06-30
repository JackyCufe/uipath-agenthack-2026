# tools.md — 脚本工具说明

`scripts/` 目录下的工具脚本，覆盖检查、编辑、验证、创建全流程。

---

## inspect.py — 结构分析（阶段1必用）

```bash
python scripts/inspect.py <文件>                          # 分析所有页
python scripts/inspect.py <文件> --slide N               # 分析第N页（1-based）
python scripts/inspect.py <文件> --slide N --json        # JSON 格式输出（供脚本解析）
python scripts/inspect.py <文件> --slide N --relations   # 附加 shape 空间关联分析
python scripts/inspect.py <文件> --slide N --overflow    # 附加文字溢出风险评估
python scripts/inspect.py <文件> --layouts               # 列出所有可用幻灯片版式
```

**关键功能：**
- 输出每个 shape 的 id、name、type、坐标（英寸）、文字内容、字体
- `--relations`：识别固定边界元素 + 中心轴对齐分组 + 上下左右最近邻
- `--overflow`：对每个文本框估算是否有溢出风险（high/medium/low）
- `--layouts`：列出模板/文件的所有版式名称及占位符 idx（模板填充前必看）

**依赖：** `python-pptx`

> **注意：** 此脚本名为 `inspect.py`，与 Python 标准库同名。脚本内部已修复 `sys.path` 冲突问题，直接运行无需特殊处理。

---

## preview.py — 布局可视化（编辑前/后对比）

```bash
python scripts/preview.py <文件> --slide N                 # 保存 PNG 到 PPTX 同目录
python scripts/preview.py <文件> --slide N --out path.png  # 指定输出路径
python scripts/preview.py <文件> --all                     # 每页输出一张 PNG
```

**输出内容：**
- 按比例绘制所有 shape 的位置和尺寸（色块示意图）
- 不同 shape 类型用不同颜色区分（TEXT_BOX / AUTO_SHAPE / PICTURE / TABLE / CHART）
- 固定边界元素自动标红并加 `[边界]` 标注
- 标注每个 shape 的 id 和前12字文本
- 附网格线（0.5in 间距），便于目测坐标

**典型使用场景：**
1. 编辑前运行 → 了解布局关系，识别固定元素
2. 编辑后运行 → 验证调整结果，确认无重叠

**依赖：** `python-pptx`、`matplotlib`（`pip install matplotlib`）

**中文支持：** 自动检测系统字体，Windows 优先使用 Microsoft YaHei，macOS 使用 PingFang SC。

---

## safe_save.py — 安全保存（编辑脚本 import 使用）

```python
# 在编辑脚本中替换 prs.save(path)：
import importlib.util, os
_spec = importlib.util.spec_from_file_location("safe_save",
    os.path.join(os.path.dirname(__file__), "scripts", "safe_save.py"))
_mod = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_mod)
safe_save_pptx = _mod.safe_save_pptx

safe_save_pptx(prs, output_path)                    # 被占用时报错退出
safe_save_pptx(prs, output_path, auto_rename=True)  # 被占用时自动改名保存
```

**功能：**
- 保存前检测文件是否被 PowerPoint 锁定
- 被占用时输出清晰中文提示，而不是难以理解的 `PermissionError`
- `auto_rename=True` 时自动在文件名后加时间戳（如 `_143022.pptx`）

**命令行验证用法：**
```bash
python scripts/safe_save.py <文件路径>   # 检测文件是否被占用
```

**依赖：** 仅 Python 标准库，无需安装

---

## template_fill.py — 模板填充引擎（工作流一）

```bash
# 列出模板可用版式（填充前必须先看）
python scripts/template_fill.py --template <模板.pptx> --list-layouts

# 执行填充
python scripts/template_fill.py \
    --template <模板.pptx> \
    --content  <内容.json> \
    --output   <输出.pptx>
```

**功能：** 加载 `.pptx` 模板，按 JSON 内容逐页选版式、填占位符，产物 100% 原生可编辑。

**内容 JSON 结构：**
```json
{
  "slides": [
    {
      "layout": 0,
      "placeholders": {
        "0": "标题文字",
        "1": "副标题或正文",
        "2": ["要点一", "要点二", "要点三"]
      },
      "image": { "idx": 3, "path": "图片路径.png" }
    }
  ]
}
```

> `layout` 为整数索引（0-based），用 `--list-layouts` 查看各模板支持的索引范围。

> `layout` 名称来自 `--list-layouts` 的输出。`image` 字段可选，用于图片占位符（type=PICTURE）。

**依赖：** `python-pptx`

---

## check_deps.py — 依赖自检（首次使用或遇缺包报错时）

```bash
python scripts/check_deps.py            # 检测所有依赖，输出报告
python scripts/check_deps.py --install  # 检测并自动安装缺失的必需依赖
python scripts/check_deps.py --json     # JSON 格式输出（供脚本解析）
```

| 依赖 | 级别 | 用途 |
|------|------|------|
| `python-pptx` | 必需 | inspect.py / template_fill.py / safe_save.py |
| `matplotlib` | 可选 | preview.py 布局可视化 |
| `markitdown` | 可选 | PptxGenJS 工作流 QA 验证（`python -m markitdown output.pptx`）|

退出码：`0` = 必需依赖齐全；`1` = 有缺失。

---

## make_demo_templates.py — 内置模板生成器（一次性工具）

```bash
python scripts/make_demo_templates.py
```

**功能：** 生成三套内置 demo 模板到 `templates/` 目录：
- `business_dark.pptx` — 深色商务风
- `clean_light.pptx`   — 浅色简约风
- `warm_report.pptx`   — 暖色报告风

> 通常只在初始化或需要重置模板时运行一次。已有模板文件时无需重复运行。

**依赖：** `python-pptx`

---

## 六工具协作流程

```
编辑现有 PPT：
  check_deps.py          →  首次使用时检查依赖
  inspect.py --slide N   →  读懂结构，获取 shape 索引/坐标/字体
  preview.py --slide N   →  可视化布局，识别固定边界元素
    ↓ 生成一次性编辑脚本
  safe_save_pptx()       →  安全保存，避免文件锁定
  inspect.py --slide N   →  验证修改结果
  preview.py --slide N   →  对比前后布局截图

从模板创建 PPT（工作流一）：
  inspect.py --layouts   →  列出模板版式名称和占位符 idx
  template_fill.py       →  填充 JSON 内容到模板
  inspect.py             →  验证填充结果

从零创建 PPT（工作流二 PptxGenJS）：
  check_deps.py          →  确认 Node.js 和 pptxgenjs 可用
    ↓ 生成 slide-XX.js + compile.js
  node compile.js        →  编译生成 output.pptx
  python -m markitdown   →  QA 验证文字内容完整性
```
