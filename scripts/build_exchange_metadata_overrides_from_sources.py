"""Build source-backed exchange metadata overrides from captured universe files."""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
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

from trading_agent.backtest.slippage_guard import normalize_exchange  # noqa: E402
from trading_agent.storage import questdb_client as qdb  # noqa: E402

DEFAULT_OUTPUT = ROOT / "configs" / "exchange_metadata_overrides.csv"
REPORT_PATH = ROOT / "docs" / "data_sources" / "exchange_metadata_status.md"
DEFAULT_SOURCES = [
    ROOT / "data" / "processed" / "dry_run" / "vietcap_iq_universe" / "20260604T101513Z" / "symbol_universe.csv",
    ROOT / "data" / "processed" / "dry_run" / "vietcap_iq_universe" / "20260604T101513Z" / "exchange_listings.csv",
    ROOT / "data" / "processed" / "dry_run" / "hose_listed_universe_all_pages" / "20260603T080254Z" / "symbol_universe.csv",
    ROOT / "data" / "processed" / "dry_run" / "hose_listed_universe_all_pages" / "20260603T080254Z" / "exchange_listings.csv",
]
SUPPORTED = {"HOSE", "HSX", "HNX", "UPCOM", "UPC"}


def _normalize_exchange(value: str | None) -> str:
    normalized = normalize_exchange(value)
    if normalized == "HSX":
        return "HOSE"
    return normalized


def _read_source(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            symbol = str(raw.get("symbol") or "").strip().upper()
            exchange = str(raw.get("exchange") or raw.get("exchange_or_floor") or raw.get("floor_raw") or "").strip().upper()
            if not symbol or not exchange:
                continue
            normalized = _normalize_exchange(exchange)
            if exchange not in SUPPORTED or normalized == "UNKNOWN":
                continue
            quality = str(raw.get("quality_status") or "").strip().lower()
            if quality and quality not in {"pass", "warn"}:
                continue
            source_name = str(raw.get("source_name") or path.parent.parent.name or "captured_universe").strip()
            run_id = str(raw.get("all_pages_run_id") or path.parent.name).strip()
            rows.append(
                {
                    "symbol": symbol,
                    "exchange": normalized,
                    "source": f"{source_name}:{path.name}:{run_id}",
                    "quality_status": quality or "unknown",
                }
            )
    return rows


def _securities_symbols(url: str) -> set[str]:
    base = url.rstrip("/")
    with qdb.open_client(timeout_seconds=60.0) as client:
        _, rows = qdb.exec_rows(client, base, "SELECT symbol FROM securities")
    return {str(row[0]).upper() for row in rows if row}


def _current_exchange_count(url: str) -> tuple[int, int]:
    base = url.rstrip("/")
    with qdb.open_client(timeout_seconds=60.0) as client:
        total = int(qdb.exec_scalar(client, base, "SELECT count() FROM securities", 0))
        known = int(qdb.exec_scalar(client, base, "SELECT count() FROM securities WHERE exchange IS NOT NULL AND exchange != '' AND exchange != 'UNKNOWN'", 0))
    return total, known


def build_overrides(url: str, sources: list[Path], output: Path) -> dict[str, Any]:
    securities = _securities_symbols(url)
    before_total, before_known = _current_exchange_count(url)
    evidence: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    source_rows = 0
    for path in sources:
        rows = _read_source(path)
        source_rows += len(rows)
        for row in rows:
            if row["symbol"] not in securities:
                continue
            evidence[row["symbol"]][row["exchange"]].add(row["source"])

    conflicts = {
        symbol: {exchange: sorted(srcs) for exchange, srcs in by_exchange.items()}
        for symbol, by_exchange in evidence.items()
        if len(by_exchange) > 1
    }
    output_rows: list[dict[str, str]] = []
    skipped_conflicts = sorted(conflicts)
    for symbol in sorted(evidence):
        if symbol in conflicts:
            continue
        exchange, srcs = next(iter(evidence[symbol].items()))
        sources_joined = "|".join(sorted(srcs))
        confidence = "high" if len(srcs) >= 2 else "medium"
        output_rows.append(
            {
                "symbol": symbol,
                "exchange": exchange,
                "source": sources_joined,
                "confidence": confidence,
                "notes": "source-backed exchange metadata from captured Vietcap IQ and/or HOSE universe dry-run files",
            }
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["symbol", "exchange", "source", "confidence", "notes"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(output_rows)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    coverage_pct = (len(output_rows) / before_total * 100.0) if before_total else 0.0
    lines = [
        "# Exchange metadata status",
        "",
        f"- output_config: `{output}`",
        f"- source_files: `{len(sources)}`",
        f"- raw_source_rows_seen: `{source_rows}`",
        f"- securities_total: `{before_total}`",
        f"- securities_known_exchange_before_apply: `{before_known}`",
        f"- source_backed_override_rows: `{len(output_rows)}`",
        f"- source_backed_coverage_pct_vs_securities: `{coverage_pct:.2f}%`",
        f"- conflicts_skipped: `{len(skipped_conflicts)}`",
        "",
        "## Sources",
        "",
    ]
    for path in sources:
        lines.append(f"- `{path}`")
    lines.extend(["", "## Conflicts", ""])
    if skipped_conflicts:
        for symbol in skipped_conflicts[:50]:
            lines.append(f"- `{symbol}`: `{conflicts[symbol]}`")
    else:
        lines.append("No source conflicts detected among generated override rows.")
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- This config updates only symbols found in QuestDB `securities`.",
            "- Symbols absent from captured source evidence are not assigned an exchange.",
            "- Applying the config updates only `securities.exchange`; it does not mutate OHLCV, FA, or backtest tables.",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return {
        "source_rows_seen": source_rows,
        "securities_total": before_total,
        "known_exchange_before_apply": before_known,
        "overrides_written": len(output_rows),
        "coverage_pct_vs_securities": coverage_pct,
        "conflicts_skipped": len(skipped_conflicts),
        "output": str(output),
        "report_path": str(REPORT_PATH),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build source-backed exchange metadata override config.")
    parser.add_argument("--questdb-url", default=qdb.DEFAULT_QUESTDB_URL)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--source", action="append", help="Additional/override CSV source path. Can be repeated.")
    args = parser.parse_args()
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    sources = [Path(item) for item in args.source] if args.source else DEFAULT_SOURCES
    sources = [path if path.is_absolute() else ROOT / path for path in sources]
    result = build_overrides(args.questdb_url, sources, output)
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
