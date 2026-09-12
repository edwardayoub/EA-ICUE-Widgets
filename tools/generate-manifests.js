#!/usr/bin/env node
// tools/generate-manifests.js
// Generates manifest.json for each EA widget for Marketplace submission.
// Run from repo root: node tools/generate-manifests.js

const fs = require('fs');
const path = require('path');

const AUTHOR = 'Edward Ayoub';
const MIN_FRAMEWORK_VERSION = '1.0.0';
const MIN_APP_VERSION = '5.45';
const VERSION = '1.0.0';
// Windows-only: the official spec and icuewidget CLI (≥0.2.3, still in 0.4.41)
// accept only 'windows'; iCUE 5.x import also rejects 'macos'.
const OS = [{ platform: 'windows' }];

const widgets = [
  {
    folder: 'EAClaudeUsage',
    id: 'com.edwardayoub.claudeusage',
    name: 'Claude Usage',
    description: 'Live Claude Code token usage and API-equivalent cost meter, fed by a local companion server.',
    devices: [{ type: 'dashboard_lcd' }],
    interactive: false,
    version: '1.0.0',
  },
];

const widgetsDir = path.join(__dirname, '..', 'widgets');

for (const w of widgets) {
  const manifest = {
    author: AUTHOR,
    id: w.id,
    name: w.name,
    description: w.description,
    version: w.version || VERSION,
    preview_icon: w.previewIcon || 'icon.png',
    min_framework_version: MIN_FRAMEWORK_VERSION,
    os: w.os || OS,
    supported_devices: w.devices.map(d => {
      const entry = { type: d.type };
      if (d.features) entry.features = d.features;
      return entry;
    }),
    min_app_version: MIN_APP_VERSION,
  };
  if (w.interactive) manifest.interactive = true;
  if (w.modules) manifest.modules = w.modules;

  const outPath = path.join(widgetsDir, w.folder, 'manifest.json');
  try {
    fs.writeFileSync(outPath, JSON.stringify(manifest, null, 2) + '\n');
    console.log(`Written: ${outPath}`);
  } catch (err) {
    console.error(`ERROR: could not write ${outPath}: ${err.message}`);
    process.exitCode = 1;
  }
}
console.log(`\nDone. ${widgets.length} manifest.json files created.`);

// After the main loop, check for uncovered widget folders
const INTENTIONALLY_OMITTED = new Set([]); // (EAPumpVisualizer is version-managed here even though it isn't Marketplace-bound)
const actualFolders = fs.readdirSync(widgetsDir).filter(f =>
  fs.statSync(path.join(widgetsDir, f)).isDirectory() && f.startsWith('EA')
);
const coveredFolders = new Set(widgets.map(w => w.folder));
const skipped = actualFolders.filter(f => !coveredFolders.has(f) && !INTENTIONALLY_OMITTED.has(f));
if (skipped.length > 0) {
  console.warn(`\nWARNING: ${skipped.length} widget folder(s) have no manifest entry and were skipped:`);
  skipped.forEach(f => console.warn(`  - ${f}`));
}
