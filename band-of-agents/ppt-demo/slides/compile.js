const pptxgen = require('pptxgenjs');
const pres = new pptxgen();
pres.layout = 'LAYOUT_16x9';

const theme = {
  primary: "1a1a2e",
  secondary: "16213e",
  accent: "0f3460",
  light: "e94560",
  bg: "f5f5f5"
};

for (let i = 1; i <= 2; i++) {
  const num = String(i).padStart(2, '0');
  require(`./slide-${num}.js`).createSlide(pres, theme);
}

pres.writeFile({ fileName: './output/demo.pptx' }).then(() => {
  console.log('✅ PPT generated: output/demo.pptx');
});
