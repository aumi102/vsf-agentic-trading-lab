"""Read-only QuestDB agent backend (zero external dependencies).

FastAPI is preferred but is NOT installed in this env, and the overnight ingestion
is running in the same env, so we avoid `pip install` and use the Python stdlib
http.server instead. The route surface mirrors what a FastAPI app would expose,
including OpenAI/Open-WebUI compatible `/v1/models` and `/v1/chat/completions`.

Endpoints:
  GET  /health
  GET  /questdb/health
  GET  /market/latest/{symbol}
  GET  /market/ohlcv?symbol=&start_date=&end_date=&adjusted=&limit=
  POST /backtest/ma-cross
  POST /agent/chat
  GET  /v1/models
  POST /v1/chat/completions   (non-streaming only)
"""
from __future__ import annotations

import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pandas as pd

from trading_agent.agent.questdb_agent_service import answer_query
from trading_agent.strategies.simple_ma_cross import run_ma_cross_backtest
from trading_agent.tools import questdb_market_data_tool as tool

SERVICE_NAME = "vsf-questdb-agent-backend"
MODEL_ID = "vsf-questdb-agent"
DEFAULT_OHLCV_LIMIT = 2000


# --- route handlers: each returns (status_code, dict) -----------------------
def handle_health(_qurl: str) -> tuple[int, dict]:
    return 200, {"status": "ok", "service": SERVICE_NAME}


def handle_questdb_health(qurl: str) -> tuple[int, dict]:
    res = tool.get_table_health(url=qurl)
    if res["status"] != "ok" or not res["rows"]:
        return 503, {"status": "error", "caveats": res["caveats"]}
    row = res["rows"][0]
    wal = tool.query_questdb("SELECT suspended FROM wal_tables() WHERE name='daily_prices'", url=qurl)
    wal_suspended = None
    if wal["status"] == "ok" and wal["rows"]:
        wal_suspended = list(wal["rows"][0].values())[0]
    return 200, {
        "status": "ok",
        "row_count": int(row.get("total_rows", 0)),
        "distinct_symbols": int(row.get("symbols", 0)),
        "first_date": str(row.get("first_date"))[:10],
        "last_date": str(row.get("last_date"))[:10],
        "wal_suspended": wal_suspended,
        "adjustment_status_breakdown": row.get("adjustment_status_breakdown", []),
        "caveats": res["caveats"],
    }


def handle_latest(qurl: str, symbol: str) -> tuple[int, dict]:
    res = tool.get_latest_ohlcv(symbol, url=qurl)
    if res["status"] != "ok":
        return 400, res
    if res["row_count"] == 0:
        return 404, {"status": "not_found", "symbol": symbol.upper(), "rows": [], "caveats": res["caveats"]}
    return 200, {"status": "ok", "symbol": symbol.upper(), "latest": res["rows"][0], "caveats": res["caveats"]}


def handle_ohlcv(qurl: str, params: dict) -> tuple[int, dict]:
    symbol = (params.get("symbol", [""])[0]).strip()
    start = (params.get("start_date", [""])[0]).strip()
    end = (params.get("end_date", [""])[0]).strip()
    adjusted = (params.get("adjusted", ["true"])[0]).strip().lower() != "false"
    try:
        limit = int(params.get("limit", [str(DEFAULT_OHLCV_LIMIT)])[0])
    except ValueError:
        limit = DEFAULT_OHLCV_LIMIT
    if not symbol or not start or not end:
        return 400, {"status": "error", "caveats": ["symbol, start_date, end_date are required"]}
    res = tool.get_ohlcv_window(symbol, start, end, adjusted=adjusted, url=qurl)
    if res["status"] != "ok":
        return 400, res
    rows = res["rows"]
    caveats = list(res["caveats"])
    truncated = False
    if limit > 0 and len(rows) > limit:
        rows = rows[:limit]
        truncated = True
        caveats.append(f"output truncated to limit={limit} (full row_count={res['row_count']})")
    return 200, {
        "status": "ok", "symbol": symbol.upper(), "start_date": start, "end_date": end,
        "adjusted": adjusted, "row_count": res["row_count"], "returned": len(rows),
        "truncated": truncated, "rows": rows, "caveats": caveats,
    }


