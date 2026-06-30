---
name: PowerPoint Editor
description: "PPT 全功能 skill。编辑现有 PPTX（改内容/调布局/补数据）；从零创建演示文稿（⭐ PptxGenJS 原生可编辑 + 完整设计系统）。强制三阶段工作流：检查→编辑→验证，防止视觉破坏和数据损坏。支持 Windows / macOS / Linux。"
version: 1.1.0
---

## 适用场景

以下情况使用本 skill：

- 修改现有 PPT 的文字内容（标题、正文、标签）
- 调整幻灯片布局（位置、尺寸、对齐）
- 补充或更新表格数据
- 更新图表数据（系列数据、分类标签）
- 批量替换多页内容

**从头创建全新 PPT：** 使用本 skill 的「从零创建 PPT」工作流（见文末）。

---

## 依赖

### 环境自检（按需，非强制）

依赖安装好后通常不需要重复检查。以下两种情况再跑：

1. **首次使用**本 skill（环境从未配置过）
2. **任务报 ImportError / ModuleNotFoundError** 等缺包错误时

```bash
python scripts/check_deps.py            # 文本报告
python scripts/check_deps.py --install  # 检测并自动安装缺失依赖
python scripts/check_deps.py --json     # JSON 格式（脚本解析用）
```

退出码 `0` = 依赖齐全；`1` = 有缺失，按提示安装后继续。

依赖分级：

| 包 | 必需 | 缺失影响 |
|----|------|---------|
| `python-pptx` | 是 | 无法读取/编辑 PPTX、inspect.py 不可用 |
| `matplotlib` | 否 | preview.py 布局可视化不可用（可降级跳过）|

### 手动安装（备用）

```bash
# 编辑现有 PPT（必须）
pip install python-pptx

# 布局可视化，可选
pip install matplotlib
```

---

## 工具脚本（scripts/）

| 脚本 | 用途 | 阶段 |
|------|------|------|
| `check_deps.py` | 依赖自检：检测/安装 python-pptx、matplotlib | 首次使用或遇缺包错误时 |
| `inspect.py` | 分析 PPTX 结构：shape 坐标、字体、关联分析、溢出风险 | 检查 + 验证 |
| `preview.py` | 将布局可视化输出为 PNG，编辑前后对比 | 检查 + 验证 |
| `safe_save.py` | 安全保存，检测文件是否被 PowerPoint 占用 | 编辑 |


---

## 核心工作流（三阶段强制执行）

### 阶段1：检查（强制，不可跳过）

**目的：** 在编辑前完整了解文件结构，获取 shape 索引、占位符 idx、字体属性、坐标。

```bash
# 分析指定页（推荐用绝对路径）
python scripts/inspect.py <文件路径> --slide N

# 附加空间关联分析（识别固定边界元素、锚点分组）
python scripts/inspect.py <文件路径> --slide N --relations

# 附加溢出风险评估
python scripts/inspect.py <文件路径> --slide N --overflow

# 可视化布局（输出 PNG）
python scripts/preview.py <文件路径> --slide N

# 分析所有页
python scripts/inspect.py <文件路径>
```

**读懂以下信息后方可进入阶段2：**
- 目标 shape 的索引（index）和 id
- 占位符 idx（如有）
- 原有字体名称、字号、颜色
- 原有坐标（left / top / width / height）
- 固定边界元素的位置（色条、页码等，调布局时必须识别）
- 表格的行列数（如涉及表格）
- 图表的系列数和类型（如涉及图表）

---

### 阶段2：编辑（生成一次性脚本执行）

根据任务类型，参考对应规范生成专用 Python 脚本：

| 任务类型 | 参考文档 | 核心 API |
|---------|---------|---------|
| 改文字内容 | [edit-rules.md § 规则二、三](references/edit-rules.md) | `run.text` |
| 调布局位置/尺寸 | [edit-rules.md § 规则六、十、十一、十二](references/edit-rules.md) | `shape.left/top/width/height` |
| 补充表格数据 | [edit-rules.md § 规则五](references/edit-rules.md) | `cell.text_frame` |
| 更新图表数据 | [edit-rules.md § 规则七](references/edit-rules.md) | `chart.replace_data()` |

**每次生成的脚本必须包含：**

```python
import sys
import io
import os
import shutil
from datetime import datetime

# ── Windows CMD UTF-8 输出（必须在所有 print 之前）──────────────
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
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

# safe_save 用 importlib 导入（避免 sys.path 污染导致 inspect 标准库冲突）
import importlib.util as _ilu
_ss_spec = _ilu.spec_from_file_location(
    "safe_save",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "safe_save.py")
)
_ss_mod = _ilu.module_from_spec(_ss_spec)
_ss_spec.loader.exec_module(_ss_mod)
safe_save_pptx = _ss_mod.safe_save_pptx

# 1. 备份原文件（编辑前必须执行）
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = src_path.replace(".pptx", f"_backup_{ts}.pptx")
shutil.copy2(src_path, backup_path)
print(f"✅ 备份：{backup_path}")

# 2. 编辑操作（使用 run 方式，保留字体属性）
# ...

# 3. 安全保存（替代 prs.save()，防止文件被 PowerPoint 占用报错）
safe_save_pptx(prs, output_path)
```

