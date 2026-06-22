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
    get_decision_example,
    get_decision_field_schema,
    get_decision_template,
    get_demo_readiness,
    get_demo_script,
    get_demo_status,
    get_upload_recommendation,
    list_registry_status,
    run_disabled_family_preview,
    run_noop_adapter_preview,
    run_pending_contract_validation,
)
from trading_agent.mentor_demo.decision_capture import get_demo_talk_track


HOST = "127.0.0.1"
DEFAULT_PORT = 8765

API_ROUTES: dict[str, Callable[[], dict[str, Any]]] = {
    "/api/health": lambda: {"status": "ok"},
    "/api/summary": build_demo_summary,
    "/api/status": get_demo_status,
    "/api/upload": get_upload_recommendation,
    "/api/pending-contract": run_pending_contract_validation,
    "/api/registry": list_registry_status,
    "/api/noop-preview": run_noop_adapter_preview,
    "/api/disabled-family": run_disabled_family_preview,
    "/api/decision-fields": get_decision_field_schema,
    "/api/decision-template": get_decision_template,
    "/api/decision-example": get_decision_example,
    "/api/talk-track": get_demo_talk_track,
    "/api/demo-readiness": get_demo_readiness,
    "/api/demo-script": get_demo_script,
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
    label { display: grid; gap: 5px; margin-bottom: 10px; color: #bcd3e9; }
    input, select { width: 100%; box-sizing: border-box; border: 1px solid #385675; border-radius: 7px; padding: 9px; background: #07111f; color: #dce8f5; }
    .decision-form { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 8px 14px; }
    .wide { grid-column: 1 / -1; }
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
    <section class="wide"><h2>9. Mentor Decision Capture</h2>
      <p>Local browser form only. The pending draft is not sent to or stored by the server.</p>
      <div class="decision-form">
        <label>Strategy family<select id="decision-family"><option>moving_average</option><option>momentum</option><option>breakout</option><option>mean_reversion</option></select></label>
        <label>Universe<input id="decision-universe" placeholder="small-symbol research universe"></label>
        <label>Symbols<input id="decision-symbols" placeholder="FPT, VNM, VCB"></label>
        <label>Start date<input id="decision-start" type="date"></label>
        <label>End date<input id="decision-end" type="date"></label>
        <label>Execution price<input id="decision-execution" placeholder="next_adjusted_open"></label>
        <label>Transaction cost bps<input id="decision-cost" type="number" min="0"></label>
        <label>Slippage bps<input id="decision-slippage" type="number" min="0"></label>
        <label>Exchange<select id="decision-exchange"><option>HOSE</option><option>HSX</option><option>UPCOM</option></select></label>
        <label>Rebalance rule<input id="decision-rebalance"></label>
        <label>Risk rule<input id="decision-risk"></label>
        <label>Position sizing<input id="decision-sizing"></label>
        <label>Max holding period<input id="decision-holding"></label>
      </div>
      <button onclick="fillSampleMentorDecision()">Fill Sample Mentor Decision</button>
      <button onclick="copyPendingDraft()">Copy pending contract draft</button>
      <button onclick="copyDemoTalkTrack()">Copy Demo Talk Track</button>
      <button onclick="loadSection('/api/decision-example','decision-output')">Show Pending Example</button>
      <pre id="decision-output">Draft remains pending until approval is recorded manually.</pre>
    </section>
    <section class="wide"><h2>10. Final Demo Readiness</h2>
      <p>Verify the one-command demo, minimal upload, safety checks, and five-minute call route.</p>
      <button onclick="loadSection('/api/demo-readiness','readiness-output')">Check Demo Readiness</button>
      <button onclick="loadSection('/api/demo-script','readiness-output')">Show 5-Minute Demo Script</button>
      <button onclick="copyDemoScript()">Copy Demo Script</button>
      <pre id="readiness-output">Ready to run the final local checks.</pre>
    </section>
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
    function fieldValue(id) { return document.getElementById(id).value.trim(); }
    function numberOrNull(id) { const value = fieldValue(id); return value === '' ? null : Number(value); }
    function buildPendingDraft() {
      const exchange = fieldValue('decision-exchange');
      const exchangeBands = {HOSE: 700, HSX: 700, UPCOM: 1500};
      return {
        strategy_id: 'PENDING_MENTOR_DECISION_DRAFT',
        strategy_family: fieldValue('decision-family'),
        universe: fieldValue('decision-universe'),
        symbols: fieldValue('decision-symbols').split(',').map(value => value.trim().toUpperCase()).filter(Boolean),
        date_range: {start: fieldValue('decision-start'), end: fieldValue('decision-end')},
        price_basis: 'adjusted_ohlc',
        feature_inputs: ['PENDING_MENTOR_APPROVAL'],
        entry_rule: 'PENDING_MENTOR_APPROVAL',
        exit_rule: 'PENDING_MENTOR_APPROVAL',
        rebalance_rule: fieldValue('decision-rebalance'),
        execution_price: fieldValue('decision-execution'),
        transaction_cost_bps: numberOrNull('decision-cost'),
        slippage_bps: numberOrNull('decision-slippage'),
        exchange: exchange,
        slippage_band_bps: exchangeBands[exchange],
        position_sizing: fieldValue('decision-sizing'),
        risk_rule: fieldValue('decision-risk'),
        max_holding_period: fieldValue('decision-holding'),
        lookahead_policy: 'Inputs must be available before execution.',
        data_quality_gates: ['adjusted_ohlc_ready', 'provenance_present', 'symbols_covered'],
        expected_outputs: ['pending_contract_review'],
        caveats: ['Draft only; mentor approval must be recorded manually before validation can return ok.', 'Not investment advice.'],
        mentor_approval_status: 'pending'
      };
    }
    function validateClientDecisionDraft(draft) {
      const missing = [];
      for (const field of ['strategy_family', 'universe', 'execution_price', 'exchange', 'rebalance_rule', 'risk_rule', 'position_sizing', 'max_holding_period']) {
        if (!draft[field]) { missing.push(field); }
      }
      if (!draft.symbols.length) { missing.push('symbols'); }
      if (!draft.date_range.start || !draft.date_range.end) { missing.push('date_range'); }
      if (draft.transaction_cost_bps === null) { missing.push('transaction_cost_bps'); }
      if (draft.slippage_bps === null) { missing.push('slippage_bps'); }
      const missingNumbers = missing.filter(field => ['transaction_cost_bps', 'slippage_bps'].includes(field));
      return {
        status: missing.length ? 'not_ready' : 'draft_ready',
        missing_fields: missing,
        warning: missingNumbers.length ? 'Required number fields are blank; values remain null and the draft is not_ready.' : null
      };
    }
    function renderDecisionPreview(draft) {
      const preview = {...validateClientDecisionDraft(draft), contract_draft: draft};
      document.getElementById('decision-output').textContent = JSON.stringify(preview, null, 2);
      return preview;
    }
    function fillSampleMentorDecision() {
      document.getElementById('decision-family').value = 'moving_average';
      document.getElementById('decision-universe').value = 'small_symbol_research';
      document.getElementById('decision-symbols').value = 'FPT, VNM, VCB';
      document.getElementById('decision-start').value = '2025-01-01';
      document.getElementById('decision-end').value = '2025-12-31';
      document.getElementById('decision-execution').value = 'next_adjusted_open';
      document.getElementById('decision-cost').value = '15';
      document.getElementById('decision-slippage').value = '10';
      document.getElementById('decision-exchange').value = 'HOSE';
      document.getElementById('decision-rebalance').value = 'daily after completed bar';
      document.getElementById('decision-risk').value = 'no leverage';
      document.getElementById('decision-sizing').value = 'equal research weight';
      document.getElementById('decision-holding').value = '20 sessions';
      renderDecisionPreview(buildPendingDraft());
    }
    async function copyPendingDraft() {
      const draft = buildPendingDraft();
      const text = JSON.stringify(draft, null, 2);
      renderDecisionPreview(draft);
      if (navigator.clipboard) { await navigator.clipboard.writeText(text); }
    }
    async function copyDemoTalkTrack() {
      const response = await fetch('/api/talk-track');
      const payload = await response.json();
      document.getElementById('decision-output').textContent = payload.talk_track;
      if (navigator.clipboard) { await navigator.clipboard.writeText(payload.talk_track); }
    }
    async function copyDemoScript() {
      const response = await fetch('/api/demo-script');
      const payload = await response.json();
      const text = payload.steps.map(step => `${step.time} — ${step.topic}: ${step.talk_track}`).join('\n');
      document.getElementById('readiness-output').textContent = text;
      if (navigator.clipboard) { await navigator.clipboard.writeText(text); }
    }
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
