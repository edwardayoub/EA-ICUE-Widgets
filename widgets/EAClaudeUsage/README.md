# EA Claude Usage - iCUE Dashboard Claude Code Meter

A live usage meter for [Claude Code](https://claude.com/claude-code) on the **Corsair Xeneon Edge**. Shows how many tokens you have burned today, what that would cost at API list prices, a 24-hour and 7-day history, per-model breakdown, and which sessions are active right now.

---

## How It Works

The widget has two parts:

- **`index.html`** - the iCUE widget rendered on the Xeneon Edge
- **`server/ClaudeUsageServer.pyw`** - a tiny companion server that runs on your PC

Claude Code records the token usage of every response in local transcript files under `%USERPROFILE%\.claude\projects`. The server tails those files, de-duplicates the streamed entries, prices each message at Anthropic's published API rates, and serves the totals as JSON on `http://localhost:16330/usage`. The widget polls that endpoint every 5 seconds.

Nothing leaves your machine. No API key, no login. The server only reads the transcript files.

**Cost is "API-equivalent".** If you are on a Claude subscription (Pro / Max) you are not billed per token; the dollar figure tells you what the same usage would cost through the API, which is a handy way to see how much value you are getting and how close you are to the plan's rolling 5-hour window.

---

## What It Shows

| Element | Meaning |
|---------|---------|
| Big number | API-equivalent cost today (or tokens today, switchable in settings) |
| Input / Output / Cache read | Uncached input tokens, output tokens, and cache-read tokens today |
| 5h window | Cost (or tokens) in the last rolling 5 hours, matching Claude's plan-limit window |
| Last 24 hours | Hourly stacked bars: input (blue), cache (amber), output (accent) |
| Last 7 days | Daily stacked bars (L/XL and tall vertical slots) |
| Models today | Per-model share of today's usage (XL and tall vertical slots) |
| Active sessions | Sessions that produced a response in the last 5 minutes, with project name and model |

---

## Requirements

- Corsair iCUE 5.45 or later with a Xeneon Edge
- Windows 10/11 with Python 3.10+ on PATH (`python.org` installer, tick "Add Python to PATH")
- Claude Code installed and used at least once on this PC

Optional: `pip install pystray Pillow` gives the server a tray icon with a Quit item. `StartServer.bat` installs these for you if missing. Without them the server still runs; end it from Task Manager (`pythonw.exe`).

---

## Setup

1. Import `EAClaudeUsage.icuewidget` through the **+** button in iCUE's widget picker.
2. Run `server\StartServer.bat` (found next to the widget files, or in the separate `ClaudeUsageServer.zip` from the release). The first scan of your transcripts takes a few seconds; the widget shows a progress bar meanwhile.
3. Add the widget to a slot. If the widget says **Server offline**, the server is not running or the port does not match.

To start the server automatically at login, put a shortcut to `StartServer.bat` in `shell:startup`.

### Server options

```
pythonw ClaudeUsageServer.pyw --port 16330 --interval 10
python  ClaudeUsageServer.pyw --once          # print the JSON once and exit
python  ClaudeUsageServer.pyw --claude-dir "D:\claude\projects"
```

The server honours `CLAUDE_CONFIG_DIR` if you have relocated Claude Code's config directory.

---

## Settings

**Claude Usage**
- **Server Port** - must match the `--port` the server is started with (default `16330`)
- **Main Number** - Cost or Tokens as the hero figure
- **Show Active Sessions** - hide the session list if you prefer a cleaner layout
- **Custom Title** - optional label centred at the top

**Widget Personalization**
- Background Image, Glass Blur, Text Color, Accent Color (output/cost), Input Color, Cache Color, Background Color, Transparency

---

## Pricing Table

Rates live at the top of `ClaudeUsageServer.pyw` in `PRICING` (USD per million tokens: input, output, 5-minute cache write, 1-hour cache write, cache read). Update them there when Anthropic changes list prices. Models without an entry (for example third-party models routed through a proxy) count toward token totals but not cost, and are listed under `unknownModels` in the JSON.

---

## Privacy

The server binds to `127.0.0.1` only and exposes aggregate numbers plus project folder names of active sessions. It never reads or serves message content.
