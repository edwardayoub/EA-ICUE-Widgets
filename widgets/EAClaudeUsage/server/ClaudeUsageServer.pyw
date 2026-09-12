"""
Claude Usage Companion Server for the EA Claude Usage iCUE widget
=================================================================
Reads the transcript files Claude Code writes locally
(~/.claude/projects/**/*.jsonl), de-duplicates the per-message token usage
they record, prices it at Anthropic's published API rates, and serves the
aggregated numbers as JSON over a local HTTP endpoint that the widget polls.

Nothing leaves your PC. No API key is needed. The server only ever reads
the transcript files; it never modifies them.

Dependencies:
    None (Python 3.10+ standard library only).
    Optional: pip install pystray Pillow   -> adds a system-tray icon with Quit.

Usage:
    pythonw ClaudeUsageServer.pyw [--port 16330] [--claude-dir PATH] [--interval 10]
    python  ClaudeUsageServer.pyw --once        # print the JSON once and exit

Endpoints:
    GET /usage   -> JSON usage summary (see build_summary)
    GET /health  -> {"ok": true, "ready": bool}
"""

import argparse
import datetime as dt
import json
import logging
import math
import os
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ClaudeUsage")

DEFAULT_PORT = 16330
SCAN_INTERVAL = 10          # seconds between incremental rescans
ACTIVE_WINDOW = 5 * 60      # a session counts as "active" if it wrote in the last 5 min
ROLLING_WINDOW = 5 * 3600   # Claude plan limits are enforced on a rolling 5-hour window

# ---------------------------------------------------------------------------
# Pricing (USD per million tokens) - Anthropic first-party API list prices.
# Columns: input, output, cache write (5 min), cache write (1 h), cache read.
# Cache writes cost 1.25x input (5 min) or 2x input (1 h); reads cost 0.1x input,
# except Fable 5.1 / Mythos 5.1 whose cache reads are $0.25/MTok.
# Longest prefix wins, so 'claude-opus-4-8' is matched before 'claude-opus-4'.
# ---------------------------------------------------------------------------
PRICING = {
    "claude-fable-5-1":  (10.0, 50.0, 12.5, 20.0, 0.25),
    "claude-mythos-5-1": (10.0, 50.0, 12.5, 20.0, 0.25),
    "claude-fable-5":    (10.0, 50.0, 12.5, 20.0, 1.0),
    "claude-mythos-5":   (10.0, 50.0, 12.5, 20.0, 1.0),
    "claude-opus-5":     (5.0, 25.0, 6.25, 10.0, 0.5),
    "claude-opus-4-8":   (5.0, 25.0, 6.25, 10.0, 0.5),
    "claude-opus-4-7":   (5.0, 25.0, 6.25, 10.0, 0.5),
    "claude-opus-4-6":   (5.0, 25.0, 6.25, 10.0, 0.5),
    "claude-opus-4-5":   (5.0, 25.0, 6.25, 10.0, 0.5),
    "claude-opus-4-1":   (15.0, 75.0, 18.75, 30.0, 1.5),
    "claude-opus-4":     (15.0, 75.0, 18.75, 30.0, 1.5),
    "claude-sonnet-5":   (2.0, 10.0, 2.5, 4.0, 0.2),
    "claude-sonnet-4-6": (3.0, 15.0, 3.75, 6.0, 0.3),
    "claude-sonnet-4-5": (3.0, 15.0, 3.75, 6.0, 0.3),
    "claude-sonnet-4":   (3.0, 15.0, 3.75, 6.0, 0.3),
    "claude-sonnet-3-7": (3.0, 15.0, 3.75, 6.0, 0.3),
    "claude-haiku-4-5":  (1.0, 5.0, 1.25, 2.0, 0.1),
    "claude-haiku-3-5":  (0.8, 4.0, 1.0, 1.6, 0.08),
}
_PRICING_KEYS = sorted(PRICING, key=len, reverse=True)
_price_cache = {}


def price_for(model):
    """Return the pricing tuple for a model id, or None if unknown."""
    if model in _price_cache:
        return _price_cache[model]
    found = None
    for key in _PRICING_KEYS:
        if model.startswith(key):
            found = PRICING[key]
            break
    _price_cache[model] = found
    return found