**数据来源处理：**

- **用户直接提供** → 数据硬编码在脚本中，直接执行
- **从文件读取（Excel/CSV）** → 使用 EasyClaw 内置文件读取技能获取数据后，传入脚本变量

---

### 阶段3：验证（强制）

```bash
# 对比编辑后的文件结构
python scripts/inspect.py <输出文件路径> --slide N

# 可视化对比（与阶段1生成的 before.png 对比）
python scripts/preview.py <输出文件路径> --slide N --out after.png
```

逐项确认 [edit-rules.md 检查清单](references/edit-rules.md)：

- [ ] 备份文件已创建
- [ ] 字体属性与原文件一致
- [ ] 无占位符残留文字
- [ ] 无文字截断（高风险溢出已处理）
- [ ] 表格/图表数据正确
- [ ] 布局调整时：未超出固定边界元素区域
- [ ] 多 shape 重新分布时：已以锚点为中心对齐

---

## 典型任务示例

### 任务1：修改某页文字

```
用户：把第3页标题改为"2026年Q1财报"
AI 执行：
  1. python scripts/inspect.py file.pptx --slide 3
  2. 找到标题 shape（name 含"Title"或 placeholder idx=0）
  3. 生成脚本：备份 → run.text 修改 → safe_save_pptx 保存
  4. python scripts/inspect.py output.pptx --slide 3 验证
```

### 任务2：更新表格数据

```
用户：把第5页的销售数据表格更新为新数据
AI 执行：
  1. python scripts/inspect.py file.pptx --slide 5
  2. 确认表格 shape 索引、行列数
  3. 获取数据（用户提供 或 EasyClaw 读取 Excel）
  4. 生成脚本：备份 → 逐行逐列更新 cell → 保存
  5. inspect 验证表格内容
```

### 任务3：更新图表数据

```
用户：把第8页的柱状图数据更新为最新季度数据
AI 执行：
  1. python scripts/inspect.py file.pptx --slide 8
  2. 确认图表类型、系列数、分类数
  3. 获取新数据，严格匹配原系列数和分类数
  4. 生成脚本：备份 → chart.replace_data() → 保存
  5. inspect 验证图表结构
```

### 任务4：调整布局

```
用户：把第2页的文本框往下移0.5英寸，高度增加0.3英寸
AI 执行：
  1. python scripts/inspect.py file.pptx --slide 2 --relations
  2. 确认目标 shape 原始坐标，识别固定边界元素
  3. 生成脚本：备份 → shape.top += Inches(0.5), shape.height += Inches(0.3) → 保存
  4. inspect + preview 验证新坐标
```

---

## 参考文档

| 文档 | 内容 |
|------|------|
| [references/edit-rules.md](references/edit-rules.md) | 编辑规范，12条规则 + 检查清单 |
| [references/python-pptx.md](references/python-pptx.md) | python-pptx API 速查 |
| [references/pitfalls.md](references/pitfalls.md) | 19条已知陷阱 + 故障排查表 |
| [references/tools.md](references/tools.md) | 三个工具脚本详细说明 |

---

## 重要提示

1. **不读结构，不编辑** — 阶段1是强制的，不是可选的
2. **一次性脚本** — 每个编辑任务生成专用脚本，不复用通用接口
3. **保留视觉语言** — 改内容，不改样式（除非用户明确要求）
4. **备份优先** — 任何编辑操作前必须先备份原文件
5. **安全保存** — 使用 `safe_save_pptx()` 替代 `prs.save()`
6. **验证闭环** — 改完必须用 inspect.py 验证，不假设成功
7. **识别边界** — 调布局前必须用 `--relations` 识别固定边界元素

---

## 从零创建 PPT：PptxGenJS ⭐

### 依赖安装

```bash
# 在 powerpoint-editor/ 目录下安装（首次使用运行一次）
npm install pptxgenjs
npm install react-icons react react-dom sharp   # 图标支持（可选）
pip install "markitdown[pptx]"                   # QA 内容验证
```

> ⚠️ **打包说明：** 技能包上线时 **不携带 `node_modules/`**。用户首次运行前执行 `python scripts/check_deps.py --install` 即可自动安装全部 Node.js 依赖。

---

### ⚠️ Pre-Flight Checklist（动手前必须完成）

