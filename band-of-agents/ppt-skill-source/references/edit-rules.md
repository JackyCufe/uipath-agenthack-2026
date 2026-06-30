# edit-rules.md — 编辑规范

编辑现有 PPTX 的核心规则。所有编辑操作必须遵守本文件，违反任何一条都可能导致文件损坏或视觉破坏。

---

## 强制工作流（三阶段，不可跳过）

```
阶段1：检查（必须先执行）
  python scripts/inspect.py <文件> --slide N
  → 读懂结构：shape 索引、占位符 idx、字体、坐标
  → 没读过结构，不允许编辑

阶段2：编辑（按任务类型选择方式）
  → 改文字：直接修改 run.text，保留字体属性
  → 调布局：修改 shape.left / top / width / height
  → 补数据：修改表格 cell.text 或重建图表数据
  → 备份：编辑前自动保存 _backup_YYYYMMDD_HHMMSS.pptx
  → 保存：使用 safe_save_pptx() 代替 prs.save()，防止文件被占用

阶段3：验证（必须执行）
  python scripts/inspect.py <输出文件> --slide N
  python scripts/preview.py <输出文件> --slide N   # 可视化确认布局
  → 对比编辑前后差异
  → 确认无文字截断、无占位符残留、无坐标偏移
```

---

## 规则一：永远保留原有视觉语言

- **不改字体名称**：除非用户明确要求，否则保持原有字体
- **不改颜色**：保持原有 RGB 颜色，不引入新颜色
- **不改字号**：除非内容变长导致溢出，否则保持原有字号
- **不改坐标**：除非用户明确要求调整布局，否则保持原有位置
- **不改对齐方式**：保持原有段落对齐

改内容 ≠ 改样式。两者必须分开操作。

---

## 规则二：改文字必须通过 run，不能替换整个 text_frame

**正确做法：**
```python
# 保留字体属性，只改文字
run = shape.text_frame.paragraphs[0].runs[0]
original_size  = run.font.size
original_bold  = run.font.bold
try:
    original_color = run.font.color.rgb if run.font.color.type else None
except Exception:
    original_color = None  # 颜色继承自主题，无需手动恢复

run.text = "新内容"

run.font.size = original_size
run.font.bold = original_bold
if original_color:
    run.font.color.rgb = original_color
```

**禁止做法：**
```python
# ❌ 会清除所有字体格式
shape.text_frame.text = "新内容"
# ❌ 会破坏段落结构
shape.text_frame.paragraphs[0].text = "新内容"
```

---

## 规则三：多段落文本框必须逐段处理

一个 shape 可能有多个段落（paragraph），每个段落有独立格式。

```python
# 场景：shape 有3个段落，只改第2段
tf = shape.text_frame
para = tf.paragraphs[1]  # 0-based
if para.runs:
    para.runs[0].text = "新内容"
else:
    # 段落无 run 时，添加新 run
    from pptx.util import Pt
    run = para.add_run()
    run.text = "新内容"
```

---

## 规则四：编辑前必须备份

```python
import shutil
from datetime import datetime

def backup(src_path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = src_path.replace(".pptx", f"_backup_{ts}.pptx")
    shutil.copy2(src_path, dst)
    print(f"✅ 备份已创建：{dst}")
    return dst
```

备份文件命名规则：`原文件名_backup_YYYYMMDD_HHMMSS.pptx`，与原文件同目录。

---

## 规则五：表格编辑保留单元格格式

```python
# 只改文字，不动格式
cell = shape.table.rows[row_idx].cells[col_idx]
# 遍历段落和 run 保留格式
for para in cell.text_frame.paragraphs:
    for run in para.runs:
        run.text = new_text
        break  # 通常只需改第一个 run
    break
```

如果单元格无 run：
```python
para = cell.text_frame.paragraphs[0]
run = para.add_run()
run.text = new_text
```

---

## 规则六：布局调整使用 EMU 单位

python-pptx 内部使用 EMU（英制度量单位）：
- 1 英寸 = 914400 EMU
- 使用 `pptx.util.Inches()` 和 `pptx.util.Pt()` 转换

```python
from pptx.util import Inches, Pt

shape.left   = Inches(1.0)   # 距左边 1 英寸
shape.top    = Inches(2.5)   # 距顶部 2.5 英寸
shape.width  = Inches(8.0)   # 宽度 8 英寸
shape.height = Inches(1.2)   # 高度 1.2 英寸
```

调整布局前，必须先用 inspect.py 确认原始坐标，避免盲目移动。

---

## 规则七：调整布局前必须识别固定边界元素

在调整任何 shape 的位置或尺寸之前，必须先识别幻灯片上的**固定边界元素**，包括：

- 左侧/右侧色条、装饰边框（通常是细高的矩形，贯穿整个幻灯片高度）
- 页码徽章、Logo、水印（通常固定在角落）
- 标题区、时间线等结构性锚点元素

**识别方法：**
```python
# 在 inspect 输出中，重点关注：
# - height 接近幻灯片高度（5.625in）的 shape → 很可能是边条
# - 位于幻灯片四角的小 shape → 很可能是页码/Logo
# - 无文字、无图表的纯色矩形 → 很可能是装饰元素
```

