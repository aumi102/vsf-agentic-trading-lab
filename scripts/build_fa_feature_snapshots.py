"""Build fa_feature_snapshots from already-source-backed FA fact rows.

Source of truth: the candidate inspection report
(scripts/inspect_fa_feature_candidates.py). We only compute features whose
source metric codes are reported READY there. This keeps features source-backed
and never invents metric names.

Target table: fa_feature_snapshots
Safe fields:
  - symbol
  - as_of_date (public_date of the latest period covered)
  - statement_date (period_to / period_end if present)
  - period_type
  - revenue_yoy               (latest / prior-year-same-period, when both exist)
  - net_profit_yoy            (same convention)
  - equity_latest
  - operating_cashflow_latest
  - data_quality_status
  - source_run_id
  - source_metric_codes       (codes actually aggregated)
  - source_metric_names       (English names actually aggregated)
  - last_built_at
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (str(SRC), str(ROOT / "scripts"), str(ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from trading_agent.storage import questdb_client as qdb  # noqa: E402

TARGET_TABLE = "fa_feature_snapshots"
COLUMNS = [
    "symbol", "as_of_date", "statement_date", "period_type",
    "revenue_yoy", "net_profit_yoy", "equity_latest", "operating_cashflow_latest",
    "data_quality_status", "source_run_id", "source_metric_codes", "source_metric_names",
    "last_built_at",
]

# Feature definitions. Each feature aggregates the listed metric_codes to a single
# value per (symbol, period_type, year). The aggregation is "sum across all
# matched codes for that period" because Vietcap often splits the same logical
# metric into multiple granular codes; summing those granular codes reconstructs
# the headline number.
FEATURES: list[dict] = [
    {
        "field": "revenue_yoy",
        "family": "INCOME_STATEMENT",
        "patterns": [r"\brevenue\b", r"^net sales$", r"^net revenue$", r"^sales\b", r"\bdoanh thu\b"],
    },
    {
        "field": "net_profit_yoy",
        "family": "INCOME_STATEMENT",
        "patterns": [r"net profit", r"profit after tax", r"profit for the year", r"\bnet income\b",
                     r"\blợi nhuận sau thuế\b"],
    },
    {
        "field": "equity_latest",
        "family": "BALANCE_SHEET",
        "patterns": [r"^equity$", r"total equity", r"owners' equity", r"shareholders' equity",
                     r"vốn chủ sở hữu"],
    },
    {
        "field": "operating_cashflow_latest",
        "family": "CASH_FLOW",
        "patterns": [r"operating cash flow", r"cash from operating", r"net cash.*operating",
                     r"lưu chuyển tiền.*hoạt động"],
    },
]


def _table_exists(client, base_url: str, table: str) -> bool:
    _, rows = qdb.exec_rows(client, base_url, "SHOW TABLES")
    return table in {str(row[0]) for row in rows if row}


def _csv_bytes(rows: list[dict], columns: list[str]) -> bytes:
    """Tiny CSV writer (RFC4180-ish) to avoid pulling in pandas."""
    import csv
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    for r in rows:
        w.writerow({c: r.get(c, "") for c in columns})
    return buf.getvalue().encode("utf-8")


def _resolve_codes(client, base_url: str) -> dict[str, list[str]]:
    """Resolve each feature to its concrete metric_code list (consensus only)."""
    import re
    rows = qdb.exec_rows(
        client, base_url,
        "SELECT metric_code, metric_name_en, statement_type FROM fa_metric_mapping "
        "WHERE quality_status = 'source_backed_consensus' "
        "AND metric_name_en IS NOT NULL AND metric_name_en != ''",
    )[1]
    out: dict[str, list[str]] = {}
    for r in rows:
        if len(r) < 3:
            continue
        code, name, family = str(r[0]), str(r[1] or ""), str(r[2] or "")
        for f in FEATURES:
            if family != f["family"]:
                continue
            if any(re.search(p, name, re.IGNORECASE) for p in f["patterns"]):
                out.setdefault(f["field"], []).append(code)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Build fa_feature_snapshots (source-backed).")
    parser.add_argument("--questdb-url", default=qdb.DEFAULT_QUESTDB_URL)
    parser.add_argument("--source-run-id", required=True, help="run_id to source from (fa_ingest_runs).")
    parser.add_argument("--dry-run", action="store_true", help="Print plan only, do not write.")
    args = parser.parse_args()
    base_url = args.questdb_url.rstrip("/")

    with qdb.open_client(timeout_seconds=300.0) as client:
        codes_by_field = _resolve_codes(client, base_url)
        if not codes_by_field:
            print("error=no source-backed metric codes resolved; defer feature build", file=sys.stderr)
            return 2

        for fam in ("fa_balance_sheet", "fa_income_statement", "fa_cash_flow", "fa_notes"):
            if not _table_exists(client, base_url, fam):
                print(f"error=missing FA family table {fam}", file=sys.stderr)
                return 2

        if args.dry_run:
            print(json.dumps({"resolved": codes_by_field, "target": TARGET_TABLE, "columns": COLUMNS},
                             indent=2, ensure_ascii=False))
            return 0

        family_table = {"BALANCE_SHEET": "fa_balance_sheet", "INCOME_STATEMENT": "fa_income_statement",
                        "CASH_FLOW": "fa_cash_flow", "NOTE": "fa_notes"}
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        out_rows: list[dict] = []

        # Pull per-(symbol, period_type, year) sums for each feature. Then collapse
        # to per-symbol latest values.
        per_symbol: dict[str, dict] = {}
        for f in FEATURES:
            codes = codes_by_field.get(f["field"]) or []
            if not codes:
                continue
            code_list = ",".join(f"'{c}'" for c in codes)
            sql = (
                f"SELECT symbol, period_type, year(public_date) yr, "
                f"sum(metric_value) FROM {family_table[f['family']]} "
                f"WHERE run_id = '{args.source_run_id}' AND metric_code IN ({code_list}) "
                f"AND metric_value IS NOT NULL "
                f"GROUP BY symbol, period_type, year(public_date)"
            )
            _, rows = qdb.exec_rows(client, base_url, sql)
            # Index: (symbol, period_type, year) -> sum
            agg: dict[tuple[str, str, int], float] = {}
            for r in rows:
                if not r or r[0] is None:
                    continue
                sym, pt, yr, total = str(r[0]), str(r[1] or ""), int(r[2] or 0), float(r[3] or 0.0)
                agg[(sym, pt, yr)] = total
            # Compute yoy for income-statement features, latest for the others.
            if f["field"].endswith("_yoy"):
                # For each (symbol, period_type), find the latest year with data and
                # the previous-year same period. If both exist, ratio - 1.
                by_key: dict[tuple[str, str], list[tuple[int, float]]] = {}
                for (sym, pt, yr), val in agg.items():
                    by_key.setdefault((sym, pt), []).append((yr, val))
                for (sym, pt), years in by_key.items():
                    years.sort(reverse=True)
                    if not years:
                        continue
                    latest_yr, latest_val = years[0]
                    prev = next((v for y, v in years if y == latest_yr - 1), None)
                    if prev is None or prev == 0:
                        continue
                    yoy = (latest_val / prev) - 1.0
                    row = per_symbol.setdefault(sym, {"symbol": sym})
                    row[f["field"]] = round(yoy, 6)
                    row.setdefault("statement_date", str(latest_yr))
                    row.setdefault("period_type", pt)
            else:
                # Latest per (symbol, period_type).
                by_key: dict[tuple[str, str], list[tuple[int, float]]] = {}
                for (sym, pt, yr), val in agg.items():
                    by_key.setdefault((sym, pt), []).append((yr, val))
                for (sym, pt), years in by_key.items():
                    years.sort(reverse=True)
                    if not years:
                        continue
                    latest_yr, latest_val = years[0]
                    row = per_symbol.setdefault(sym, {"symbol": sym})
                    row[f["field"]] = round(latest_val, 6)
                    row.setdefault("statement_date", str(latest_yr))
                    row.setdefault("period_type", pt)

        for sym, row in per_symbol.items():
            row["as_of_date"] = row.get("statement_date", "")
            row["data_quality_status"] = "source_backed_consensus"
            row["source_run_id"] = args.source_run_id
            row["source_metric_codes"] = ";".join(
                code for f in FEATURES if (codes := codes_by_field.get(f["field"])) for code in codes
            )
            row["source_metric_names"] = ";".join(f["field"] for f in FEATURES if codes_by_field.get(f["field"]))
            row["last_built_at"] = now_iso
            out_rows.append(row)

        # Ensure target table (CREATE TABLE IF NOT EXISTS).
        if not _table_exists(client, base_url, TARGET_TABLE):
            ddl = (
                f"CREATE TABLE IF NOT EXISTS {TARGET_TABLE} ("
                f"symbol SYMBOL, as_of_date SYMBOL, statement_date SYMBOL, period_type SYMBOL, "
                f"revenue_yoy DOUBLE, net_profit_yoy DOUBLE, equity_latest DOUBLE, "
                f"operating_cashflow_latest DOUBLE, data_quality_status SYMBOL, "
                f"source_run_id SYMBOL, source_metric_codes STRING, source_metric_names STRING, "
                f"last_built_at TIMESTAMP"
                f") timestamp(last_built_at) PARTITION BY NONE"
            )
            qdb.exec_query(client, base_url, ddl)

        if out_rows:
            qdb.imp_csv(client, base_url, TARGET_TABLE, _csv_bytes(out_rows, COLUMNS), timeout_seconds=180.0)
            qdb.wait_wal_applied(client, base_url, TARGET_TABLE, attempts=120)

        print(f"symbol_count={len(out_rows)} target={TARGET_TABLE} source_run_id={args.source_run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