**不要跳过此步骤。** 写第一行代码之前，确认以下所有项：

- [ ] 已读 [design-system.md](references/design-system.md) — 调色板选择、颜色规则、字体配对、风格食谱
- [ ] 已读 [slide-types.md](references/slide-types.md) — 5种页型、子类型、字号层级
- [ ] 已读 [pitfalls.md](references/pitfalls.md) — 常见错误和 PptxGenJS 致命陷阱
- [ ] 调色板已从18个选项中选定 — **调色板名称：___**
- [ ] 5个 theme key 已映射到调色板颜色 — `primary / secondary / accent / light / bg`
- [ ] 风格食谱已选定 — **Sharp / Soft / Rounded / Pill（圈选一个）**
- [ ] 字体配对已选定 — **标题字体：___ / 正文字体：___**
- [ ] 每张幻灯片已归类为5种页型之一
- [ ] 至少每个主要章节有一张 Section Divider（不可省略）
- [ ] 相邻内容页使用不同子类型
- [ ] 每张内容页至少有一个非文字视觉元素（全幅图→image-gen；图标→PptxGenJS形状；禁 emoji）
- [ ] 小型图标/装饰用 OVAL/RECTANGLE 等原生形状，不走 image-gen
- [ ] 长文本已按字符数估算行数并预留足够 box 高度
- [ ] 需要图片素材的页面已列出清单，准备调用 image-gen 生图
- [ ] 所有颜色只用 `theme.*` key，零硬编码 hex

---

### 工作流步骤

**Step 1：研究需求**
搜索了解主题、受众、目的、基调、内容深度。同步收集视觉参考：浏览搜索结果中的实拍图、信息图，提取可复用的构图手法（如"对角线构图""低角度仰拍""极简白底"），写入后续的 image-gen prompt 中以提升生图质量。勿直接使用网页图片（版权风险）。

