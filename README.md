# EA iCUE Widgets

Custom widgets for the Corsair Xeneon Edge, built for iCUE's native widget system as self-contained single-HTML-file apps.

## Widgets

| Widget | Description |
|--------|-------------|
| [Claude Usage](widgets/EAClaudeUsage) | Live Claude Code token and API-equivalent cost meter with 24-hour and 7-day history, per-model breakdown, and active sessions. Fed by a small local companion server. |
| [Home Control](widgets/EAHomeControl) | Touch control for Home Assistant: rooms you tap into, lights, switches, fans, thermostats, covers, locks, media and sensors, updating live. Connects directly to Home Assistant; no companion server. |

## Installation

### Using iCUE's import (recommended)

1. Download the `.icuewidget` file for the widget from [Releases](https://github.com/edwardayoub/EA-ICUE-Widgets/releases), or build it locally (see below).
2. Double-click the file, or use the **+** button in iCUE's widget picker.
3. If the widget has a `server/` folder, run its `StartServer.bat` once. It stays in the system tray.

### From source (Windows)

```
tools/build-release.sh
```

Writes one `.icuewidget` per widget into `dist/`, plus a ZIP of any companion server.

## Development

- `node tools/screenshot.js widgets/EAClaudeUsage/index.html L` renders a widget at any slot size (`S`, `M`, `L`, `XL`, `VS`, `VM`, `VL`, `VXL`). Needs `npm install` once for puppeteer.
- `node tools/generate-manifests.js` regenerates every `manifest.json` from the array inside the script.
- `node tools/generate-icons.js` renders `icon.png` and `icon@2x.png` from each widget's picker SVG.
- `CLAUDE.md` holds the iCUE widget API notes and design rules used when building these widgets.

## Credits

Build tooling and widget conventions started from [QuadraKev/QK-iCUE-Widgets](https://github.com/QuadraKev/QK-iCUE-Widgets) (MIT). The Jost typeface is embedded under the SIL Open Font License.

## License

MIT
