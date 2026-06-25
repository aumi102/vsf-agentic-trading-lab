"""Benchmark QuestDB REST `/exec` vs PGWire (psycopg) for representative reads.

  python scripts\benchmark_questdb_query_paths.py --repeats 50

For each query it warms up, then times N repeats on each path and prints
p50/p95/min/max of the total round-trip plus the mean server execute time. It is
read-only and never mutates QuestDB. If PGWire is unavailable it reports clearly
and benchmarks REST only.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass

from trading_agent.storage import questdb_pgwire_client as pg  # noqa: E402
from trading_agent.storage import questdb_read as qr  # noqa: E402

QUERIES: dict[str, str] = {
    "latest_ohlcv_FPT": "SELECT trade_date, open, high, low, close, adjusted_close, volume FROM daily_prices WHERE symbol = 'FPT' ORDER BY trade_date DESC LIMIT 1",
    "market_summary_features_FPT": "SELECT trade_date, adjusted_close, ma20, ma50, volatility20 FROM feature_snapshots WHERE symbol = 'FPT' ORDER BY trade_date DESC LIMIT 1",
    "latest_signal_FPT": "SELECT trade_date, signal, score, reason_code FROM signals WHERE symbol = 'FPT' ORDER BY trade_date DESC LIMIT 1",
    "backtest_comparison_FPT": "SELECT r.strategy_id, m.final_value, m.total_return_pct, m.sharpe_ratio FROM backtest_runs r JOIN backtest_metrics m ON r.run_id = m.run_id WHERE r.symbol = 'FPT' AND r.slippage_bps = 0.0",
    "event_latest_FPT": "SELECT published_at, title, category FROM event_news_items WHERE symbol = 'FPT' ORDER BY published_at DESC LIMIT 5",
    "count_daily_prices": "SELECT count() FROM daily_prices",
}


def _summarize(totals: list[float]) -> dict[str, float]:
    ordered = sorted(totals)
    return {
        "min": round(ordered[0], 3),
        "p50": round(statistics.median(ordered), 3),
        "p95": round(ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))], 3),
        "max": round(ordered[-1], 3),
        "mean": round(statistics.fmean(ordered), 3),
    }


def _bench(runner, sql: str, repeats: int, warmup: int) -> dict | None:
    for _ in range(warmup):
        res = runner(sql)
        if res.get("status") != "ok":
            return {"error": "; ".join(res.get("caveats", [])) or "query failed"}
    totals: list[float] = []
    executes: list[float] = []
    for _ in range(repeats):
        res = runner(sql)
        if res.get("status") != "ok":
            return {"error": "; ".join(res.get("caveats", [])) or "query failed"}
        timing = res.get("timing", {})
        totals.append(float(timing.get("total_ms", 0.0)))
        executes.append(float(timing.get("execute_ms", 0.0)))
    summary = _summarize(totals)
    summary["execute_mean"] = round(statistics.fmean(executes), 4)
    summary["rows"] = res.get("row_count", 0)
    return summary


def _compare_hosts(repeats: int = 5) -> None:
    """Show the Windows localhost(IPv6) vs 127.0.0.1(IPv4) fresh-connect penalty.

    Each iteration uses a *fresh* httpx client (no keep-alive) to expose the
    per-connection cost. QuestDB binds IPv4, so `localhost` pays a ~2s `::1`
    connect-timeout fallback on Windows; `127.0.0.1` avoids it.
    """
    import httpx

    print("localhost vs 127.0.0.1 fresh-connection latency (no keep-alive)")
    print(f"  {'host':<24} {'p50_ms':>10} {'min_ms':>10} {'max_ms':>10}")
    print("  " + "-" * 56)
    for label, base in (("http://localhost:9000", "http://localhost:9000"), ("http://127.0.0.1:9000", "http://127.0.0.1:9000")):
        samples: list[float] = []
        for _ in range(repeats):
            client = httpx.Client(timeout=10.0)
            t0 = time.perf_counter()
            try:
                client.get(f"{base}/exec", params={"query": "SELECT 1"})
                samples.append((time.perf_counter() - t0) * 1000.0)
            except Exception as exc:  # pragma: no cover
                samples.append(float("nan"))
                print(f"  {label:<24} error: {exc}")
            finally:
                client.close()
        ordered = sorted(s for s in samples if s == s)
        if ordered:
            print(f"  {label:<24} {statistics.median(ordered):>10.1f} {ordered[0]:>10.1f} {ordered[-1]:>10.1f}")
    print("  finding: prefer 127.0.0.1 on Windows demo machines; the ~2s gap is connect overhead, not query execution.")
    print("")


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark QuestDB REST vs PGWire query paths.")
    parser.add_argument("--questdb-url", default=qr.DEFAULT_URL)
    parser.add_argument("--repeats", type=int, default=50)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--compare-hosts", action="store_true", help="Show localhost(IPv6) vs 127.0.0.1(IPv4) connect penalty and exit.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.compare_hosts:
        _compare_hosts()
        return 0

    pgwire_ok = pg.pgwire_available()
    ping = pg.ping() if pgwire_ok else {"status": "error", "caveats": ["psycopg unavailable"]}
    pgwire_live = pgwire_ok and ping.get("status") == "ok"

    report: dict[str, dict] = {}
    for name, sql in QUERIES.items():
        rest = _bench(lambda q: qr.query_rest_timed(q, url=args.questdb_url), sql, args.repeats, args.warmup)
        pgw = (
            _bench(lambda q: pg.query_pgwire(q), sql, args.repeats, args.warmup)
            if pgwire_live
            else {"error": "pgwire unavailable"}
        )
        report[name] = {"rest": rest, "pgwire": pgw}

    if args.json:
        print(json.dumps({"pgwire_live": pgwire_live, "repeats": args.repeats, "results": report}, indent=2))
        return 0

    print(f"QuestDB query-path benchmark  repeats={args.repeats} warmup={args.warmup}")
    print(f"pgwire_live={pgwire_live}  (connect uses a reused/pooled connection)")
    print("")
    header = f"{'query':<28} {'path':<7} {'p50_ms':>8} {'p95_ms':>8} {'min_ms':>8} {'max_ms':>8} {'exec_ms':>8} {'rows':>5}"
    print(header)
    print("-" * len(header))
    rest_p50: list[float] = []
    pg_p50: list[float] = []
    for name, paths in report.items():
        for path in ("rest", "pgwire"):
            summary = paths[path]
            if "error" in summary:
                print(f"{name:<28} {path:<7} {summary['error']}")
                continue
            print(
                f"{name:<28} {path:<7} {summary['p50']:>8} {summary['p95']:>8} "
                f"{summary['min']:>8} {summary['max']:>8} {summary['execute_mean']:>8} {summary['rows']:>5}"
            )
            if path == "rest":
                rest_p50.append(summary["p50"])
            else:
                pg_p50.append(summary["p50"])
    print("")
    if rest_p50 and pg_p50:
        rest_med = statistics.fmean(rest_p50)
        pg_med = statistics.fmean(pg_p50)
        print(f"mean of per-query p50  REST={rest_med:.3f}ms  PGWire={pg_med:.3f}ms")
        if pg_med < rest_med * 0.9:
            print("recommendation: PGWire is faster for repeated reads -> set QUESTDB_QUERY_MODE=pgwire for read-only APIs.")
        elif rest_med < pg_med * 0.9:
            print("recommendation: REST is competitive here -> keep REST (default); revisit PGWire under higher load.")
        else:
            print("recommendation: REST and PGWire are close -> keep REST default; PGWire ready behind QUESTDB_QUERY_MODE=pgwire.")
    print("note: keep REST `/imp` for CSV ingestion; this benchmark only covers read queries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
