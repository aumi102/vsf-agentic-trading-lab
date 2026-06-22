"""Full-universe Vietcap daily OHLCV -> QuestDB batch ingestion (sequential, no async).

Pipeline (per the mentor spec):
  1. Load the tradable universe (>1000 tickers).
  2. Ensure a correct QuestDB `daily_prices` schema (raw + adjusted OHLC, WAL,
     PARTITION BY YEAR, DEDUP UPSERT KEYS(trade_date, security_id, source_id)).
  3. Loop tickers sequentially in batches of N (default 10):
        fetch N -> parse/adjust/validate -> one CSV -> /imp -> gc.collect().
  4. Rate-limit / failures go to a retry queue; --retry-failed drains it with
     backoff; unresolved tickers are recorded in final_failed.jsonl.
  5. --resume skips tickers already completed in prior checkpoints.
  6. Print a final report with real QuestDB row counts and date ranges.

Example:
  python scripts/batch_ingest_vietcap_ohlcv_to_questdb.py ^
    --questdb-url http://localhost:9000 --from-date 2000-01-01 --to-date today ^
    --batch-size 10 --resume --retry-failed --table daily_prices
"""
from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import io
import json
import sys
import random
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass

from trading_agent.ingestion.vietcap_full_ohlcv_fetcher import (  # noqa: E402
    DAILY_PRICES_COLUMNS,
    OHLCV_ENDPOINT,
    PARSER_VERSION,
    SymbolFetchResult,
    extract_universe,
    fetch_symbol_ohlcv,
    fetch_universe_payload,
    make_run_id,
    ohlcv_request_body,
    parse_symbol_payload,
    utc_now_iso,
)
from trading_agent.storage import questdb_client as qdb  # noqa: E402

UNIVERSE_CSV = ROOT / "data/cache/vietcap/universe/latest_universe.csv"
RAW_OHLCV_DIR = ROOT / "data/raw/vietcap_ohlcv"
BATCH_DIR = ROOT / "data/cache/vietcap/batches"
RETRY_DIR = ROOT / "data/cache/vietcap/retry"
CHECKPOINT_DIR = ROOT / "data/cache/vietcap/checkpoints"
QUARANTINE_DIR = ROOT / "data/cache/vietcap/quarantine"

RETRYABLE = {"rate_limited", "timeout", "http_error", "bad_json"}