**计算可用区域：**
```
可用左边界 = 左侧边条的 right（left + width）+ 安全间距（≥ 0.03in）
可用右边界 = 右侧边条的 left（或页码shape的 left）- 安全间距
可用区域宽度 = 可用右边界 - 可用左边界
```

**禁止：** 将内容 shape 的 left 设置为小于可用左边界的值，即使数学上"还有空间"。

---

## 规则八：图表数据修改必须匹配原有系列数量

图表的分类数（categories）和系列数（series）必须与原图表完全一致，否则图表崩溃。

```python
from pptx.chart.data import ChartData

# 先用 inspect.py 确认原图表的系列数和类型
# series_count 必须与原图表一致
chart_data = ChartData()
chart_data.categories = ["Q1", "Q2", "Q3", "Q4"]  # 分类数必须匹配
chart_data.add_series("销售额", (120, 135, 148, 162))  # 系列数必须匹配

chart.replace_data(chart_data)
```

---

## 规则九：数据来源处理

**来源A：用户直接提供（对话中输入）**
- AI 直接读取用户提供的数据，生成一次性编辑脚本

**来源B：从文件读取（Excel/CSV）**
- 使用 EasyClaw 内置的文件读取技能获取数据
- 获取后传入编辑脚本，流程同来源A

两种来源的数据处理完后，均通过一次性脚本写入 PPTX，不需要通用参数接口。

---

## 规则十：文字长度超出时的处理策略

改完文字后如果内容变长，按以下顺序处理：

1. **优先缩小字号**：缩小 1-2pt，保持布局不变
2. **次选扩大文本框高度**：`shape.height += Inches(0.2)`，不改宽度
3. **最后选择精简内容**：提示用户内容过长，建议精简

禁止：自动换行到相邻 shape 区域、修改其他 shape 的位置来腾空间。

---

## 规则十一：扩展布局时优先分析方向可行性

当内容需要更多空间时，扩展方向不能想当然，必须先分析两个方向的实际可用空间：

| 方向 | 检查项 |
|------|--------|
| 纵向扩展（加高） | 幻灯片底部是否有余量，下方有无其他 shape |
| 横向扩展（加宽） | 左右边界约束，相邻 shape 的位置，固定边界元素 |

**判断流程：**
```
1. 用 inspect.py 列出该页所有 shape 的完整坐标
2. 计算横向可用区域（排除边条、页码等固定元素后的净宽）
3. 计算纵向可用区域（排除顶部标题、底部装饰后的净高）
4. 选择空间更充裕、对其他元素影响更小的方向
5. 确认方案后再执行，不凭直觉猜测
```

**本次教训：** 内容是纵向增加的（新增一行文字），但横向空间更充裕（卡片间距达1.5in），正确方案是加宽卡片让文字在一行内显示，而不是加高。需要两个方向都分析后再决策。

---

## 规则十二：多 shape 重新分布时必须以结构性锚点为中心对齐

当一组 shape（如卡片）需要重新分布宽度或位置时，不能用均匀分布算法，必须先识别与每个 shape 对应的**结构性锚点**（时间线圆圈、图标、标题等），以锚点中心为基准对齐。

**错误做法（均匀分布）：**
```python
# ❌ 4张卡片均匀分布，看似整齐，但与上方圆圈位置脱节
for i in range(4):
    card_left = SAFE_LEFT + i * (CARD_W + GAP)
```

**正确做法（锚点对齐）：**
```python
# ✅ 先读取每个锚点的中心X，再以此为基准计算卡片left
circle_cx = {card_id: (shape.left + shape.width/2) / 914400 for ...}

for card in cards:
    cx = circle_cx[card["bg_id"]]
    card_left = cx - CARD_W / 2
    # 再叠加边界约束（左侧色条、右侧页码）
    card_left = max(SAFE_LEFT, card_left)
    card_left = min(RIGHT_MAX - CARD_W, card_left)
```

**识别锚点的方法：**
- 用 inspect.py 找出与每张卡片视觉关联的 shape（通常在卡片正上方）
- 计算其中心X：`cx = (shape.left + shape.width/2) / 914400`
- 将此 cx 作为卡片中心的目标值

**边界冲突处理：**
- 若锚点靠近边条导致卡片左边超出 SAFE_LEFT → 向右平移，接受轻微偏移
- 若锚点靠近右边导致卡片右边超出 RIGHT_MAX → 向左平移，接受轻微偏移
- 偏移量在输出日志中打印，便于验证

---

## 检查清单（编辑完成后逐项确认）

- [ ] 备份文件已创建
- [ ] 所有修改的 shape 字体属性与原文件一致
- [ ] 无占位符文字残留（如"单击此处添加标题"）
- [ ] 无文字截断（文字未超出文本框边界）
- [ ] 表格行列数与原文件一致
- [ ] 图表系列数与原文件一致
- [ ] 输出文件已用 inspect.py 验证
- [ ] **布局调整时：已识别固定边界元素，调整后的 shape 未超出可用区域**
- [ ] **布局调整时：已分析横纵两个方向的可用空间，选择了最优扩展方向**
- [ ] **多 shape 重新分布时：已以结构性锚点（圆圈/图标/标题）为中心对齐，而非均匀分布**
