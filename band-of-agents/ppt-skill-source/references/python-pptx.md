# python-pptx.md — API 参考

场景A（编辑现有PPTX）常用 API 速查。

---

## 基础操作

```python
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

# 打开文件
prs = Presentation("file.pptx")

# 基本属性
len(prs.slides)          # 总页数
prs.slide_width          # 宽度（EMU）
prs.slide_height         # 高度（EMU）

# 保存（推荐使用 safe_save，防止文件被 PowerPoint 占用时报错）
from safe_save import safe_save_pptx
safe_save_pptx(prs, "output.pptx")           # 被占用时报错提示
safe_save_pptx(prs, "output.pptx", auto_rename=True)  # 被占用时自动改名

# 直接保存（不推荐，被占用时抛出难以理解的 PermissionError）
# prs.save("output.pptx")
```

---

## 遍历结构

```python
# 遍历所有页
for i, slide in enumerate(prs.slides):
    print(f"第 {i+1} 页，{len(slide.shapes)} 个 shape")

# 遍历某页的所有 shape
slide = prs.slides[0]  # 第1页（0-based）
for shape in slide.shapes:
    print(shape.name, shape.shape_type)

# 判断 shape 类型
shape.has_text_frame   # 是否有文本
shape.has_table        # 是否是表格
shape.has_chart        # 是否是图表
shape.is_placeholder   # 是否是占位符
```

---

## 文本操作

```python
# 读取文本
shape.text_frame.text                          # 全部文字（不含格式）
shape.text_frame.paragraphs[0].text            # 第1段文字
shape.text_frame.paragraphs[0].runs[0].text    # 第1段第1个run

# 修改文字（保留格式）
run = shape.text_frame.paragraphs[0].runs[0]
run.text = "新内容"

# 字体属性读写
run.font.size              # 字号（EMU，除以12700得pt）
run.font.size = Pt(14)     # 设置字号
run.font.name              # 字体名称
run.font.name = "微软雅黑"
run.font.bold              # 是否加粗
run.font.bold = True
run.font.italic            # 是否斜体
run.font.color.rgb         # 颜色（RGBColor对象）
run.font.color.rgb = RGBColor(0xFF, 0x00, 0x00)  # 红色

# 段落对齐
from pptx.enum.text import PP_ALIGN
para.alignment = PP_ALIGN.LEFT    # 左对齐
para.alignment = PP_ALIGN.CENTER  # 居中
para.alignment = PP_ALIGN.RIGHT   # 右对齐

# 文本框自动换行
shape.text_frame.word_wrap = True
```

---

## 位置与尺寸

```python
from pptx.util import Inches

# 读取位置（返回 EMU，转换为英寸）
left   = shape.left / 914400    # 英寸
top    = shape.top / 914400
width  = shape.width / 914400
height = shape.height / 914400

# 设置位置
shape.left   = Inches(1.0)
shape.top    = Inches(2.0)
shape.width  = Inches(8.0)
shape.height = Inches(1.5)
```

---

## 表格操作

```python
table = shape.table

# 基本属性
len(table.rows)        # 行数
len(table.columns)     # 列数

# 读取单元格
cell = table.rows[0].cells[0]   # 第1行第1列
cell.text                        # 单元格全部文字

# 修改单元格（保留格式）
for para in cell.text_frame.paragraphs:
    for run in para.runs:
        run.text = "新数据"
        break
    break

# 单元格无 run 时新增
para = cell.text_frame.paragraphs[0]
run = para.add_run()
run.text = "新数据"

# 单元格背景色
from pptx.dml.color import RGBColor
cell.fill.solid()
cell.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0x00)  # 黄色背景

# 行高 / 列宽
table.rows[0].height = Inches(0.5)
table.columns[0].width = Inches(2.0)
```

---

## 图表操作

```python
from pptx.chart.data import ChartData, XyChartData

chart = shape.chart

# 读取图表信息
str(chart.chart_type)      # 图表类型
len(chart.series)          # 系列数量
chart.has_title            # 是否有标题
chart.chart_title.text_frame.text   # 标题文字

# 读取系列数据
for series in chart.series:
    print(series.name)
    print(list(series.values))

# 替换数据（分类数和系列数必须与原图表一致）
chart_data = ChartData()
chart_data.categories = ["Q1", "Q2", "Q3", "Q4"]
chart_data.add_series("系列1", (100, 120, 140, 160))
chart_data.add_series("系列2", (80,  95, 110, 130))
chart.replace_data(chart_data)

# 修改图表标题
chart.chart_title.text_frame.text = "新标题"
```

---

## 图片操作

```python
from pptx.util import Inches

# 添加图片到页面
slide.shapes.add_picture(
    "image.png",
    left=Inches(1), top=Inches(1),
    width=Inches(4), height=Inches(3)
)

# 替换现有图片（需要 shape 是 PICTURE 类型）
# python-pptx 不支持直接替换，需通过 XML 操作
# 推荐：删除旧图片 shape，添加新图片到相同位置
```

---

## 幻灯片操作

```python
# 删除幻灯片（通过 XML 操作）
from pptx.oxml.ns import qn

def delete_slide(prs, slide_index):
    xml_slides = prs.slides._sldIdLst
    slide = prs.slides[slide_index]
    rId = prs.slides._sldIdLst[slide_index].get('r:id')
    prs.part.drop_rel(rId)
    del xml_slides[slide_index]

# 复制幻灯片（同文件内）
import copy
from pptx.oxml.ns import qn

def duplicate_slide(prs, slide_index):
    template = prs.slides[slide_index]
    blank_layout = prs.slide_layouts[6]  # 空白布局
    new_slide = prs.slides.add_slide(blank_layout)
    new_slide.shapes._spTree.clear()
    for shape in template.shapes:
        sp = copy.deepcopy(shape._element)
        new_slide.shapes._spTree.append(sp)
    return new_slide
```

---

## 占位符操作

```python
# 列出所有占位符
for ph in slide.placeholders:
    print(ph.placeholder_format.idx, ph.name, ph.text)

# 通过 idx 访问占位符（比 shape 索引更稳定）
title_ph = slide.placeholders[0]   # idx=0 通常是标题
body_ph  = slide.placeholders[1]   # idx=1 通常是正文

# 修改占位符文字
title_ph.text = "新标题"  # 注意：这会清除格式，用 run 方式更安全
```

---

## 颜色常量速查

```python
from pptx.dml.color import RGBColor

# 常用颜色
RGBColor(0x00, 0x00, 0x00)  # 黑色
RGBColor(0xFF, 0xFF, 0xFF)  # 白色
RGBColor(0xFF, 0x00, 0x00)  # 红色
RGBColor(0x00, 0x70, 0xC0)  # 商务蓝
RGBColor(0x70, 0xAD, 0x47)  # 绿色
RGBColor(0xFF, 0xC0, 0x00)  # 金黄色

# 从十六进制字符串创建
RGBColor.from_string("FF0000")   # 红色（不带#）
```

---

## 单位换算

| 单位 | 换算 |
|------|------|
| 1 英寸 | 914400 EMU |
| 1 厘米 | 360000 EMU |
| 1 磅(pt) | 12700 EMU |
| Inches(1.0) | 914400 |
| Pt(12) | 152400 |