def short_model(model):
    """'claude-opus-4-8-20250805' -> 'Opus 4.8'"""
    name = model
    if name.startswith("claude-"):
        name = name[7:]
    parts = name.split("-")
    family = parts[0].capitalize() if parts else name
    digits = [p for p in parts[1:] if p.isdigit() and len(p) <= 2]
    return (family + " " + ".".join(digits)).strip()


# ---------------------------------------------------------------------------
# Transcript scanning
# ---------------------------------------------------------------------------
class Record:
    __slots__ = ("ts", "model", "inp", "out", "cw5", "cw1", "cr",
                 "cost_in", "cost_out", "cost_cache", "session", "project", "priced")

    def __init__(self, ts, model, usage, session, project):
        self.ts = ts
        self.model = model
        self.session = session
        self.project = project
        self.inp = int(usage.get("input_tokens") or 0)
        self.out = int(usage.get("output_tokens") or 0)
        self.cr = int(usage.get("cache_read_input_tokens") or 0)
        cw_total = int(usage.get("cache_creation_input_tokens") or 0)
        cc = usage.get("cache_creation") or {}
        self.cw1 = int(cc.get("ephemeral_1h_input_tokens") or 0)
        self.cw5 = int(cc.get("ephemeral_5m_input_tokens") or 0)
        if self.cw1 + self.cw5 == 0:
            self.cw5 = cw_total  # older transcripts have no breakdown; assume 5 min
        p = price_for(model)
        self.priced = p is not None
        if p:
            self.cost_in = self.inp * p[0] / 1e6
            self.cost_out = self.out * p[1] / 1e6
            self.cost_cache = (self.cw5 * p[2] + self.cw1 * p[3] + self.cr * p[4]) / 1e6
        else:
            self.cost_in = self.cost_out = self.cost_cache = 0.0

    @property
    def tokens(self):
        return self.inp + self.out + self.cw5 + self.cw1 + self.cr

    @property
    def cost(self):
        return self.cost_in + self.cost_out + self.cost_cache


def parse_ts(value):
    """ISO-8601 'Z' timestamp -> epoch seconds (float), or None."""
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return dt.datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def project_name(cwd):
    if not cwd:
        return "?"
    cwd = cwd.replace("\\", "/").rstrip("/")
    name = cwd.rsplit("/", 1)[-1]
    return name or cwd


class FileState:
    __slots__ = ("offset", "size", "mtime", "partial", "records", "seen")

    def __init__(self):
        self.offset = 0
        self.size = -1
        self.mtime = -1
        self.partial = b""
        self.records = []
        self.seen = set()


class TranscriptStore:
    """Incrementally tails every transcript under the Claude projects dir."""

    def __init__(self, projects_dir):
        self.projects_dir = projects_dir
        self.files = {}
        self.lock = threading.Lock()
        self.ready = False
        self.progress = 0.0
        self.last_scan = 0.0
        self.scan_error = None

    # -- discovery ---------------------------------------------------------
    def _walk(self):
        for root, _dirs, names in os.walk(self.projects_dir):
            for n in names:
                if n.endswith(".jsonl"):
                    yield os.path.join(root, n)

    # -- ingest ------------------------------------------------------------
    def _ingest_line(self, state, raw):
        # Fast reject: only assistant turns carry usage. Avoid json.loads on
        # multi-megabyte tool_result lines.
        if b'"assistant"' not in raw or b'"usage"' not in raw:
            return
        try:
            d = json.loads(raw)
        except ValueError:
            return
        if d.get("type") != "assistant":
            return
        msg = d.get("message") or {}
        usage = msg.get("usage")
        if not usage:
            return
        model = msg.get("model") or ""
        if not model or model.startswith("<"):
            return  # synthetic / local messages
        mid = msg.get("id") or d.get("requestId") or d.get("uuid")
        if mid in state.seen:
            return  # streamed content blocks repeat the same usage payload
        state.seen.add(mid)
        ts = parse_ts(d.get("timestamp"))
        if ts is None:
            return
        state.records.append(Record(ts, model, usage,
                                    d.get("sessionId") or "", project_name(d.get("cwd"))))

    def _read_file(self, path, state):
        with open(path, "rb") as fh:
            fh.seek(state.offset)
            data = state.partial + fh.read()
            state.offset = fh.tell()
        lines = data.split(b"\n")
        state.partial = lines.pop()  # possibly incomplete trailing line
        for line in lines:
            if line:
                self._ingest_line(state, line)

    def scan(self):
        paths = list(self._walk())
        total = len(paths) or 1
        current = set(paths)
        with self.lock:
            for gone in [p for p in self.files if p not in current]:
                del self.files[gone]
        for i, path in enumerate(paths):
            try:
                st = os.stat(path)
            except OSError:
                continue
            state = self.files.get(path)
            if state is None:
                state = FileState()
                with self.lock:
                    self.files[path] = state
            if st.st_size == state.size and st.st_mtime == state.mtime:
                continue
            if st.st_size < state.offset:
                # truncated / rewritten: start over for this file
                fresh = FileState()
                with self.lock:
                    self.files[path] = fresh
                state = fresh
            try:
                self._read_file(path, state)
            except OSError as e:
                log.warning("read failed %s: %s", path, e)
                continue
            state.size, state.mtime = st.st_size, st.st_mtime
            if not self.ready:
                self.progress = (i + 1) / total
        self.last_scan = time.time()
        self.ready = True
        self.progress = 1.0

    def all_records(self):
        with self.lock:
            out = []
            for s in self.files.values():
                out.extend(s.records)
            return out


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def _bucket():
    return {"cost": 0.0, "costIn": 0.0, "costOut": 0.0, "costCache": 0.0,
            "tokens": 0, "input": 0, "output": 0, "cacheWrite": 0, "cacheRead": 0,
            "messages": 0}


