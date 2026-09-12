#!/usr/bin/env node
// tools/generate-icons.js
// Generates icon.png (256x256) and icon@2x.png (512x512) for each EA widget.
// Run from repo root: node tools/generate-icons.js
// Requires: puppeteer (already installed)

const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const WIDGETS_DIR = path.join(__dirname, '..', 'widgets');
const SIZES = [
  { size: 256, filename: 'icon.png' },
  { size: 512, filename: 'icon@2x.png' },
];

// Brand palette for PNG listing icons.
// SVG picker icons stay monochromatic white per Marketplace rules.
const BG_COLOR    = '#4f5458';
const PRIMARY     = '#f84bff'; // magenta
const SECONDARY   = '#009bff'; // blue
const TERTIARY    = '#ffae30'; // amber

// Per-widget color — PRIMARY for all by default.
// Widgets with multi-color treatment are handled in colorize().
const ICON_COLOR = PRIMARY;

const folders = [
  'EAClaudeUsage',
];

// Colorize SVG for PNG rendering. Most widgets get a flat primary color.
// Special widgets get multi-color treatment.
function colorize(folder, svg) {
  if (folder === 'EAClaudeUsage') {
    // Brand palette on the three usage bars; asterisk stays primary
    return svg
      .replace(/<rect x="1" y="10" width="3" height="5" fill="#FFFFFF"\/>/, '<rect x="1" y="10" width="3" height="5" fill="#009bff"/>')
      .replace(/<rect x="6" y="6" width="3" height="9" fill="#FFFFFF"\/>/, '<rect x="6" y="6" width="3" height="9" fill="#f84bff"/>')
      .replace(/<rect x="11" y="2" width="3" height="13" fill="#FFFFFF" opacity="0.5"\/>/, '<rect x="11" y="2" width="3" height="13" fill="#ffae30"/>')
      .replace(/stroke="#FFFFFF"/, `stroke="${PRIMARY}"`);
  }

  // Default: flat primary color
  return svg
    .replace(/fill="#FFFFFF"/gi, `fill="${ICON_COLOR}"`)
    .replace(/fill="#FFF"/gi, `fill="${ICON_COLOR}"`)
    .replace(/stroke="#FFFFFF"/gi, `stroke="${ICON_COLOR}"`)
    .replace(/stroke="#FFF"/gi, `stroke="${ICON_COLOR}"`);
}

async function generateIcons() {
  const browser = await puppeteer.launch({ args: ['--no-sandbox'] });

  for (const folder of folders) {
    const widgetDir = path.join(WIDGETS_DIR, folder);
    const resourcesDir = path.join(widgetDir, 'resources');

    if (!fs.existsSync(resourcesDir)) {
      console.warn(`  No resources/ in ${folder}, skipping`);
      continue;
    }

    const svgFile = fs.readdirSync(resourcesDir).sort().find(f => f.endsWith('.svg')); // expects exactly one SVG per resources/
    if (!svgFile) {
      console.warn(`  No SVG in ${folder}/resources/, skipping`);
      continue;
    }

    const svgPath = path.join(resourcesDir, svgFile);
    let svgContent = fs.readFileSync(svgPath, 'utf8');

    // Ensure SVG scales properly: add viewBox from width/height if missing,
    // then strip width/height so CSS controls dimensions
    const wMatch = svgContent.match(/\bwidth="(\d+(?:\.\d+)?)"/);
    const hMatch = svgContent.match(/\bheight="(\d+(?:\.\d+)?)"/);
    if (!/viewBox/.test(svgContent) && wMatch && hMatch) {
      svgContent = svgContent.replace(/<svg/, `<svg viewBox="0 0 ${wMatch[1]} ${hMatch[1]}"`);
    }
    svgContent = svgContent.replace(/(<svg[^>]*?)\s*width="[^"]*"/, '$1');
    svgContent = svgContent.replace(/(<svg[^>]*?)\s*height="[^"]*"/, '$1');

    let colorizedSvg = colorize(folder, svgContent);

    for (const { size, filename } of SIZES) {
      const page = await browser.newPage();
      await page.setViewport({ width: size, height: size, deviceScaleFactor: 1 });

      // Embed colorized SVG on brand background with padding
      const html = `<!DOCTYPE html>
<html>
<head>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body {
    width: ${size}px;
    height: ${size}px;
    background: ${BG_COLOR};
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
  }
  svg {
    width: 70%;
    height: 70%;
  }
</style>
</head>
<body>
  ${colorizedSvg}
</body>
</html>`;

      await page.setContent(html, { waitUntil: 'networkidle0' });

      const outPath = path.join(widgetDir, filename);
      await page.screenshot({ path: outPath, type: 'png' });
      await page.close();

      console.log(`  ${folder}/${filename}`);
    }

    console.log(`✓ ${folder}`);
  }

  await browser.close();
  console.log('\nDone.');
}

generateIcons().catch(err => {
  console.error('Error:', err);
  process.exit(1);
});
