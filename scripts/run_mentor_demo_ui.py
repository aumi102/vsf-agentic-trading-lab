from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.mentor_demo.demo_service import (
    build_demo_summary,
    get_demo_status,
    get_upload_recommendation,
    list_registry_status,
    run_disabled_family_preview,
    run_noop_adapter_preview,
    run_pending_contract_validation,
)


HOST = "127.0.0.1"
DEFAULT_PORT = 8765

API_ROUTES: dict[str, Callable[[], dict[str, Any]]] = {
    "/api/summary": build_demo_summary,
    "/api/status": get_demo_status,
    "/api/upload": get_upload_recommendation,
    "/api/pending-contract": run_pending_contract_validation,
    "/api/registry": list_registry_status,
    "/api/noop-preview": run_noop_adapter_preview,
    "/api/disabled-family": run_disabled_family_preview,
}


def build_dashboard_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VSF Local Mentor Demo UI</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, system-ui, sans-serif; }
    body { margin: 0; background: #07111f; color: #dce8f5; }
    header, main { width: min(1180px, 92vw); margin: 0 auto; }
    header { padding: 38px 0 18px; }
    h1 { margin: 0 0 8px; font-size: clamp(2rem, 5vw, 3.5rem); }
    .talk { color: #8fe3c1; font-weight: 650; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); gap: 16px; padding-bottom: 48px; }
    section { background: #101f32; border: 1px solid #29415d; border-radius: 14px; padding: 18px; box-shadow: 0 12px 28px #02070d66; }
    h2 { margin-top: 0; font-size: 1.08rem; color: #f5c76b; }
    button { border: 0; border-radius: 8px; padding: 9px 13px; background: #42c59a; color: #06130f; font-weight: 700; cursor: pointer; }
    button:hover { background: #74dbb8; }
    pre { min-height: 70px; overflow: auto; padding: 12px; border-radius: 8px; background: #07111f; color: #bcd3e9; white-space: pre-wrap; }
    ul { padding-left: 20px; }
    code { color: #8fe3c1; }
  </style>
</head>
<body>
  <header>
    <h1>VSF Local Mentor Demo UI</h1>
    <p class="talk">This demo shows safety gates, not strategy performance.</p>
    <p class="talk">Real strategy family remains blocked until mentor approval.</p>
  </header>
  <main class="grid">
    <section><h2>1. Current Status</h2><button onclick="loadSection('/api/status','status')">Refresh Status</button><pre id="status">Ready.</pre></section>
    <section><h2>2. Upload Files</h2><pre id="upload">Loading...</pre></section>
    <section><h2>3. Pending Contract Validation</h2><button onclick="loadSection('/api/pending-contract','pending')">Validate Pending Template</button><pre id="pending">Expected: not_ready.</pre></section>
    <section><h2>4. Registry / Enabled Families</h2><button onclick="loadSection('/api/registry','registry')">Show Registry</button><pre id="registry">Only noop is enabled.</pre></section>
    <section><h2>5. Noop Adapter Preview</h2><button onclick="loadSection('/api/noop-preview','noop')">Run Noop Preview</button><pre id="noop">Synthetic adjusted-OHLC interface preview.</pre></section>
    <section><h2>6. Disabled Family Demo</h2><button onclick="loadSection('/api/disabled-family','disabled')">Run Disabled Family Demo</button><pre id="disabled">moving_average remains blocked.</pre></section>
    <section><h2>7. Mentor Decisions Needed</h2><ul><li>First strategy family</li><li>Universe</li><li>Execution price</li><li>Transaction cost and slippage</li><li>Rebalance and risk rule</li></ul></section>
    <section><h2>8. Caveats</h2><pre id="caveats">Research only. No real strategy execution. No production server.</pre></section>
  </main>
  <script>
    async function loadSection(endpoint, target) {
      const output = document.getElementById(target);
      output.textContent = 'Running...';
      try {
        const response = await fetch(endpoint);
        output.textContent = JSON.stringify(await response.json(), null, 2);
      } catch (error) {
        output.textContent = 'Local request failed: ' + error;
      }
    }
    loadSection('/api/status', 'status');
    loadSection('/api/upload', 'upload');
    fetch('/api/summary').then(response => response.json()).then(data => {
      document.getElementById('caveats').textContent = JSON.stringify(data.caveats, null, 2);
    });
  </script>
</body>
</html>
"""


def build_response(path: str) -> tuple[int, str, bytes]:
    if path == "/":
        return 200, "text/html; charset=utf-8", build_dashboard_html().encode("utf-8")
    handler = API_ROUTES.get(path)
    if handler is None:
        payload = {"status": "not_found", "path": path}
        return 404, "application/json; charset=utf-8", _json_bytes(payload)
    return 200, "application/json; charset=utf-8", _json_bytes(handler())


class MentorDemoHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        status, content_type, body = build_response(self.path.split("?", 1)[0])
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[mentor-demo] {format % args}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local-only VSF mentor demo UI.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--once-json", action="store_true")
    args = parser.parse_args(argv)

    if args.once_json:
        print(json.dumps(build_demo_summary(), indent=2, ensure_ascii=False))
        return 0
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    url = f"http://{HOST}:{args.port}"
    server = ThreadingHTTPServer((HOST, args.port), MentorDemoHandler)
    print(f"VSF mentor demo UI: {url}")
    print("Press Ctrl+C to stop the local server.")
    if not args.no_open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping mentor demo UI.")
    finally:
        server.server_close()
    return 0


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