def _add(b, r):
    b["cost"] += r.cost
    b["costIn"] += r.cost_in
    b["costOut"] += r.cost_out
    b["costCache"] += r.cost_cache
    b["tokens"] += r.tokens
    b["input"] += r.inp
    b["output"] += r.out
    b["cacheWrite"] += r.cw5 + r.cw1
    b["cacheRead"] += r.cr
    b["messages"] += 1


def _round(b):
    for k in ("cost", "costIn", "costOut", "costCache"):
        b[k] = round(b[k], 4)
    return b


def build_summary(store, now=None):
    now = now or time.time()
    local_now = dt.datetime.fromtimestamp(now)
    midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    month_start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()
    hour_start = local_now.replace(minute=0, second=0, microsecond=0).timestamp()

    today, window, month, all_time = _bucket(), _bucket(), _bucket(), _bucket()
    hours = [_bucket() for _ in range(24)]        # index 23 = current hour
    days = [_bucket() for _ in range(7)]          # index 6 = today
    day_starts = []
    for i in range(6, -1, -1):
        d = (local_now - dt.timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_starts.append(d)
    day_bounds = [(d.timestamp(), (d + dt.timedelta(days=1)).timestamp()) for d in day_starts]
    models_today = {}
    sessions = {}
    today_sessions = set()
    unknown = set()
    last_activity = 0.0

    for r in store.all_records():
        _add(all_time, r)
        if not r.priced:
            unknown.add(r.model)
        if r.ts > last_activity:
            last_activity = r.ts
        if r.ts >= month_start:
            _add(month, r)
        if r.ts >= midnight:
            _add(today, r)
            today_sessions.add(r.session)
            m = models_today.setdefault(r.model, _bucket())
            _add(m, r)
        if r.ts >= now - ROLLING_WINDOW:
            _add(window, r)
        if r.ts >= hour_start:
            _add(hours[23], r)
        else:
            h = int((hour_start - r.ts) // 3600)  # 0 = previous hour
            if h < 23:
                _add(hours[22 - h], r)
        for i, (start, end) in enumerate(day_bounds):
            if start <= r.ts < end:
                _add(days[i], r)
                break
        s = sessions.get(r.session)
        if s is None or r.ts > s["lastTs"]:
            sessions[r.session] = {"lastTs": r.ts, "project": r.project, "model": r.model}

    active = []
    for sid, s in sessions.items():
        if s["lastTs"] >= now - ACTIVE_WINDOW:
            active.append({
                "id": sid[:8],
                "project": s["project"],
                "model": short_model(s["model"]),
                "lastActivity": round(s["lastTs"]),
                "agoSec": int(now - s["lastTs"]),
            })
    active.sort(key=lambda a: a["agoSec"])

    model_rows = []
    for model, b in models_today.items():
        model_rows.append({"model": model, "name": short_model(model),
                           "priced": price_for(model) is not None, **_round(b)})
    model_rows.sort(key=lambda m: (-m["cost"], -m["tokens"]))

    today["sessions"] = len(today_sessions)

    return {
        "ready": store.ready,
        "progress": round(store.progress, 3),
        "serverTime": round(now),
        "lastScan": round(store.last_scan),
        "lastActivity": round(last_activity),
        "activeCount": len(active),
        "activeSessions": active[:8],
        "today": _round(today),
        "window5h": _round(window),
        "month": _round(month),
        "allTime": _round(all_time),
        "hours24": [_round(h) for h in hours],
        "days7": [{"date": ds.strftime("%Y-%m-%d"), "dow": ds.strftime("%a"), **_round(b)}
                  for ds, b in zip(day_starts, days)],
        "models": model_rows[:6],
        "unknownModels": sorted(unknown),
        "pricing": "Anthropic API list prices (USD); cache writes 1.25x/2x input, reads 0.1x",
    }


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
class UsageHandler(BaseHTTPRequestHandler):
    store = None
    _cache = {"t": 0.0, "body": b""}
    _cache_lock = threading.Lock()

    def log_message(self, fmt, *args):  # quiet
        pass

    def _send(self, status, body, ctype="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/health":
            body = json.dumps({"ok": True, "ready": self.store.ready}).encode()
            return self._send(HTTPStatus.OK, body)
        if path in ("/", "/usage"):
            now = time.time()
            with self._cache_lock:
                if now - self._cache["t"] > 2.0 or not self._cache["body"]:
                    self._cache["body"] = json.dumps(build_summary(self.store, now)).encode()
                    self._cache["t"] = now
                body = self._cache["body"]
            return self._send(HTTPStatus.OK, body)
        self._send(HTTPStatus.NOT_FOUND, b'{"error":"not found"}')


def scan_loop(store, interval, stop_event):
    while not stop_event.is_set():
        try:
            t0 = time.time()
            store.scan()
            log.debug("scan took %.2fs", time.time() - t0)
        except Exception as e:  # keep serving stale data rather than dying
            store.scan_error = str(e)
            log.exception("scan failed")
        stop_event.wait(interval)


# ---------------------------------------------------------------------------
# Optional tray icon
# ---------------------------------------------------------------------------
def _tray_image():
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Claude-style asterisk: 4 spokes plus a hub
    c, r, w = 32, 26, 9
    for angle in (0, 45, 90, 135):
        a = math.radians(angle)
        dx, dy = math.cos(a) * r, math.sin(a) * r
        d.line([(c - dx, c - dy), (c + dx, c + dy)], fill=(217, 119, 87, 255), width=w)
    d.ellipse([c - 7, c - 7, c + 7, c + 7], fill=(217, 119, 87, 255))
    return img


def run_with_tray(httpd, port):
    try:
        import pystray
        img = _tray_image()
    except Exception:
        return False

    def on_quit(icon, _item):
        threading.Thread(target=httpd.shutdown, daemon=True).start()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(f"Claude Usage Server - port {port}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    )
    icon = pystray.Icon("ClaudeUsageServer", img, "Claude Usage Server", menu)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    icon.run()  # blocks on the main thread (required on Windows)
    return True


# ---------------------------------------------------------------------------
def default_projects_dir():
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base, "projects")


def main():
    parser = argparse.ArgumentParser(description="Claude Usage companion server for iCUE widgets")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"HTTP port (default {DEFAULT_PORT})")
    parser.add_argument("--claude-dir", default=None,
                        help="Claude Code projects directory (default: ~/.claude/projects)")
    parser.add_argument("--interval", type=float, default=SCAN_INTERVAL,
                        help=f"seconds between rescans (default {SCAN_INTERVAL})")
    parser.add_argument("--once", action="store_true", help="scan once, print JSON, exit")
    parser.add_argument("--no-tray", action="store_true", help="never show a tray icon")
    args = parser.parse_args()

    projects_dir = args.claude_dir or default_projects_dir()
    if not os.path.isdir(projects_dir):
        log.error("Claude projects directory not found: %s", projects_dir)
        if args.once:
            sys.exit(1)
    store = TranscriptStore(projects_dir)

    if args.once:
        store.scan()
        print(json.dumps(build_summary(store), indent=1))
        return

    stop_event = threading.Event()
    threading.Thread(target=scan_loop, args=(store, args.interval, stop_event), daemon=True).start()

    UsageHandler.store = store
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), UsageHandler)
    log.info("Serving http://localhost:%d/usage  (transcripts: %s)", args.port, projects_dir)
    try:
        if args.no_tray or not run_with_tray(httpd, args.port):
            httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        httpd.server_close()


if __name__ == "__main__":
    main()