**Step 2：选调色板 + 字体**
从 [design-system.md 调色板参考](references/design-system.md#color-palette-reference) 选择调色板。
从 [字体配对表](references/design-system.md#recommended-font-pairings) 选择字体。

**Step 3：选设计风格**
从 [风格食谱](references/design-system.md#style-recipes) 选择 Sharp / Soft / Rounded / Pill。

**Step 4：规划幻灯片大纲**
每张幻灯片归类为 [5种页型](references/slide-types.md) 之一，确保视觉多样性。同时标注需要图片素材的页面。

**Step 4.5：生成图片素材（有需要则执行）**

> 🎨 视觉素材分两级：**全幅背景/大幅面配图** → image-gen 生图；**图标/装饰元素** → PptxGenJS 原生形状（矢量、零成本、风格统一）。

**素材选用决策：**

| 素材类型 | 来源 | 原因 |
|---------|------|------|
| Cover 全幅背景图 | image-gen | 需要真实摄影感 |
| Content 页半版/大幅配图 | image-gen | 需要真实场景支撑 |
| 卡片小图标（如装备、鱼种） | **PptxGenJS 形状** | 小尺寸下 AI 生图留白多、风格不统一 |
| 勾/叉/箭头/分隔线 | **PptxGenJS 形状** | 纯几何形状，形状渲染完美 |
| 星级评分 | **文本字符 ★☆** | 矢量文字，不依赖图片 |
| 数字序号圆 | **PptxGenJS OVAL + 文本** | 原生形状，颜色精确可控 |

**生图流程：**
1. 根据每页的视觉需求，为每张图构造英文 prompt（遵循 image-gen 的公式：主体+场景+风格+光线+构图+质量）
2. 调用 image-gen 脚本生图，保存到 `slides/imgs/` 目录：
   ```bash
   python {image-gen}/scripts/generate_image.py --prompt "..." --filename "{workspace}/ppt-project/slides/imgs/slide-03-hero.png" --size 1536x1024
   ```
3. 在对应的 slide-XX.js 中使用 `slide.addImage()` 引入图片：
   ```javascript
   slide.addImage({ path: "imgs/slide-03-hero.png", x: 0, y: 0, w: 5, h: 3 });
   ```
4. 生图时始终使用 `{workspace}` 下的绝对路径作为 `--filename`
5. Slide JS 文件中的图片路径使用相对路径 `imgs/xxx.png`（compile.js 运行时 cwd = slides/）

**图片尺寸建议：**
| 用途 | --size | 说明 |
|------|--------|------|
| Cover 全幅背景 | 1536x1024 | 16:9 横版，覆盖整个幻灯片 |
| 半版配图（左/右） | 1024x1024 | 方形，适配半栏布局 |
| 小插图/图标位 | 1024x1024 | 方形，区域内裁剪 |
| 竖版插图 | 1024x1536 | 3:4 竖版，适配窄栏 |

**注意：** 生图耗时较长（每张数十秒），应并行调用所有独立的生图任务，不要串行等待。

**Step 5：生成每张幻灯片 JS 文件**

目录结构：
```
slides/
├── slide-01.js
├── slide-02.js
├── ...
├── compile.js
├── imgs/           # 图片资源（AI生图 + 外部素材）
│   ├── slide-01-bg.png
│   ├── slide-03-hero.png
│   └── ...
└── output/         # 最终 PPTX
```

每个文件格式（**必须同步，不能用 async/await**）。

> 🔌 **require 路径规则：** 所有 slide-XX.js 和 compile.js 中必须使用 `require("pptxgenjs")` 而非相对路径。AI 生成时在 compile.js 顶部插入一行 `const pptxgen = require("pptxgenjs");` 即可，Node.js 会沿着目录树向上查找 `node_modules/`。用户在任意工作目录下创建 PPT 项目后，只需在该目录 `npm install pptxgenjs` 或在父级目录安装。

```javascript
// slide-01.js
const pptxgen = require("pptxgenjs");

const slideConfig = { type: 'cover', index: 1, title: '标题' };

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText(slideConfig.title, {
    x: 0.5, y: 2, w: 9, h: 1.2,
    fontSize: 72, fontFace: "Microsoft YaHei",
    color: theme.primary, bold: true, align: "center"
  });
  return slide;
}

if (require.main === module) {
  const pres = new pptxgen();
  pres.layout = 'LAYOUT_16x9';
  const theme = { primary: "22223b", secondary: "4a4e69", accent: "9a8c98", light: "c9ada7", bg: "f2e9e4" };
  createSlide(pres, theme);
  pres.writeFile({ fileName: "slide-01-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
```

**Step 6：compile.js 合并输出**

```javascript
// slides/compile.js
const pptxgen = require('pptxgenjs');
const pres = new pptxgen();
pres.layout = 'LAYOUT_16x9';

const theme = {
  primary: "22223b",
  secondary: "4a4e69",
  accent: "9a8c98",
  light: "c9ada7",
  bg: "f2e9e4"
};

for (let i = 1; i <= 10; i++) {   // 按实际页数调整
  const num = String(i).padStart(2, '0');
  require(`./slide-${num}.js`).createSlide(pres, theme);
}

pres.writeFile({ fileName: './output/presentation.pptx' });
```

```bash
cd slides && node compile.js
```

**Step 7：QA 验证**

```bash
python -m markitdown slides/output/presentation.pptx
# 检查：内容完整、无占位符残留、无 lorem ipsum
python -m markitdown slides/output/presentation.pptx | findstr /i "xxxx lorem ipsum placeholder"
# 有结果则修复后重跑
```

详见 [pitfalls.md QA 流程](references/pitfalls.md#qa-process)。

---

### Theme Object Contract（必须遵守）

| Key | 用途 | 示例 |
|-----|------|------|
| `theme.primary` | 最深色，标题 | `"22223b"` |
| `theme.secondary` | 次强调，正文 | `"4a4e69"` |
| `theme.accent` | 中调强调 | `"9a8c98"` |
| `theme.light` | 浅强调 | `"c9ada7"` |
| `theme.bg` | 背景色 | `"f2e9e4"` |

**禁止使用其他 key 名**（如 `background`、`text`、`muted` 等）。

---

### 页码徽章（Cover 以外所有页必须加）

位置固定：`x: 9.3", y: 5.1"`

```javascript
// 圆形（默认）
slide.addShape(pres.shapes.OVAL, { x: 9.3, y: 5.1, w: 0.4, h: 0.4, fill: { color: theme.accent } });
slide.addText("3", { x: 9.3, y: 5.1, w: 0.4, h: 0.4, fontSize: 12, fontFace: "Arial",
  color: "FFFFFF", bold: true, align: "center", valign: "middle" });
```

---

### 关键禁止项

| 禁止 | 原因 |
|------|------|
| `color: "#FF0000"` | `#` 号导致文件损坏 |
| `color: "FFFFFFbb"` | 8位 hex 包含透明度，PptxGenJS 不支持，用 `transparency` 属性替代 |
| `shadow: { color: "00000020" }` | 8位 hex 编码透明度导致文件损坏，用 `opacity` 属性 |
| `async function createSlide()` | compile.js 不会 await，幻灯片丢失 |
| 复用 option 对象 | PptxGenJS 原地修改对象，第二次调用数据错误 |
| unicode 项目符号（`"* 文字"`）| 产生双重项目符号，用 `bullet: true` |
| 标题下方加装饰线 | AI 生成 PPT 的典型标志，改用留白或背景色区分 |

完整陷阱列表见 [pitfalls.md](references/pitfalls.md)。
完整 API 参考见 [pptxgenjs.md](references/pptxgenjs.md)。
