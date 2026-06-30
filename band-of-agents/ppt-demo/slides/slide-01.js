const pptxgen = require("pptxgenjs");

const slideConfig = { type: 'cover', index: 1, title: 'IQ Relay + Band Routing' };

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  // 装饰条
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.15,
    fill: { color: theme.primary }
  });

  // 标题
  slide.addText("IQ Relay + Band Routing", {
    x: 0.8, y: 1.8, w: 8.4, h: 1.2,
    fontSize: 44, fontFace: "Arial",
    color: theme.primary, bold: true, align: "left"
  });

  // 副标题
  slide.addText("Enterprise Feedback Routing with Multi-Agent Collaboration", {
    x: 0.8, y: 3.0, w: 8.4, h: 0.8,
    fontSize: 20, fontFace: "Arial",
    color: theme.secondary, align: "left"
  });

  // 标签
  slide.addText("Band of Agents Hackathon 2026", {
    x: 0.8, y: 4.2, w: 4, h: 0.5,
    fontSize: 14, fontFace: "Arial",
    color: theme.accent, align: "left"
  });

  // 页码徽章
  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("1", {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fontSize: 12, fontFace: "Arial",
    color: "FFFFFF", bold: true, align: "center", valign: "middle"
  });

  return slide;
}

if (require.main === module) {
  const pres = new pptxgen();
  pres.layout = 'LAYOUT_16x9';
  const theme = { primary: "1a1a2e", secondary: "16213e", accent: "0f3460", light: "e94560", bg: "f5f5f5" };
  createSlide(pres, theme);
  pres.writeFile({ fileName: "slide-01-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
