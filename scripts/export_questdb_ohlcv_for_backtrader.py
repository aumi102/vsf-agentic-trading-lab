"""Export QuestDB daily_prices OHLCV to a Backtrader-compatible CSV.

Read-only by design: this script only SELECTs from QuestDB and writes local
cache files under a caller-provided path.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.storage import questdb_client as qdb  # noqa: E402

DEFAULT_URL = qdb.DEFAULT_QUESTDB_URL
DEFAULT_TABLE = "daily_prices"
SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,12}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ADJUSTED_COLUMNS = ["adjusted_open", "adjusted_high", "adjusted_low", "adjusted_close"]
RAW_COLUMNS = ["open", "high", "low", "close"]
CSV_COLUMNS = ["datetime", "open", "high", "low", "close", "volume", "openinterest"]


@dataclass(frozen=True)
class ExportResult:
    symbol: str
    path: Path
    rows: int
    first_date: str
    last_date: str
    used_adjusted: bool
    caveats: tuple[str, ...]


def parse_symbols(raw: str | None) -> list[str]:
    if not raw:
        return []
    symbols = list(dict.fromkeys(part.strip().upper() for part in raw.split(",") if part.strip()))
    invalid = [symbol for symbol in symbols if not SYMBOL_RE.fullmatch(symbol)]
    if invalid:
        raise ValueError(f"invalid symbols: {', '.join(invalid)}")
    return symbols


def validate_date(value: str, name: str) -> str:
    if not DATE_RE.fullmatch(value or ""):
        raise ValueError(f"{name} must be YYYY-MM-DD")
    return value


def _rows_to_dicts(columns: list[str], dataset: list[list[Any]]) -> list[dict[str, Any]]:
    return [dict(zip(columns, row)) for row in dataset]


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date_only(value: Any) -> str:
    text = str(value or "")
    return text[:10]


def _select_price_columns(columns: set[str]) -> tuple[bool, list[str], list[str]]:
    has_adjusted = all(col in columns for col in ADJUSTED_COLUMNS)
    if has_adjusted:
        return True, ADJUSTED_COLUMNS, ["using adjusted_open/high/low/close from daily_prices"]
    return False, RAW_COLUMNS, ["adjusted OHLC columns unavailable; using raw open/high/low/close"]


def _build_sql(symbol: str, start_date: str, end_date: str, table: str, columns: set[str]) -> tuple[str, bool, list[str]]:
    used_adjusted, price_columns, caveats = _select_price_columns(columns)
    quality_filter = " AND quality_status = 'pass'" if "quality_status" in columns else ""
    select_parts = [
        "trade_date",
        f"{price_columns[0]} AS bt_open",
        f"{price_columns[1]} AS bt_high",
        f"{price_columns[2]} AS bt_low",
        f"{price_columns[3]} AS bt_close",
        "volume",
        "adjustment_status" if "adjustment_status" in columns else "'' AS adjustment_status",
    ]
    if used_adjusted:
        select_parts.extend([
            "open AS raw_open",
            "high AS raw_high",
            "low AS raw_low",
            "close AS raw_close",
        ])
    sql = (
        f"SELECT {', '.join(select_parts)} FROM {table} "
        f"WHERE symbol = '{symbol}' "
        f"AND trade_date >= '{start_date}' "
        f"AND trade_date <= '{end_date}T23:59:59.999999Z'"
        f"{quality_filter} ORDER BY trade_date ASC"
    )
    if quality_filter:
        caveats.append("filtered to quality_status='pass'")
    return sql, used_adjusted, caveats


def _validate_export_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    invalid: list[str] = []
    for index, row in enumerate(rows, start=1):
        dt = _date_only(row.get("trade_date"))
        open_ = _float_or_none(row.get("bt_open"))
        high = _float_or_none(row.get("bt_high"))
        low = _float_or_none(row.get("bt_low"))
        close = _float_or_none(row.get("bt_close"))
        volume = _float_or_none(row.get("volume"))
        if None in (open_, high, low, close, volume):
            invalid.append(f"row={index} date={dt} has null/non-numeric OHLCV")
            continue
        assert open_ is not None and high is not None and low is not None and close is not None and volume is not None
        if high + 1e-9 < max(open_, close):
            invalid.append(f"row={index} date={dt} high below open/close")
            continue
        if low - 1e-9 > min(open_, close):
            invalid.append(f"row={index} date={dt} low above open/close")
            continue
        if volume < 0:
            invalid.append(f"row={index} date={dt} negative volume")
            continue
        out.append({
            "datetime": dt,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "openinterest": 0,
        })
    if invalid:
        preview = "; ".join(invalid[:5])
        raise ValueError(f"OHLCV validation failed for {len(invalid)} rows: {preview}")
    return out


def _adjustment_caveats(rows: list[dict[str, Any]], used_adjusted: bool) -> list[str]:
    caveats: list[str] = []
    statuses = sorted({str(row.get("adjustment_status") or "") for row in rows if row.get("adjustment_status")})
    warn_statuses = [status for status in statuses if "adjusted_price_missing_warn" in status]
    if warn_statuses:
        caveats.append("adjustment_status includes adjusted_price_missing_warn; adjusted OHLC source remains unverified")
    if used_adjusted and rows:
        compared = 0
        equal = 0
        for row in rows:
            pairs = [
                (row.get("bt_open"), row.get("raw_open")),
                (row.get("bt_high"), row.get("raw_high")),
                (row.get("bt_low"), row.get("raw_low")),
                (row.get("bt_close"), row.get("raw_close")),
            ]
            for adjusted, raw in pairs:
                a = _float_or_none(adjusted)
                r = _float_or_none(raw)
                if a is None or r is None:
                    continue
                compared += 1
                if abs(a - r) <= 1e-9:
                    equal += 1
        if compared and compared == equal:
            caveats.append("adjusted OHLC equals raw OHLC for exported rows; adjustment factor appears to be 1.0")
    return caveats


def export_symbol_to_csv(
    *,
    symbol: str,
    start_date: str,
    end_date: str,
    out_path: Path,
    questdb_url: str = DEFAULT_URL,
    table: str = DEFAULT_TABLE,
) -> ExportResult:
    symbol = symbol.strip().upper()
    if not SYMBOL_RE.fullmatch(symbol):
        raise ValueError(f"invalid symbol: {symbol!r}")
    validate_date(start_date, "start_date")
    validate_date(end_date, "end_date")
    base = questdb_url.rstrip("/")
    with qdb.open_client(timeout_seconds=120.0) as client:
        columns = set(qdb.column_names(client, base, table))
        if not columns:
            raise RuntimeError(f"QuestDB table not found or has no columns: {table}")
        sql, used_adjusted, caveats = _build_sql(symbol, start_date, end_date, table, columns)
        result_columns, dataset = qdb.exec_rows(client, base, sql)
    raw_rows = _rows_to_dicts(result_columns, dataset)
    export_rows = _validate_export_rows(raw_rows)
    caveats.extend(_adjustment_caveats(raw_rows, used_adjusted))
    if not export_rows:
        raise RuntimeError(f"no exportable rows for {symbol} from {start_date} to {end_date}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(export_rows)
    return ExportResult(
        symbol=symbol,
        path=out_path,
        rows=len(export_rows),
        first_date=str(export_rows[0]["datetime"]),
        last_date=str(export_rows[-1]["datetime"]),
        used_adjusted=used_adjusted,
        caveats=tuple(dict.fromkeys(caveats)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Export QuestDB daily_prices data for Backtrader.")
    parser.add_argument("--questdb-url", default=DEFAULT_URL)
    parser.add_argument("--table", default=DEFAULT_TABLE)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--symbol")
    group.add_argument("--symbols")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--out")
    parser.add_argument("--out-dir", default="data/cache/backtrader")
    args = parser.parse_args()
    try:
        validate_date(args.start_date, "start_date")
        validate_date(args.end_date, "end_date")
        symbols = parse_symbols(args.symbol or args.symbols)
        if args.symbol and args.out:
            outputs = [Path(args.out)]
        elif args.symbol:
            outputs = [Path(args.out_dir) / f"backtrader_{symbols[0]}.csv"]
        else:
            if args.out:
                parser.error("--out is only valid with --symbol; use --out-dir for --symbols")
            outputs = [Path(args.out_dir) / f"backtrader_{symbol}.csv" for symbol in symbols]
        for symbol, out_path in zip(symbols, outputs):
            result = export_symbol_to_csv(
                symbol=symbol,
                start_date=args.start_date,
                end_date=args.end_date,
                out_path=out_path,
                questdb_url=args.questdb_url,
                table=args.table,
            )
            print(
                f"symbol={result.symbol} rows_exported={result.rows} "
                f"date_range={result.first_date}..{result.last_date} path={result.path}"
            )
            print(f"used_adjusted_ohlc={result.used_adjusted}")
            for caveat in result.caveats:
                print(f"caveat={caveat}")
    except Exception as exc:
        print(f"error={type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
