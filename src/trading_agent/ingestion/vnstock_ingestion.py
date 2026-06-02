from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

from trading_agent.data_sources.vnstock_client import FetchResult, VnstockClient
from trading_agent.ingestion.contracts import (
    CORPORATE_EVENTS_COLUMNS,
    DAILY_PRICES_COLUMNS,
    SCHEMA_VERSION,
    SECURITIES_COLUMNS,
    SOURCE,
    RawRecord,
    first_present,
    get_series,
    make_security_id,
    normalize_exchange,
    normalize_symbol,
    quality_reasons_to_string,
    source_id_for,
)
from trading_agent.quality.checks import QualityResult, check_corporate_events, check_daily_prices, check_securities
from trading_agent.storage.parquet_store import ParquetStore


@dataclass
class InventoryItem:
    dataset: str
    row_count: int
    original_columns: list[str]
    canonical_output_path: str
    status: str
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    symbol: str | None = None


@dataclass
class IngestionResult:
    run_id: str
    inventory: list[InventoryItem]
    quality_results: list[QualityResult]
    outputs: dict[str, str]
    warnings: list[str]


class VnstockIngestion:
    def __init__(
        self,
        client: VnstockClient | None = None,
        raw_base_dir: str | Path = "data/raw/vnstock",
        silver_dir: str | Path = "data/silver",
        reports_dir: str | Path = "reports",
    ) -> None:
        self.client = client or VnstockClient()
        self.raw_base_dir = Path(raw_base_dir)
        self.store = ParquetStore(silver_dir)
        self.reports_dir = Path(reports_dir)

    def run(self, symbols: list[str], start: str, end: str) -> IngestionResult:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        crawled_at = datetime.now(timezone.utc).isoformat()
        inventory: list[InventoryItem] = []
        quality_results: list[QualityResult] = []
        outputs: dict[str, str] = {}
        warnings: list[str] = []

        listing_all = self._fetch_and_save(self.client.get_listing_all_symbols(), run_id, crawled_at, inventory)
        listing_by_exchange = self._fetch_and_save(self.client.get_listing_symbols_by_exchange(), run_id, crawled_at, inventory)

        ohlcv_records = []
        event_records = []
        for symbol in symbols:
            ohlcv_records.append(self._fetch_and_save(self.client.get_ohlcv(symbol, start, end), run_id, crawled_at, inventory))
            event_record = self._fetch_and_save(self.client.get_company_events(symbol), run_id, crawled_at, inventory)
            if event_record is not None:
                event_records.append(event_record)
            else:
                warnings.append(f"company_events unavailable for {symbol}")

        raw_records = [record for record in [listing_all, listing_by_exchange] if record is not None]
        securities = normalize_securities(raw_records, symbols, run_id, crawled_at)
        symbol_exchange = self._symbol_exchange_lookup_from_securities(securities)
        securities_quality = check_securities(securities)
        quality_results.append(securities_quality)
        securities["quality_status"] = securities_quality.quality_status
        securities["quality_reasons"] = quality_reasons_to_string(securities_quality.failed_gates + securities_quality.warning_reasons)
        outputs["securities"] = str(self.store.write("securities", securities[SECURITIES_COLUMNS]))

        daily_prices = normalize_daily_prices([record for record in ohlcv_records if record is not None], symbol_exchange)
        daily_quality = check_daily_prices(daily_prices)
        quality_results.append(daily_quality)
        daily_prices["quality_status"] = daily_quality.quality_status
        daily_prices["quality_reasons"] = quality_reasons_to_string(daily_quality.failed_gates + daily_quality.warning_reasons)
        if not daily_prices.empty:
            outputs["daily_prices"] = str(self.store.write("daily_prices", daily_prices[DAILY_PRICES_COLUMNS]))
        else:
            warnings.append("daily_prices output not written because no OHLCV rows were available")

        corporate_events = normalize_corporate_events(event_records, symbol_exchange)
        if not corporate_events.empty:
            events_quality = check_corporate_events(corporate_events)
            quality_results.append(events_quality)
            corporate_events["quality_status"] = events_quality.quality_status
            corporate_events["quality_reasons"] = quality_reasons_to_string(events_quality.failed_gates + events_quality.warning_reasons)
            outputs["corporate_events"] = str(self.store.write("corporate_events", corporate_events[CORPORATE_EVENTS_COLUMNS]))
        else:
            warnings.append("corporate_events output not written because company_events failed or returned no rows")
            quality_results.append(
                QualityResult(
                    table="corporate_events",
                    row_count=0,
                    quality_status="warn",
                    failed_gates=[],
                    warning_reasons=["company_events_unavailable_or_empty"],
                )
            )

        self._write_inventory_report(run_id, crawled_at, symbols, start, end, inventory, outputs, warnings)
        self._write_quality_report(
            run_id,
            quality_results,
            warnings,
            symbols=symbols,
            securities=securities,
            daily_prices=daily_prices,
        )

        return IngestionResult(run_id=run_id, inventory=inventory, quality_results=quality_results, outputs=outputs, warnings=warnings)

    def _fetch_and_save(
        self,
        result: FetchResult,
        run_id: str,
        crawled_at: str,
        inventory: list[InventoryItem],
    ) -> RawRecord | None:
        if not result.ok:
            inventory.append(
                InventoryItem(
                    dataset=result.dataset,
                    row_count=0,
                    original_columns=[],
                    canonical_output_path="",
                    status="failure",
                    error=result.error,
                    symbol=result.symbol,
                )
            )
            return None

        assert result.data is not None
        source_id = source_id_for(result.dataset, run_id, result.symbol)
        raw_dir = self.raw_base_dir / f"run_id={run_id}" / result.dataset
        if result.symbol:
            raw_dir = raw_dir / f"symbol={result.symbol.upper()}"
        raw_dir.mkdir(parents=True, exist_ok=True)

        raw_csv = raw_dir / "data.csv"
        result.data.to_csv(raw_csv, index=False)
        content_hash = hashlib.sha256(raw_csv.read_bytes()).hexdigest()
        metadata = {
            "dataset": result.dataset,
            "symbol": result.symbol,
            "source": SOURCE,
            "source_id": source_id,
            "crawled_at": crawled_at,
            "original_columns": [str(col) for col in result.data.columns],
            "row_count": len(result.data),
            "content_hash": content_hash,
            "status": result.status,
            "error": result.error,
        }
        (raw_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

        inventory.append(
            InventoryItem(
                dataset=result.dataset,
                row_count=len(result.data),
                original_columns=[str(col) for col in result.data.columns],
                canonical_output_path=str(raw_csv),
                status="success",
                symbol=result.symbol,
            )
        )
        return RawRecord(
            dataset=result.dataset,
            data=result.data,
            source_id=source_id,
            raw_path=str(raw_csv),
            crawled_at=crawled_at,
            original_columns=[str(col) for col in result.data.columns],
        )

    @staticmethod
    def _symbol_exchange_lookup(records: Iterable[RawRecord]) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for record in records:
            if record.data.empty:
                continue
            symbol_col = first_present(record.data, "symbol")
            exchange_col = first_present(record.data, "exchange")
            if not symbol_col:
                continue
            for _, row in record.data.iterrows():
                symbol = normalize_symbol(row.get(symbol_col))
                if not symbol:
                    continue
                exchange = normalize_exchange(row.get(exchange_col)) if exchange_col else "UNKNOWN"
                if symbol not in lookup or lookup[symbol] == "UNKNOWN":
                    lookup[symbol] = exchange
        return lookup

    @staticmethod
    def _symbol_exchange_lookup_from_securities(securities: pd.DataFrame) -> dict[str, str]:
        lookup: dict[str, str] = {}
        if securities.empty:
            return lookup
        ranked = securities.assign(
            exchange_rank=securities["exchange"].map(lambda value: 1 if normalize_exchange(value) != "UNKNOWN" else 0)
        ).sort_values(["symbol", "exchange_rank"], ascending=[True, False])
        for _, row in ranked.iterrows():
            symbol = normalize_symbol(row.get("symbol"))
            if symbol and symbol not in lookup:
                lookup[symbol] = normalize_exchange(row.get("exchange"))
        return lookup

    def _write_inventory_report(
        self,
        run_id: str,
        crawled_at: str,
        symbols: list[str],
        start: str,
        end: str,
        inventory: list[InventoryItem],
        outputs: dict[str, str],
        warnings: list[str],
    ) -> None:
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Data Inventory",
            "",
            f"- run_id: `{run_id}`",
            f"- crawl_time: `{crawled_at}`",
            f"- symbols: `{','.join(symbols)}`",
            f"- date_range: `{start}` to `{end}`",
            "",
            "| Dataset | Symbol | Row count | Original columns | Canonical output/raw path | Status | Warnings/errors |",
            "|---|---|---:|---|---|---|---|",
        ]
        for item in inventory:
            warning_text = item.error or "; ".join(item.warnings)
            lines.append(
                f"| `{item.dataset}` | `{item.symbol or ''}` | {item.row_count} | `{', '.join(item.original_columns)}` | `{item.canonical_output_path}` | `{item.status}` | {warning_text} |"
            )
        lines.extend(["", "## Silver Outputs", ""])
        for name, path in outputs.items():
            lines.append(f"- `{name}` -> `{path}`")
        lines.extend(["", "## Warnings", ""])
        if warnings:
            lines.extend(f"- {warning}" for warning in warnings)
        else:
            lines.append("- none")
        (self.reports_dir / "data_inventory.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_quality_report(
        self,
        run_id: str,
        quality_results: list[QualityResult],
        warnings: list[str],
        symbols: list[str],
        securities: pd.DataFrame,
        daily_prices: pd.DataFrame,
    ) -> None:
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Data Quality Report",
            "",
            f"- run_id: `{run_id}`",
            "",
            "| Table | Row count | Quality status | Failed gates | Warning reasons | Duplicate count | OHLC error count | Missing required columns |",
            "|---|---:|---|---|---|---:|---:|---|",
        ]
        for result in quality_results:
            lines.append(
                f"| `{result.table}` | {result.row_count} | `{result.quality_status}` | `{', '.join(result.failed_gates)}` | `{', '.join(result.warning_reasons)}` | {result.duplicate_count} | {result.ohlc_error_count} | `{', '.join(result.missing_required_columns or [])}` |"
            )
        lines.extend(
            [
                "",
                "## Limitations",
                "",
                "- If `adjusted_close` is missing or unclear, prices may be unadjusted around corporate events.",
                "- If `corporate_events` is unavailable, backtest reports must include the corporate-action limitation.",
            ]
        )
        if warnings:
            lines.extend(f"- {warning}" for warning in warnings)
        lines.extend(["", "## Exchange Distribution", ""])
        lines.extend(_distribution_lines("securities", securities, "exchange"))
        lines.extend(_distribution_lines("daily_prices", daily_prices, "exchange"))
        lines.extend(["", "## Requested Symbol Coverage", ""])
        requested = [normalize_symbol(symbol) or symbol.upper() for symbol in symbols]
        if daily_prices.empty:
            lines.append("- daily_prices: no rows")
        else:
            covered = set(daily_prices["symbol"].dropna().astype(str).str.upper())
            lines.append(f"- requested: `{', '.join(requested)}`")
            lines.append(f"- daily_prices covered: `{', '.join(symbol for symbol in requested if symbol in covered) or 'none'}`")
            missing = [symbol for symbol in requested if symbol not in covered]
            lines.append(f"- daily_prices missing: `{', '.join(missing) if missing else 'none'}`")
            lines.append("")
            lines.append("| Symbol | Min trade_date | Max trade_date | Rows |")
            lines.append("|---|---|---|---:|")
            date_ranges = daily_prices.groupby("symbol", dropna=False)["trade_date"].agg(["min", "max", "count"]).reset_index()
            for _, row in date_ranges.iterrows():
                lines.append(f"| `{row['symbol']}` | `{row['min']}` | `{row['max']}` | {row['count']} |")
        securities_unknown = int((securities.get("exchange", pd.Series(dtype=object)).map(normalize_exchange) == "UNKNOWN").sum()) if not securities.empty else 0
        daily_unknown = int((daily_prices.get("exchange", pd.Series(dtype=object)).map(normalize_exchange) == "UNKNOWN").sum()) if not daily_prices.empty else 0
        lines.extend(
            [
                "",
                "## Warning Explanations",
                "",
                f"- UNKNOWN exchange rows: securities={securities_unknown}, daily_prices={daily_unknown}.",
                "- Remaining securities UNKNOWN rows come from `listing_symbols_by_exchange` rows whose raw `exchange` is missing or not one of HOSE/HNX/UPCOM after normalization. `listing_all_symbols` is now used only as enrichment/fallback and no longer creates duplicate UNKNOWN rows when a known exchange exists for the same symbol.",
                "- `adjusted_close_missing_or_unclear` is a warning, not a blocking failure. Later backtests must include the corporate-action limitation until adjusted prices or event-based adjustment logic are implemented.",
            ]
        )
        (self.reports_dir / "data_quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def normalize_securities(records: list[RawRecord], requested_symbols: list[str], run_id: str, crawled_at: str) -> pd.DataFrame:
    listing_all_by_symbol: dict[str, dict[str, object]] = {}
    exchange_frames = []
    for record in records:
        if record.dataset not in {"listing_all_symbols", "listing_symbols_by_exchange"} or record.data.empty:
            continue
        df = record.data.copy()
        frame = pd.DataFrame(
            {
                "symbol": get_series(df, "symbol").map(normalize_symbol),
                "exchange": get_series(df, "exchange", "UNKNOWN").map(normalize_exchange),
                "company_name": get_series(df, "company_name"),
                "security_type": get_series(df, "security_type"),
                "industry": get_series(df, "industry"),
                "market_cap": pd.to_numeric(get_series(df, "market_cap"), errors="coerce"),
                "foreign_room": pd.to_numeric(get_series(df, "foreign_room"), errors="coerce"),
                "source": SOURCE,
                "source_id": record.source_id,
                "crawled_at": crawled_at,
                "schema_version": SCHEMA_VERSION,
            }
        )
        frame = frame[frame["symbol"].notna()].copy()
        if record.dataset == "listing_all_symbols":
            for _, row in frame.iterrows():
                symbol = str(row["symbol"])
                listing_all_by_symbol.setdefault(symbol, row.to_dict())
        else:
            exchange_frames.append(frame)

    if exchange_frames:
        securities = pd.concat(exchange_frames, ignore_index=True)
        for column in ["company_name", "security_type", "industry", "market_cap", "foreign_room"]:
            securities[column] = securities.apply(
                lambda row, column=column: row[column]
                if pd.notna(row[column])
                else listing_all_by_symbol.get(row["symbol"], {}).get(column),
                axis=1,
            )
    elif listing_all_by_symbol:
        securities = pd.DataFrame(list(listing_all_by_symbol.values()))
    else:
        securities = pd.DataFrame(
            {
                "symbol": [normalize_symbol(symbol) for symbol in requested_symbols],
                "exchange": ["UNKNOWN"] * len(requested_symbols),
                "company_name": [None] * len(requested_symbols),
                "security_type": [None] * len(requested_symbols),
                "industry": [None] * len(requested_symbols),
                "market_cap": [None] * len(requested_symbols),
                "foreign_room": [None] * len(requested_symbols),
                "source": [SOURCE] * len(requested_symbols),
                "source_id": [source_id_for("securities_fallback", run_id)] * len(requested_symbols),
                "crawled_at": [crawled_at] * len(requested_symbols),
                "schema_version": [SCHEMA_VERSION] * len(requested_symbols),
            }
        )

    if listing_all_by_symbol:
        existing_symbols = set(securities["symbol"].dropna())
        missing_listing_rows = [row for symbol, row in listing_all_by_symbol.items() if symbol not in existing_symbols]
        if missing_listing_rows:
            securities = pd.concat([securities, pd.DataFrame(missing_listing_rows)], ignore_index=True)

    requested_known = {normalize_symbol(symbol) for symbol in requested_symbols}
    requested_known.discard(None)
    existing_symbols = set(securities["symbol"].dropna()) if not securities.empty else set()
    missing_requested = [symbol for symbol in requested_known if symbol not in existing_symbols]
    if missing_requested:
        securities = pd.concat(
            [
                securities,
                pd.DataFrame(
                    {
                        "symbol": missing_requested,
                        "exchange": ["UNKNOWN"] * len(missing_requested),
                        "company_name": [None] * len(missing_requested),
                        "security_type": [None] * len(missing_requested),
                        "industry": [None] * len(missing_requested),
                        "market_cap": [None] * len(missing_requested),
                        "foreign_room": [None] * len(missing_requested),
                        "source": [SOURCE] * len(missing_requested),
                        "source_id": [source_id_for("securities_fallback", run_id)] * len(missing_requested),
                        "crawled_at": [crawled_at] * len(missing_requested),
                        "schema_version": [SCHEMA_VERSION] * len(missing_requested),
                    }
                ),
            ],
            ignore_index=True,
        )

    securities["symbol"] = securities["symbol"].map(normalize_symbol)
    securities = securities[securities["symbol"].notna()].copy()
    securities["exchange"] = securities["exchange"].map(normalize_exchange)
    has_known_exchange = securities.groupby("symbol")["exchange"].transform(lambda values: (values != "UNKNOWN").any())
    securities = securities[~((securities["exchange"] == "UNKNOWN") & has_known_exchange)].copy()
    securities["security_id"] = [make_security_id(exchange, symbol) for exchange, symbol in zip(securities["exchange"], securities["symbol"])]
    securities = securities.sort_values(["symbol", "exchange"]).drop_duplicates("security_id", keep="first")
    return securities[SECURITIES_COLUMNS]


def _distribution_lines(table_name: str, df: pd.DataFrame, column: str) -> list[str]:
    if df.empty or column not in df.columns:
        return [f"- {table_name}: no rows"]
    counts = df[column].map(normalize_exchange).value_counts(dropna=False).to_dict()
    formatted = ", ".join(f"{key}={value}" for key, value in counts.items())
    return [f"- {table_name}: {formatted}"]


def normalize_daily_prices(records: list[RawRecord], symbol_exchange: dict[str, str]) -> pd.DataFrame:
    frames = []
    for record in records:
        if record is None or record.data.empty:
            continue
        df = record.data.copy()
        symbol_value = normalize_symbol(record.source_id.split(":")[2]) if len(record.source_id.split(":")) >= 4 else None
        symbol_series = get_series(df, "symbol", symbol_value).map(normalize_symbol)
        symbol_series = symbol_series.fillna(symbol_value)
        exchange_series = symbol_series.map(lambda symbol: symbol_exchange.get(symbol or "", "UNKNOWN")).map(normalize_exchange)
        frame = pd.DataFrame(
            {
                "symbol": symbol_series,
                "exchange": exchange_series,
                "trade_date": pd.to_datetime(get_series(df, "trade_date"), errors="coerce").dt.date,
                "open": pd.to_numeric(get_series(df, "open"), errors="coerce"),
                "high": pd.to_numeric(get_series(df, "high"), errors="coerce"),
                "low": pd.to_numeric(get_series(df, "low"), errors="coerce"),
                "close": pd.to_numeric(get_series(df, "close"), errors="coerce"),
                "volume": pd.to_numeric(get_series(df, "volume"), errors="coerce"),
                "value": pd.to_numeric(get_series(df, "value"), errors="coerce"),
                "adjusted_close": pd.to_numeric(get_series(df, "adjusted_close"), errors="coerce"),
                "source": SOURCE,
                "source_id": record.source_id,
                "raw_path": record.raw_path,
                "crawled_at": record.crawled_at,
                "schema_version": SCHEMA_VERSION,
            }
        )
        frame["security_id"] = [make_security_id(exchange, symbol) for exchange, symbol in zip(frame["exchange"], frame["symbol"])]
        frames.append(frame)

    if not frames:
        return pd.DataFrame(columns=DAILY_PRICES_COLUMNS)
    out = pd.concat(frames, ignore_index=True).sort_values(["security_id", "trade_date"])
    out["quality_status"] = ""
    out["quality_reasons"] = ""
    return out[DAILY_PRICES_COLUMNS]


def normalize_corporate_events(records: list[RawRecord], symbol_exchange: dict[str, str]) -> pd.DataFrame:
    frames = []
    for record in records:
        if record.data.empty:
            continue
        df = record.data.copy()
        symbol_value = normalize_symbol(record.source_id.split(":")[2]) if len(record.source_id.split(":")) >= 4 else None
        symbol_series = get_series(df, "symbol", symbol_value).map(normalize_symbol).fillna(symbol_value)
        exchange_series = symbol_series.map(lambda symbol: symbol_exchange.get(symbol or "", "UNKNOWN")).map(normalize_exchange)
        title = get_series(df, "title")
        event_type = get_series(df, "event_type")
        source_event_id = get_series(df, "event_source_id")
        event_seed = (
            symbol_series.fillna("")
            + "|"
            + source_event_id.fillna("").astype(str)
            + "|"
            + title.fillna("").astype(str)
            + "|"
            + get_series(df, "ex_date").fillna("").astype(str)
            + "|"
            + record.source_id
            + "|"
            + pd.Series(df.index, index=df.index).astype(str)
        )
        frame = pd.DataFrame(
            {
                "event_id": event_seed.map(lambda text: hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]),
                "symbol": symbol_series,
                "event_type": event_type,
                "title": title,
                "description": get_series(df, "description"),
                "announcement_date": pd.to_datetime(get_series(df, "announcement_date"), errors="coerce").dt.date,
                "ex_date": pd.to_datetime(get_series(df, "ex_date"), errors="coerce").dt.date,
                "record_date": pd.to_datetime(get_series(df, "record_date"), errors="coerce").dt.date,
                "payment_date": pd.to_datetime(get_series(df, "payment_date"), errors="coerce").dt.date,
                "effective_date": pd.to_datetime(get_series(df, "effective_date"), errors="coerce").dt.date,
                "cash_dividend": pd.to_numeric(get_series(df, "cash_dividend"), errors="coerce"),
                "stock_dividend_ratio": pd.to_numeric(get_series(df, "stock_dividend_ratio"), errors="coerce"),
                "issue_ratio": pd.to_numeric(get_series(df, "issue_ratio"), errors="coerce"),
                "source": SOURCE,
                "source_id": record.source_id,
                "raw_path": record.raw_path,
                "crawled_at": record.crawled_at,
                "schema_version": SCHEMA_VERSION,
            }
        )
        frame["security_id"] = [make_security_id(exchange, symbol) for exchange, symbol in zip(exchange_series, frame["symbol"])]
        frame["quality_status"] = ""
        frame["quality_reasons"] = ""
        frames.append(frame)

    if not frames:
        return pd.DataFrame(columns=CORPORATE_EVENTS_COLUMNS)
    return pd.concat(frames, ignore_index=True)[CORPORATE_EVENTS_COLUMNS]
