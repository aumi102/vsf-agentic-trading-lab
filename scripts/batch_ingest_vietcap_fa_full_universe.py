"""Resumable full-universe Vietcap IQ financial-report (FA) batch ingester.

Reuses the verified single-symbol FA fetch/parse/normalize helpers from
``ingest_vietcap_financial_reports_to_questdb`` and adds production-style batch
controls so the whole tradable universe can be ingested under ONE run_id over
several (overnight) passes:

  * full tradable universe from ``securities`` (no curated symbol list);
  * resume: skip symbols already ATTEMPTED in this run_id (from fa_raw_payloads);
  * --retry-failed: reprocess attempted symbols that produced no balance-sheet rows;
  * --max-symbols: bound each pass (so the overnight runner can loop with cooldowns);
  * --cooldown-seconds + 429 backoff (via _fetch_with_retry) for rate limits;
  * per-run tracking rows in fa_ingest_runs (status stays in_progress until the whole
    universe is attempted, then complete -> FA tools switch to it);
  * --plan-only: print universe/attempted/covered/remaining WITHOUT any network call.

Honesty: the run is marked ``complete`` only when every universe symbol has been
attempted (failures recorded). Until then FA tools keep using the previous complete
run, so uncovered symbols (e.g. VHM) correctly stay "unavailable".

Never mutates daily_prices; appends run-scoped FA rows only.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPT_DIR = Path(__file__).resolve().parent
for path in (str(SRC), str(SCRIPT_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass

from ingest_vietcap_financial_reports_to_questdb import (  # noqa: E402
    FA_COLUMNS,
    RAW_COLUMNS,
    RAW_ROOT,
    RUN_COLUMNS,
    SYMBOL_RE,
    _csv_bytes,
    _ensure_tables,
    _fetch_with_retry,
    _normalize_facts,
    _parse_statements,
    _utc_timestamp,
    parse_payload,
)
from trading_agent.storage import questdb_client as qdb  # noqa: E402

FA_FACT_TABLES = ("fa_balance_sheet", "fa_income_statement", "fa_cash_flow", "fa_notes")


def _load_universe(client, base_url: str, universe_file: str | None) -> list[str]:
    if universe_file:
        text = Path(universe_file).read_text(encoding="utf-8")
        symbols = [line.strip().upper() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    else:
        _, rows = qdb.exec_rows(client, base_url, "SELECT DISTINCT symbol FROM securities ORDER BY symbol")
        symbols = [str(row[0]).upper() for row in rows if row]
    return [s for s in dict.fromkeys(symbols) if SYMBOL_RE.fullmatch(s)]


def _distinct_symbols(client, base_url: str, table: str, run_id: str) -> set[str]:
    if not _table_exists(client, base_url, table):
        return set()
    sql = f"SELECT DISTINCT symbol FROM {table}"
    if run_id and run_id != "*":
        sql += f" WHERE run_id = '{run_id}'"
    _, rows = qdb.exec_rows(client, base_url, sql)
    return {str(row[0]).upper() for row in rows if row}


def _table_exists(client, base_url: str, table: str) -> bool:
    _, rows = qdb.exec_rows(client, base_url, "SHOW TABLES")
    return table in {str(row[0]) for row in rows if row}


def _table_count(client, base_url: str, table: str, run_id: str) -> int:
    if not _table_exists(client, base_url, table):
        return 0
    return int(qdb.exec_scalar(client, base_url, f"SELECT count() FROM {table} WHERE run_id = '{run_id}'", 0))


def _latest_in_progress_run(client, base_url: str) -> str | None:
    if not _table_exists(client, base_url, "fa_ingest_runs"):
        return None
    sql = ("SELECT run_id FROM fa_ingest_runs WHERE scope = 'full_universe' AND status = 'in_progress' "
           "ORDER BY created_at DESC LIMIT 1")
    value = qdb.exec_scalar(client, base_url, sql, "")
    return str(value) if value else None


def _write_run_row(client, base_url: str, row: dict) -> None:
    qdb.imp_csv(client, base_url, "fa_ingest_runs", _csv_bytes([row], RUN_COLUMNS), timeout_seconds=60.0)
    qdb.wait_wal_applied(client, base_url, "fa_ingest_runs", attempts=120)


def _progress_row(*, run_id, statements, status, attempted, counts, failures) -> dict:
    return {
        "created_at": _utc_timestamp(),
        "run_id": run_id,
        "scope": "full_universe",
        "symbols": "",  # universe is large; coverage is tracked in the fact tables, not here
        "statements": ",".join(section for _, section, _ in statements),
        "replace_mode": "run",
        "status": status,
        "symbols_processed": attempted,
        "raw_payload_rows": counts.get("fa_raw_payloads", 0),
        "fa_balance_sheet_rows": counts.get("fa_balance_sheet", 0),
        "fa_income_statement_rows": counts.get("fa_income_statement", 0),
        "fa_cash_flow_rows": counts.get("fa_cash_flow", 0),
        "fa_notes_rows": counts.get("fa_notes", 0),
        "failure_count": len(failures),
        "failure_json": json.dumps(failures[:200], ensure_ascii=False),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Resumable full-universe Vietcap FA batch ingester.")
    parser.add_argument("--questdb-url", default=qdb.DEFAULT_QUESTDB_URL)
    parser.add_argument("--run-id", help="Resume/extend a specific run_id (else resume latest in_progress or start new).")
    parser.add_argument("--new-run", action="store_true", help="Force a brand-new run_id instead of resuming.")
    parser.add_argument("--universe-file", help="Optional newline-separated symbol file (default: full securities universe).")
    parser.add_argument("--statements", default="balance_sheet,income_statement,cash_flow,notes")
    parser.add_argument("--max-symbols", type=int, default=0, help="Max symbols to attempt this pass (0 = all remaining).")
    parser.add_argument("--retry-failed", action="store_true", help="Also reprocess attempted symbols with no balance-sheet rows.")
    parser.add_argument("--cooldown-seconds", type=float, default=1.0, help="Sleep between symbols.")
    parser.add_argument("--rate-limit-stop-after", type=int, default=8, help="Stop the pass after N consecutive rate-limited sections.")
    parser.add_argument("--cooldown-after-http-failures", type=int, default=0, help="Sleep cooldown-seconds after N consecutive HTTP 503/429 failures (0 = disabled).")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--plan-only", action="store_true", help="Print the plan (no network, no writes) and exit.")
    parser.add_argument("--symbols", help="Operator smoke/test override: comma-separated symbols (skips universe lookup).")
    parser.add_argument("--start-index", type=int, default=0, help="Slice the selected symbol list starting at this index (0-based).")
    parser.add_argument("--only-missing", action="store_true", help="Skip symbols already covered in FA fact tables globally.")
    parser.add_argument("--resume", action="store_true", help="Skip symbols already attempted (raw_payload row) in this run_id.")
    parser.add_argument("--sleep-seconds", type=float, default=None, help="Override --cooldown-seconds (sleep between symbols).")
    parser.add_argument("--jitter-seconds", type=float, default=0.0, help="Extra random jitter added to --sleep-seconds per symbol.")
    parser.add_argument("--max-consecutive-failures", type=int, default=0, help="Stop the pass after N consecutive failed symbols (0 = disabled).")
    parser.add_argument("--stop-on-rate-limit", action="store_true", help="Stop the pass cleanly on rate-limit style failures.")
    parser.add_argument("--count-zero-facts-as-failure", action="store_true", help="Count zero-fact symbols (http=200, no rows) toward --max-consecutive-failures. Default: they are skipped.")
    parser.add_argument("--write-summary-json", help="Write a compact summary JSON to this path (e.g. data/cache/...json). Not staged.")
    args = parser.parse_args()

    try:
        statements = _parse_statements(args.statements)
    except ValueError as exc:
        parser.error(str(exc))
    base_url = args.questdb_url.rstrip("/")

    # Operator smoke/test override: explicit symbol list skips the universe lookup.
    explicit_symbols: list[str] | None = None
    if args.symbols:
        explicit_symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        explicit_symbols = [s for s in dict.fromkeys(explicit_symbols) if SYMBOL_RE.fullmatch(s)]
        if not explicit_symbols:
            print("error=empty --symbols list", file=sys.stderr)
            return 2

    with qdb.open_client(timeout_seconds=300.0) as client:
        universe = explicit_symbols or _load_universe(client, base_url, args.universe_file)
        if not universe:
            print("error=empty universe (no securities rows and no --universe-file/--symbols)", file=sys.stderr)
            return 2

        # Resolve run_id: explicit > resume latest in_progress > new.
        if args.run_id:
            run_id = args.run_id
        elif not args.new_run and (existing := _latest_in_progress_run(client, base_url)):
            run_id = existing
        else:
            run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        is_new = not args.run_id and (args.new_run or _latest_in_progress_run(client, base_url) != run_id)

        # Per-run (run-scoped) attempted set: anything we recorded a raw_payload for.
        attempted = _distinct_symbols(client, base_url, "fa_raw_payloads", run_id)
        # Per-run covered set: anything that produced at least one balance-sheet row.
        covered = _distinct_symbols(client, base_url, "fa_balance_sheet", run_id)
        # Global covered set across all run_ids (used by --only-missing).
        globally_covered = _distinct_symbols(client, base_url, "fa_balance_sheet", "*")
        # SYMBOL_RE is a path-level import; defend in case it is missing.
        try:
            sym_re = SYMBOL_RE
        except NameError:
            from ingest_vietcap_financial_reports_to_questdb import SYMBOL_RE as sym_re  # type: ignore
        universe = [s for s in universe if sym_re.fullmatch(s)]

        # Combine flags. The default skips symbols already attempted in this run_id
        # (so a re-run is a no-op for that run). --only-missing additionally drops
        # symbols already covered in ANY run. --retry-failed forces re-attempts of
        # symbols without balance-sheet rows in this run. --resume is the default
        # skip-already-attempted behaviour; the flag is kept for explicit clarity.
        skip_attempted = args.retry_failed or args.resume or not args.only_missing
        remaining = list(universe)
        if skip_attempted and not args.retry_failed:
            remaining = [s for s in remaining if s not in attempted]
        if args.only_missing:
            remaining = [s for s in remaining if s not in globally_covered]
        if args.retry_failed:
            # Only retry symbols that were attempted but produced no balance-sheet
            # rows in this run. (i.e. attempted and not covered.)
            remaining = [s for s in remaining if s in attempted and s not in covered]

        # Optional positional slice into the remaining list.
        if args.start_index and args.start_index > 0:
            remaining = remaining[args.start_index:]
        cap = args.max_symbols if args.max_symbols and args.max_symbols > 0 else len(remaining)
        todo = remaining[:cap]

        print(f"run_id={run_id} new_run={is_new}")
        print(f"universe={len(universe)} attempted={len(attempted)} covered_bs={len(covered)} "
              f"globally_covered_bs={len(globally_covered)} remaining={len(remaining)} this_pass={len(todo)}")
        # Build resume command early so plan-only can print it.
        sleep_secs = args.sleep_seconds if args.sleep_seconds is not None else args.cooldown_seconds
        _resume_parts = [
            "python scripts\\batch_ingest_vietcap_fa_full_universe.py",
            f"--run-id {run_id}",
            f"--max-symbols {args.max_symbols}",
        ]
        if args.only_missing:
            _resume_parts.append("--only-missing")
        if args.resume:
            _resume_parts.append("--resume")
        if sleep_secs and sleep_secs != 1.0:
            _resume_parts.append(f"--sleep-seconds {sleep_secs}")
        if args.jitter_seconds > 0:
            _resume_parts.append(f"--jitter-seconds {args.jitter_seconds}")
        if args.stop_on_rate_limit:
            _resume_parts.append("--stop-on-rate-limit")
        if args.max_consecutive_failures > 0:
            _resume_parts.append(f"--max-consecutive-failures {args.max_consecutive_failures}")
        if args.count_zero_facts_as_failure:
            _resume_parts.append("--count-zero-facts-as-failure")
        if args.cooldown_after_http_failures > 0:
            _resume_parts.append(f"--cooldown-after-http-failures {args.cooldown_after_http_failures}")
        if args.write_summary_json:
            _resume_parts.append(f"--write-summary-json {args.write_summary_json}")
        resume_command = " ".join(_resume_parts)
        if args.plan_only:
            preview = ",".join(todo[:20]) + ("..." if len(todo) > 20 else "")
            print(f"plan_preview={preview}")
            print(f"resume_command={resume_command}")
            return 0

        _ensure_tables(client, base_url)
        if is_new:
            _write_run_row(client, base_url, _progress_row(
                run_id=run_id, statements=statements, status="in_progress", attempted=len(attempted),
                counts={t: _table_count(client, base_url, t, run_id) for t in (*FA_FACT_TABLES, "fa_raw_payloads")},
                failures=[],
            ))

        failures: list[dict] = []
        zero_facts_samples: list[str] = []
        raw_rows: list[dict] = []
        consecutive_rate_limited = 0
        consecutive_failures = 0
        processed_this_pass = 0
        stopped_for_rate_limit = False
        stopped_for_failures = False
        zero_facts_count = 0
        http_failures_count = 0
        rate_limit_failures_count = 0
        latest_processed_symbol: str | None = None
        sleep_seconds = args.sleep_seconds if args.sleep_seconds is not None else args.cooldown_seconds
        count_zero_facts = args.count_zero_facts_as_failure
        for symbol in todo:
            symbol_rate_limited = False
            symbol_http_failed = False  # any section had http error or non-verified
            symbol_had_parser_errors = False
            section_row_counts: list[int] = []  # row count per section, in order
            for _, section, table in statements:
                result = _fetch_with_retry(symbol, section, run_id, RAW_ROOT, args.timeout_seconds, args.retries)
                http = result.get("http_status")
                raw_rows.append({
                    "crawled_at": result.get("crawled_at") or _utc_timestamp(),
                    "symbol": symbol, "statement_type": section, "source": "vietcap_iq", "run_id": run_id,
                    "raw_payload_ref": result.get("raw_path") or "", "metadata_ref": result.get("metadata_path") or "",
                    "http_status": http or "", "access_status": result.get("access_status") or "",
                    "content_hash": result.get("content_hash") or "",
                    "quality_status": "raw_verified" if result.get("access_status") == "verified" else "fetch_failed",
                })
                if http == 429:
                    symbol_rate_limited = True
                if result.get("access_status") != "verified" or not result.get("raw_path"):
                    failures.append({"symbol": symbol, "section": section, "status": result.get("access_status"), "http": http})
                    symbol_http_failed = True
                    section_row_counts.append(0)
                    continue
                try:
                    facts, errors, _stats = parse_payload(result)
                except Exception as exc:
                    facts, errors = [], [{"kind": "parser_error", "message": f"{type(exc).__name__}: {exc}"}]
                    symbol_had_parser_errors = True
                if errors:
                    for err in errors[:3]:
                        failures.append({"symbol": symbol, "section": section, **err})
                    symbol_had_parser_errors = True
                rows = _normalize_facts(facts, table, run_id)
                if rows:
                    qdb.imp_csv(client, base_url, table, _csv_bytes(rows, FA_COLUMNS), timeout_seconds=180.0)
                    qdb.wait_wal_applied(client, base_url, table, attempts=240)
                section_row_counts.append(len(rows))
                print(f"symbol={symbol} section={section} facts={len(rows)} http={http}")
            # Symbol-level classification after all sections processed.
            total_rows = sum(section_row_counts)
            # zero_fact: all sections were verified+fetched (no http failure) but total rows = 0
            symbol_zero_fact = (not symbol_http_failed and total_rows == 0)
            # symbol_http_failed already set; parser errors on top of successful fetch don't
            # make it a zero_fact (the payload was valid but empty).
            symbol_consec_failed = symbol_http_failed or (symbol_zero_fact and count_zero_facts)
            consecutive_failures = consecutive_failures + 1 if symbol_consec_failed else 0
            if symbol_zero_fact and not count_zero_facts:
                zero_facts_samples.append(symbol)
                zero_facts_count += 1
            if symbol_http_failed:
                http_failures_count += 1
            if symbol_rate_limited:
                rate_limit_failures_count += 1
            # Cooldown after consecutive HTTP failures.
            if args.cooldown_after_http_failures > 0 and consecutive_failures >= args.cooldown_after_http_failures:
                cooldown = args.cooldown_seconds
                print(f"cooldown_http reason=consecutive_http_failures count={consecutive_failures} sleeping={cooldown}s")
                time.sleep(cooldown)
                consecutive_failures = 0
            processed_this_pass += 1
            latest_processed_symbol = symbol
            consecutive_rate_limited = consecutive_rate_limited + 1 if symbol_rate_limited else 0
            if args.stop_on_rate_limit and symbol_rate_limited and consecutive_rate_limited >= args.rate_limit_stop_after:
                stopped_for_rate_limit = True
                print(f"stopping_pass reason=rate_limit consecutive={consecutive_rate_limited}")
                break
            if args.max_consecutive_failures > 0 and consecutive_failures >= args.max_consecutive_failures:
                stopped_for_failures = True
                print(f"stopping_pass reason=consecutive_failures consecutive={consecutive_failures}")
                break
            if sleep_seconds and sleep_seconds > 0:
                jitter = random.uniform(0.0, args.jitter_seconds) if args.jitter_seconds > 0 else 0.0
                time.sleep(sleep_seconds + jitter)

        if raw_rows:
            qdb.imp_csv(client, base_url, "fa_raw_payloads", _csv_bytes(raw_rows, RAW_COLUMNS), timeout_seconds=120.0)
            qdb.wait_wal_applied(client, base_url, "fa_raw_payloads", attempts=240)

        attempted_after = _distinct_symbols(client, base_url, "fa_raw_payloads", run_id)
        covered_after = _distinct_symbols(client, base_url, "fa_balance_sheet", run_id)
        counts = {t: _table_count(client, base_url, t, run_id) for t in (*FA_FACT_TABLES, "fa_raw_payloads")}
        all_attempted = len(attempted_after) >= len(universe)
        status = "complete" if all_attempted else "in_progress"
        # Actual coverage snapshot from QuestDB (authoritative — reflects all runs even after interrupt).
        # Must be computed inside the client context.
        actual_bs_syms = _distinct_symbols(client, base_url, "fa_balance_sheet", "*")
        actual_is_syms = _distinct_symbols(client, base_url, "fa_income_statement", "*")
        actual_cf_syms = _distinct_symbols(client, base_url, "fa_cash_flow", "*")
        actual_note_syms = _distinct_symbols(client, base_url, "fa_notes", "*")
        actual_all4 = actual_bs_syms & actual_is_syms & actual_cf_syms & actual_note_syms
        remaining_globally = len(universe) - len(actual_all4)
        _write_run_row(client, base_url, _progress_row(
            run_id=run_id, statements=statements, status=status,
            attempted=len(attempted_after), counts=counts, failures=failures,
        ))

    print(f"pass_processed={processed_this_pass} stopped_for_rate_limit={stopped_for_rate_limit} stopped_for_failures={stopped_for_failures}")
    print(f"run_status={status}")
    print(f"universe={len(universe)} attempted={len(attempted_after)} covered_bs={len(covered_after)} remaining={len(universe) - len(attempted_after)}")
    print(f"latest_processed_symbol={latest_processed_symbol or ''}")
    for table in (*FA_FACT_TABLES, "fa_raw_payloads"):
        print(f"{table}_rows_run={counts[table]}")
    print(f"failures_this_pass={len(failures)}")
    print(f"zero_facts_this_pass={zero_facts_count}")
    print(f"http_failures_this_pass={http_failures_count}")
    print(f"rate_limit_failures_this_pass={rate_limit_failures_count}")
    # Build the resume command with the current option set so a copy-paste always works.
    resume_parts = [
        "python scripts\\batch_ingest_vietcap_fa_full_universe.py",
        f"--run-id {run_id}",
        f"--max-symbols {args.max_symbols}",
    ]
    if args.only_missing:
        resume_parts.append("--only-missing")
    if args.resume:
        resume_parts.append("--resume")
    if sleep_seconds and sleep_seconds != 1.0:
        resume_parts.append(f"--sleep-seconds {sleep_seconds}")
    if args.jitter_seconds > 0:
        resume_parts.append(f"--jitter-seconds {args.jitter_seconds}")
    if args.stop_on_rate_limit:
        resume_parts.append("--stop-on-rate-limit")
    if args.max_consecutive_failures > 0:
        resume_parts.append(f"--max-consecutive-failures {args.max_consecutive_failures}")
    if args.count_zero_facts_as_failure:
        resume_parts.append("--count-zero-facts-as-failure")
    if args.cooldown_after_http_failures > 0:
        resume_parts.append(f"--cooldown-after-http-failures {args.cooldown_after_http_failures}")
    if args.write_summary_json:
        resume_parts.append(f"--write-summary-json {args.write_summary_json}")
    resume_command = " ".join(resume_parts)
    if not all_attempted:
        print(f"resume_command={resume_command}")
    else:
        print(f"run_complete=true run_id={run_id} (FA tools will now use this run)")

    if args.write_summary_json:
        try:
            from pathlib import Path
            target = Path(args.write_summary_json)
            target.parent.mkdir(parents=True, exist_ok=True)
            # Detect whether pass ran any symbols.
            completed_normally = processed_this_pass > 0
            # interrupted only if we processed symbols but didn't reach the summary write
            # (the raw_rows write above succeeded, but a subsequent kill left pass_processed stale).
            interrupted = completed_normally and (
                len(attempted_after) == len(attempted) and
                latest_processed_symbol != "" and
                latest_processed_symbol not in universe[-1:]
            )
            payload = {
                "generated_at": _utc_timestamp(),
                "run_id": run_id,
                "run_status": status,
                "completed_normally": completed_normally,
                "interrupted": interrupted,
                "pass_processed": processed_this_pass,
                "latest_processed_symbol": latest_processed_symbol or "",
                "stopped_for_rate_limit": stopped_for_rate_limit,
                "stopped_for_failures": stopped_for_failures,
                "universe": len(universe),
                "attempted": len(attempted_after),
                "covered_bs": len(covered_after),
                "remaining": remaining_globally,
                "row_counts_run": counts,
                "failures_this_pass": len(failures),
                "zero_facts_this_pass": zero_facts_count,
                "http_failures_this_pass": http_failures_count,
                "rate_limit_failures_this_pass": rate_limit_failures_count,
                "failure_samples": failures[:50],
                "zero_facts_samples": zero_facts_samples[:50],
                "actual_coverage_snapshot": {
                    "bs_symbols": len(actual_bs_syms),
                    "is_symbols": len(actual_is_syms),
                    "cf_symbols": len(actual_cf_syms),
                    "note_symbols": len(actual_note_syms),
                    "all4_symbols": len(actual_all4),
                    "remaining_globally": remaining_globally,
                },
                "resume_command": resume_command,
            }
            target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"summary_written={target}")
        except Exception as exc:
            print(f"summary_write_error={type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
