const pptxgen = require("pptxgenjs");

const slideConfig = { type: 'content', index: 2, title: 'How It Works' };

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  // 标题
  slide.addText("How It Works", {
    x: 0.5, y: 0.3, w: 9, h: 0.8,
    fontSize: 32, fontFace: "Arial",
    color: theme.primary, bold: true, align: "left"
  });

  // 分隔线
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.1, w: 9, h: 0.03,
    fill: { color: theme.accent }
  });

  // Step 1
  slide.addShape(pres.shapes.OVAL, {
    x: 0.8, y: 1.5, w: 0.5, h: 0.5,
    fill: { color: theme.primary }
  });
  slide.addText("1", {
    x: 0.8, y: 1.5, w: 0.5, h: 0.5,
    fontSize: 18, fontFace: "Arial",
    color: "FFFFFF", bold: true, align: "center", valign: "middle"
  });
  slide.addText("Customer Feedback", {
    x: 1.5, y: 1.5, w: 7.5, h: 0.4,
    fontSize: 18, fontFace: "Arial",
    color: theme.primary, bold: true, align: "left"
  });
  slide.addText("Customer sends feedback in Lark group with product model", {
    x: 1.5, y: 1.9, w: 7.5, h: 0.35,
    fontSize: 14, fontFace: "Arial",
    color: theme.secondary, align: "left"
  });

  // Step 2
  slide.addShape(pres.shapes.OVAL, {
    x: 0.8, y: 2.6, w: 0.5, h: 0.5,
    fill: { color: theme.accent }
  });
  slide.addText("2", {
    x: 0.8, y: 2.6, w: 0.5, h: 0.5,
    fontSize: 18, fontFace: "Arial",
    color: "FFFFFF", bold: true, align: "center", valign: "middle"
  });
  slide.addText("Routing Agent Diagnoses", {
    x: 1.5, y: 2.6, w: 7.5, h: 0.4,
    fontSize: 18, fontFace: "Arial",
    color: theme.primary, bold: true, align: "left"
  });
  slide.addText("AI searches Bitable history, diagnoses issue type, determines entry stage", {
    x: 1.5, y: 3.0, w: 7.5, h: 0.35,
    fontSize: 14, fontFace: "Arial",
    color: theme.secondary, align: "left"
  });

  // Step 3
  slide.addShape(pres.shapes.OVAL, {
    x: 0.8, y: 3.7, w: 0.5, h: 0.5,
    fill: { color: theme.light }
  });
  slide.addText("3", {
    x: 0.8, y: 3.7, w: 0.5, h: 0.5,
    fontSize: 18, fontFace: "Arial",
    color: "FFFFFF", bold: true, align: "center", valign: "middle"
  });
  slide.addText("Route to Right Person", {
    x: 1.5, y: 3.7, w: 7.5, h: 0.4,
    fontSize: 18, fontFace: "Arial",
    color: theme.primary, bold: true, align: "left"
  });
  slide.addText("Lark card sent to the person who built this requirement", {
    x: 1.5, y: 4.1, w: 7.5, h: 0.35,
    fontSize: 14, fontFace: "Arial",
    color: theme.secondary, align: "left"
  });

  // 页码徽章
  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("2", {
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
  pres.writeFile({ fileName: "slide-02-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