def schema_sql(table: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {table} (
    trade_date TIMESTAMP,
    security_id SYMBOL CAPACITY 4096 CACHE,
    symbol SYMBOL CAPACITY 4096 CACHE,
    exchange SYMBOL,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    adjusted_open DOUBLE,
    adjusted_high DOUBLE,
    adjusted_low DOUBLE,
    adjusted_close DOUBLE,
    volume DOUBLE,
    value DOUBLE,
    adjustment_factor DOUBLE,
    price_basis SYMBOL,
    adjustment_status SYMBOL,
    quality_status SYMBOL,
    source_id SYMBOL,
    raw_path STRING,
    ingested_at TIMESTAMP
) TIMESTAMP(trade_date) PARTITION BY YEAR WAL
DEDUP UPSERT KEYS(trade_date, security_id, source_id);
""".strip()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Batch-ingest full Vietcap OHLCV into QuestDB.")
    p.add_argument("--questdb-url", default=qdb.DEFAULT_QUESTDB_URL)
    p.add_argument("--from-date", default="2000-01-01")
    p.add_argument("--to-date", default="today")
    p.add_argument("--batch-size", type=int, default=10)
    p.add_argument("--table", default="daily_prices")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--retry-failed", action="store_true")
    p.add_argument("--limit-symbols", type=int, default=0, help="Process only the first N symbols (smoke test).")
    p.add_argument("--symbols", default="", help="Explicit comma-separated symbols, overrides the universe file.")
    p.add_argument("--count-back", type=int, default=9000, help="Bars to request per symbol (>=2000 history).")
    p.add_argument("--timeout-seconds", type=int, default=30)
    p.add_argument("--run-id", default="")
    p.add_argument("--universe-path", default=str(UNIVERSE_CSV))
    p.add_argument("--recreate", action="store_true", help="Drop and recreate the table before ingest.")
    p.add_argument("--retry-rounds", type=int, default=3)
    p.add_argument("--rate-retries", type=int, default=3,
                   help="Quick per-symbol retries on rate-limit/timeout before counting it as throttled.")
    # --- Operator-safe rate-limit policy ---
    p.add_argument("--sleep-jitter-min", type=float, default=2.0, help="Min seconds between symbol fetches (jittered).")
    p.add_argument("--sleep-jitter-max", type=float, default=5.0, help="Max seconds between symbol fetches (jittered).")
    p.add_argument("--max-consecutive-rate-limits", type=int, default=5,
                   help="Stop or cool down after this many consecutive throttled symbols.")
    p.add_argument("--stop-on-rate-limit", action=argparse.BooleanOptionalAction, default=True,
                   help="Stop cleanly (exit 75) at the consecutive-throttle limit; --no-stop-on-rate-limit cools down instead.")
    p.add_argument("--cooldown-minutes", type=float, default=30.0,
                   help="When NOT stopping, sleep this long at the throttle limit, then resume.")
    p.add_argument("--max-symbols-per-run", type=int, default=0, help="Process at most N symbols this run (0 = unlimited).")
    p.add_argument("--start-index", type=int, default=0, help="Skip the first N symbols of the work list.")
    p.add_argument("--only-missing", action="store_true", help="Skip symbols already present in QuestDB.")
    p.add_argument("--status-only", action="store_true", help="Print progress/health and exit without fetching.")
    p.add_argument("--no-fetch", action="store_true", help="Do not call the network; ingest from cached raw payloads only.")
    return p.parse_args()


EXIT_RATE_LIMIT_STOP = 75  # special exit code: stopped cleanly due to sustained throttling


def resolve_dates(from_date: str, to_date: str) -> tuple[str, str, int]:
    from_d = from_date.strip()
    if to_date.strip().lower() == "today":
        to_d = date.today().isoformat()
    else:
        to_d = to_date.strip()
    end = datetime.fromisoformat(to_d).replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    to_epoch = int(min(end, now).timestamp())
    return from_d, to_d, to_epoch


def load_universe(args: argparse.Namespace) -> list[dict[str, str]]:
    if args.symbols.strip():
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        return [{"symbol": s, "security_id": f"vietcap_iq:{s}", "exchange": ""} for s in symbols]
    path = Path(args.universe_path)
    if not path.exists():
        print(f"Universe file not found ({path}); fetching live ...")
        payload, _, _ = fetch_universe_payload(args.timeout_seconds)
        return extract_universe(payload)["tradable"]
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [{"symbol": r["symbol"].upper(), "security_id": r.get("security_id") or f"vietcap_iq:{r['symbol'].upper()}",
             "exchange": r.get("exchange", "")} for r in rows if r.get("symbol")]


def ensure_schema(client, base: str, table: str, recreate: bool) -> bool:
    """Create/migrate the table. Returns True if it was dropped+recreated."""
    cols = qdb.column_names(client, base, table)
    if not cols:
        qdb.exec_query(client, base, schema_sql(table))
        print(f"Created table '{table}' with full raw+adjusted schema.")
        return False
    if recreate or "adjusted_close" not in cols:
        old = qdb.exec_scalar(client, base, f"SELECT count() FROM {table}", 0)
        reason = "forced --recreate" if recreate else "missing adjusted_close column (old schema)"
        print(f"Migrating '{table}' ({reason}); dropping {old} existing rows (re-fetchable).")
        qdb.exec_query(client, base, f"DROP TABLE {table}")
        qdb.exec_query(client, base, schema_sql(table))
        print(f"Recreated table '{table}' with full raw+adjusted schema.")
        return True
    print(f"Table '{table}' already has the correct schema.")
    return False


def load_resume_completed() -> set[str]:
    completed: set[str] = set()
    for path in CHECKPOINT_DIR.glob("run_id=*/completed_symbols.txt"):
        for line in path.read_text(encoding="utf-8").splitlines():
            token = line.strip().upper()
            if token:
                completed.add(token)
    return completed


def rows_to_csv(rows: list[dict[str, Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=DAILY_PRICES_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({col: ("" if row.get(col) is None else row.get(col)) for col in DAILY_PRICES_COLUMNS})
    return buffer.getvalue().encode("utf-8")


def save_raw(run_id: str, symbol: str, body: bytes, http_status: int | None, to_epoch: int, count_back: int) -> str:
    sym_dir = RAW_OHLCV_DIR / f"run_id={run_id}" / f"symbol={symbol}"
    sym_dir.mkdir(parents=True, exist_ok=True)
    payload_path = sym_dir / "payload.json"
    payload_path.write_bytes(body or b"")
    content_hash = hashlib.sha256(body or b"").hexdigest()
    row_count = 0
    try:
        parsed = json.loads((body or b"").decode("utf-8-sig"))
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            row_count = len(parsed[0].get("t") or [])
    except Exception:
        row_count = 0
    metadata = {
        "endpoint_label": "vietcap_iq_gap_chart",
        "endpoint": OHLCV_ENDPOINT,
        "symbol": symbol,
        "request_params": ohlcv_request_body(symbol, count_back, to_epoch),
        "http_status": http_status,
        "crawled_at": utc_now_iso(),
        "row_count": row_count,
        "content_hash": content_hash,
        "byte_size": len(body or b""),
        "parser_version": PARSER_VERSION,
    }
    (sym_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(payload_path)


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> int:
    args = parse_args()
    base = args.questdb_url.rstrip("/")
    run_id = args.run_id or make_run_id()
    from_d, to_d, to_epoch = resolve_dates(args.from_date, args.to_date)

    print(f"run_id={run_id}")
    print(f"date_range={from_d}..{to_d} (to_epoch={to_epoch}) count_back={args.count_back}")

    universe = load_universe(args)
    if args.limit_symbols > 0:
        universe = universe[: args.limit_symbols]
    print(f"universe_symbols={len(universe)}")

    client = qdb.open_client(timeout_seconds=max(120, args.timeout_seconds))
    if qdb.exec_scalar(client, base, "SELECT 1", None) != 1:
        print("ERROR: QuestDB did not answer SELECT 1.", file=sys.stderr)
        return 1

    if args.status_only:
        print_status(client, base, args.table, len(universe))
        client.close()
        return 0

    recreated = ensure_schema(client, base, args.table, args.recreate)

    resume_completed = set()
    if args.resume and not recreated:
        resume_completed = load_resume_completed()
        print(f"resume_completed_symbols={len(resume_completed)}")
    elif args.resume and recreated:
        print("resume requested but table was recreated -> ignoring old checkpoints (data was dropped).")

    work = [u for u in universe if u["symbol"] not in resume_completed]
    if args.only_missing:
        present = present_symbols(client, base, args.table)
        before = len(work)
        work = [u for u in work if u["symbol"] not in present]
        print(f"only_missing=True: skipped {before - len(work)} symbols already in QuestDB ({len(present)} present)")
    if args.start_index > 0:
        work = work[args.start_index:]
        print(f"start_index={args.start_index}: {len(work)} symbols remain")
    if args.max_symbols_per_run > 0 and len(work) > args.max_symbols_per_run:
        work = work[: args.max_symbols_per_run]
        print(f"max_symbols_per_run={args.max_symbols_per_run}: capping this run to {len(work)} symbols")
    print(f"symbols_to_process={len(work)}")

    checkpoint_path = CHECKPOINT_DIR / f"run_id={run_id}" / "completed_symbols.txt"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    retry_queue_path = RETRY_DIR / f"run_id={run_id}" / "retry_queue.jsonl"
    final_failed_path = RETRY_DIR / f"run_id={run_id}" / "final_failed.jsonl"
    quarantine_path = QUARANTINE_DIR / f"run_id={run_id}" / "quarantined_rows.jsonl"

    stats = {
        "loaded": 0, "failed": 0, "empty": 0, "rows_imported": 0,
        "adjusted_from_source": 0, "no_adjustment_needed": 0, "adjusted_missing_warn": 0,
        "quarantined_rows": 0,
    }
    failed_symbols: dict[str, dict[str, Any]] = {}
    batch_index = 0

    def fetch_one(symbol: str) -> SymbolFetchResult:
        """One symbol fetch with a SMALL number of quick jittered retries.

        We deliberately do NOT grind for minutes here: a few quick retries are
        enough to ride out a transient blip, and sustained throttling is handled
        at the loop level by the consecutive-rate-limit stop/cooldown policy."""
        if args.no_fetch:
            body = load_cached_payload(symbol)
            if body is None:
                return SymbolFetchResult(symbol, "no_cache", None, None, "no cached payload")
            return SymbolFetchResult(symbol, "ok", 200, body)
        result = fetch_symbol_ohlcv(
            symbol, count_back=args.count_back, to_epoch=to_epoch, timeout_seconds=args.timeout_seconds
        )
        attempt = 0
        while result.status in {"rate_limited", "timeout"} and attempt < args.rate_retries:
            attempt += 1
            backoff = random.uniform(args.sleep_jitter_min, args.sleep_jitter_max) * attempt
            print(f"  {symbol}: {result.status} (http={result.http_status}); quick retry "
                  f"{attempt}/{args.rate_retries} in {backoff:.1f}s")
            time.sleep(backoff)
            result = fetch_symbol_ohlcv(
                symbol, count_back=args.count_back, to_epoch=to_epoch, timeout_seconds=args.timeout_seconds
            )
        return result

    def process_symbol(item: dict[str, str], batch_rows: list[dict[str, Any]]) -> str:
        symbol = item["symbol"]
        result = fetch_one(symbol)
        if result.status != "ok":
            if result.status in RETRYABLE:
                append_jsonl(retry_queue_path, {
                    "symbol": symbol, "status": result.status, "http_status": result.http_status,
                    "error": result.error, "ts": utc_now_iso(),
                })
            return result.status
        raw_path = save_raw(run_id, symbol, result.body or b"", result.http_status, to_epoch, args.count_back)
        parsed = parse_symbol_payload(
            symbol, item.get("security_id") or f"vietcap_iq:{symbol}", item.get("exchange", ""),
            result.body or b"", from_date=from_d, to_date=to_d, raw_path=raw_path, ingested_at=utc_now_iso(),
        )
        stats["adjusted_from_source"] += parsed.adjusted_from_source
        stats["no_adjustment_needed"] += parsed.no_adjustment_needed
        stats["adjusted_missing_warn"] += parsed.adjusted_missing_warn
        for bad in parsed.quarantined:
            append_jsonl(quarantine_path, bad)
        stats["quarantined_rows"] += len(parsed.quarantined)
        if not parsed.rows:
            return "empty"
        batch_rows.extend(parsed.rows)
        return "ok"

    def flush_batch(batch_rows: list[dict[str, Any]], batch_symbols: list[str]) -> None:
        nonlocal batch_index
        if not batch_rows:
            for sym in batch_symbols:
                _mark_completed(checkpoint_path, sym)
            return
        batch_index += 1
        batch_csv_path = BATCH_DIR / f"run_id={run_id}" / f"batch_{batch_index:05d}.csv"
        batch_csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_bytes = rows_to_csv(batch_rows)
        batch_csv_path.write_bytes(csv_bytes)
        try:
            imported = qdb.imp_csv(client, base, args.table, csv_bytes)
            qdb.wait_wal_applied(client, base, args.table)
            stats["rows_imported"] += imported
            for sym in batch_symbols:
                _mark_completed(checkpoint_path, sym)
            print(f"  batch {batch_index:05d}: imported {imported} rows from {len(batch_symbols)} symbols "
                  f"({', '.join(batch_symbols)})")
        except Exception as exc:  # import failed -> retry whole batch later
            for sym in batch_symbols:
                failed_symbols[sym] = {"symbol": sym, "status": "imp_failed", "error": str(exc)[:300]}
                append_jsonl(retry_queue_path, {"symbol": sym, "status": "imp_failed", "error": str(exc)[:300], "ts": utc_now_iso()})
            print(f"  batch {batch_index:05d}: /imp FAILED ({exc}); {len(batch_symbols)} symbols queued for retry")
        finally:
            batch_rows.clear()
            batch_symbols.clear()
            gc.collect()

    # --- Main sequential loop with operator-safe throttle policy ---
    consecutive_rl = 0
    stop_due_to_throttle = False
    batch_rows: list[dict[str, Any]] = []
    batch_symbols: list[str] = []

    for item in work:
        symbol = item["symbol"]
        status = process_symbol(item, batch_rows)
        if status in {"ok", "empty"}:
            consecutive_rl = 0
            stats["loaded" if status == "ok" else "empty"] += 1
            batch_symbols.append(symbol)
        elif status in {"rate_limited", "timeout"}:
            stats["failed"] += 1
            failed_symbols[symbol] = {"symbol": symbol, "status": status}
            consecutive_rl += 1
            print(f"  {symbol}: {status} [consecutive throttled {consecutive_rl}/{args.max_consecutive_rate_limits}]")
            if consecutive_rl >= args.max_consecutive_rate_limits:
                flush_batch(batch_rows, batch_symbols)  # persist progress before stopping/cooling
                if args.stop_on_rate_limit:
                    stop_due_to_throttle = True
                    break
                print(f"  THROTTLED: {consecutive_rl} consecutive; cooling down {args.cooldown_minutes:.0f} min ...")
                time.sleep(args.cooldown_minutes * 60.0)
                consecutive_rl = 0
                continue
        else:  # http_error / bad_json / no_cache -> non-throttle failure
            stats["failed"] += 1
            failed_symbols[symbol] = {"symbol": symbol, "status": status}
            consecutive_rl = 0
            print(f"  {symbol}: fetch {status} -> recorded")
        if len(batch_symbols) >= args.batch_size:
            flush_batch(batch_rows, batch_symbols)
        if not args.no_fetch:
            time.sleep(random.uniform(args.sleep_jitter_min, args.sleep_jitter_max))

    flush_batch(batch_rows, batch_symbols)  # flush any remainder

    # --- Retry phase (skipped on a hard throttle stop to avoid hammering) ---
    if not stop_due_to_throttle and args.retry_failed and failed_symbols:
        print(f"retrying {len(failed_symbols)} failed symbols (rounds={args.retry_rounds}) ...")
        pending = list(failed_symbols.keys())
        for round_no in range(1, args.retry_rounds + 1):
            if not pending:
                break
            backoff = min(2.0 * round_no, 8.0)
            print(f"  retry round {round_no} ({len(pending)} symbols, backoff {backoff}s)")
            still: list[str] = []
            retry_rows: list[dict[str, Any]] = []
            retry_syms: list[str] = []
            for symbol in pending:
                item = {"symbol": symbol, "security_id": f"vietcap_iq:{symbol}", "exchange": ""}
                status = process_symbol(item, retry_rows)
                if status in {"ok", "empty"}:
                    retry_syms.append(symbol)
                    failed_symbols.pop(symbol, None)
                    if status == "ok":
                        stats["loaded"] += 1
                        stats["failed"] -= 1
                    else:
                        stats["empty"] += 1
                        stats["failed"] -= 1
                else:
                    still.append(symbol)
                time.sleep(backoff)
            flush_batch(retry_rows, retry_syms)
            pending = still
        for symbol in pending:
            append_jsonl(final_failed_path, {**failed_symbols.get(symbol, {"symbol": symbol}),
                                             "reason": "exhausted_retries", "ts": utc_now_iso()})
        if pending:
            print(f"  final_failed={len(pending)} -> {final_failed_path}")

    print_report(client, base, args.table, run_id, stats, len(universe), len(failed_symbols))

    next_cmd = (
        "python scripts\\batch_ingest_vietcap_ohlcv_to_questdb.py --resume --only-missing "
        f"--batch-size {args.batch_size} --sleep-jitter-min {args.sleep_jitter_min} "
        f"--sleep-jitter-max {args.sleep_jitter_max} "
        f"--max-consecutive-rate-limits {args.max_consecutive_rate_limits} --stop-on-rate-limit"
    )
    if stop_due_to_throttle:
        print("\n*** STOPPED CLEANLY: sustained Vietcap rate limiting ***")
        print(f"  consecutive throttled symbols hit the limit ({args.max_consecutive_rate_limits}); "
              f"not hammering further.")
        print(f"  progress is checkpointed; throttled symbols are queued in {retry_queue_path}")
        print(f"  wait for the throttle window to clear, then resume with:\n    {next_cmd}")
        client.close()
        return EXIT_RATE_LIMIT_STOP

    print(f"\nnext recommended command (continue coverage):\n  {next_cmd}")
    client.close()
    return 0


def _mark_completed(checkpoint_path: Path, symbol: str) -> None:
    with checkpoint_path.open("a", encoding="utf-8") as handle:
        handle.write(symbol + "\n")


def load_cached_payload(symbol: str) -> bytes | None:
    """Return the most recent cached raw gap-chart payload for a symbol (--no-fetch)."""
    candidates = sorted(RAW_OHLCV_DIR.glob(f"run_id=*/symbol={symbol}/payload.json"))
    if not candidates:
        return None
    return candidates[-1].read_bytes()  # run_id dirs sort chronologically by timestamp name


def present_symbols(client, base: str, table: str) -> set[str]:
    """Distinct symbols already present in QuestDB (for --only-missing)."""
    if not qdb.table_exists(client, base, table):
        return set()
    _, dataset = qdb.exec_rows(client, base, f"SELECT DISTINCT symbol FROM {table}")
    return {str(row[0]) for row in dataset if row and row[0] is not None}


def print_status(client, base: str, table: str, universe_n: int) -> None:
    """Concise health/progress snapshot used by --status-only."""
    exists = qdb.table_exists(client, base, table)
    print(f"table_exists={exists} table={table} universe_symbols={universe_n}")
    if not exists:
        return
    total = qdb.exec_scalar(client, base, f"SELECT count() FROM {table}", 0)
    distinct = qdb.exec_scalar(client, base, f"SELECT count_distinct(symbol) FROM {table}", 0)
    _, rng = qdb.exec_rows(client, base, f"SELECT min(trade_date), max(trade_date) FROM {table}")
    checkpointed = len(load_resume_completed())
    print(f"rows={total} distinct_symbols={distinct} checkpointed_symbols={checkpointed}")
    if rng and rng[0]:
        print(f"date_range={str(rng[0][0])[:10]}..{str(rng[0][1])[:10]}")
    print(f"universe_coverage={distinct}/{universe_n}")
    print(f"target_3M_reached={int(total) >= 3_000_000}")


def print_report(client, base: str, table: str, run_id: str, stats: dict, universe_n: int, failed_n: int) -> None:
    qdb.wait_wal_applied(client, base, table)
    total = qdb.exec_scalar(client, base, f"SELECT count() FROM {table}", 0)
    _, rng = qdb.exec_rows(client, base, f"SELECT min(trade_date), max(trade_date) FROM {table}")
    first_dt = rng[0][0] if rng and rng[0] else None
    last_dt = rng[0][1] if rng and rng[0] else None
    _, top = qdb.exec_rows(
        client, base, f"SELECT symbol, count() c FROM {table} ORDER BY c DESC LIMIT 20"
    )
    _, adj = qdb.exec_rows(client, base, f"SELECT adjustment_status, count() FROM {table}")

    print("\n================ INGESTION REPORT ================")
    print(f"run_id={run_id}")
    print(f"universe_symbols={universe_n}")
    print(f"symbols_loaded={stats['loaded']}  symbols_empty={stats['empty']}  symbols_failed={failed_n}")
    print(f"rows_imported_this_run={stats['rows_imported']}")
    print(f"quarantined_rows={stats['quarantined_rows']}")
    print(f"QuestDB table '{table}' total rows = {total}")
    print(f"trade_date range: {first_dt} .. {last_dt}")
    print("adjustment_status counts (in table):")
    for row in adj:
        print(f"  {row[0]}: {row[1]}")
    print("top 20 symbols by row count:")
    for row in top:
        print(f"  {row[0]}: {row[1]}")
    print("==================================================")


if __name__ == "__main__":
    raise SystemExit(main())