def handle_backtest(qurl: str, body: dict) -> tuple[int, dict]:
    symbol = str(body.get("symbol", "")).strip()
    start = str(body.get("start_date", "2020-01-01")).strip()
    end = str(body.get("end_date", "2025-12-31")).strip()
    fast = int(body.get("fast_window", 20))
    slow = int(body.get("slow_window", 50))
    cost_bps = float(body.get("transaction_cost_bps", 15))
    if not symbol:
        return 400, {"status": "error", "caveats": ["symbol is required"]}
    res = tool.get_ohlcv_window(symbol, start, end, adjusted=True, url=qurl)
    if res["status"] != "ok" or res["row_count"] == 0:
        return 400, {"status": "error", "symbol": symbol.upper(),
                     "caveats": res["caveats"] + [f"no data for {symbol} in {start}..{end}"]}
    bt = run_ma_cross_backtest(pd.DataFrame(res["rows"]), fast=fast, slow=slow, cost_bps=cost_bps)
    code = 200 if bt.get("status") == "ok" else 400
    bt["symbol"] = symbol.upper()
    bt.setdefault("caveats", [])
    bt["caveats"] = res["caveats"] + bt["caveats"]
    return code, bt


def handle_agent_chat(qurl: str, body: dict) -> tuple[int, dict]:
    message = str(body.get("message", "")).strip()
    if not message:
        return 400, {"status": "error", "caveats": ["message is required"]}
    return 200, answer_query(message, questdb_url=qurl)


def handle_models(_qurl: str) -> tuple[int, dict]:
    return 200, {
        "object": "list",
        "data": [{"id": MODEL_ID, "object": "model", "created": 0, "owned_by": "vsf"}],
    }


def handle_chat_completions(qurl: str, body: dict) -> tuple[int, dict]:
    if body.get("stream"):
        return 400, {"error": {"message": "streaming is not supported in this MVP; set stream=false",
                               "type": "invalid_request_error"}}
    messages = body.get("messages") or []
    user_msg = ""
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            user_msg = str(msg.get("content", ""))
            break
    if not user_msg:
        return 400, {"error": {"message": "no user message found", "type": "invalid_request_error"}}
    result = answer_query(user_msg, questdb_url=qurl)
    return 200, {
        "id": f"chatcmpl-vsf-{int(time.time()*1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": MODEL_ID,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": result["answer_markdown"]},
            "finish_reason": "stop",
        }],
        "vsf_meta": {"intent": result["intent"], "status": result["status"],
                     "tool_calls": result["tool_calls"], "caveats": result["caveats"]},
    }


class AgentHTTPRequestHandler(BaseHTTPRequestHandler):
    server_version = "vsf-agent/0.1"

    @property
    def _qurl(self) -> str:
        return getattr(self.server, "questdb_url", tool.DEFAULT_URL)

    def _send(self, code: int, obj: dict) -> None:
        payload = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(payload)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"__parse_error__": True}

    def do_OPTIONS(self) -> None:  # CORS preflight
        self._send(204, {})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            if path == "/health":
                self._send(*handle_health(self._qurl)); return
            if path == "/questdb/health":
                self._send(*handle_questdb_health(self._qurl)); return
            m = re.match(r"^/market/latest/([^/?]+)$", path)
            if m:
                self._send(*handle_latest(self._qurl, m.group(1))); return
            if path == "/market/ohlcv":
                self._send(*handle_ohlcv(self._qurl, parse_qs(parsed.query))); return
            if path == "/v1/models":
                self._send(*handle_models(self._qurl)); return
            self._send(404, {"status": "error", "caveats": [f"unknown route GET {path}"]})
        except Exception as exc:  # never crash the server on a bad request
            self._send(500, {"status": "error", "caveats": [f"server_error: {exc}"]})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        body = self._read_body()
        if body.get("__parse_error__"):
            self._send(400, {"status": "error", "caveats": ["invalid JSON body"]}); return
        try:
            if path == "/backtest/ma-cross":
                self._send(*handle_backtest(self._qurl, body)); return
            if path == "/agent/chat":
                self._send(*handle_agent_chat(self._qurl, body)); return
            if path == "/v1/chat/completions":
                self._send(*handle_chat_completions(self._qurl, body)); return
            self._send(404, {"status": "error", "caveats": [f"unknown route POST {path}"]})
        except Exception as exc:
            self._send(500, {"status": "error", "caveats": [f"server_error: {exc}"]})

    def log_message(self, fmt: str, *args) -> None:  # concise one-line access log
        print(f"[backend] {self.address_string()} {fmt % args}")


def serve(host: str = "127.0.0.1", port: int = 8010, questdb_url: str = tool.DEFAULT_URL) -> None:
    httpd = ThreadingHTTPServer((host, port), AgentHTTPRequestHandler)
    httpd.questdb_url = questdb_url  # type: ignore[attr-defined]
    print(f"{SERVICE_NAME} listening on http://{host}:{port}  (QuestDB={questdb_url})")
    print("endpoints: /health /questdb/health /market/latest/{sym} /market/ohlcv "
          "/backtest/ma-cross /agent/chat /v1/models /v1/chat/completions")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down backend ...")
    finally:
        httpd.server_close()
