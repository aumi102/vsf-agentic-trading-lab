from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.source_adapters.base import AccessStatus, SourceProbeResult
from trading_agent.source_adapters.raw_store import RawProbeStore
from trading_agent.source_adapters.registry import create_adapters, parse_source_names
from trading_agent.source_adapters.reporting import write_source_probe_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe source/vendor/provider access and raw field shapes.")
    parser.add_argument("--sources", default="all", help="Comma-separated sources, or all.")
    parser.add_argument("--symbols", default="FPT,VNM", help="Comma-separated symbols for tiny source probes.")
    parser.add_argument("--start", default="2023-11-10")
    parser.add_argument("--end", default="2026-06-01")
    parser.add_argument("--report-out", default="reports/source_probe_report.md")
    parser.add_argument("--raw-base-dir", default="data/raw/source_probe")
    return parser.parse_args()


def parse_symbols(value: str) -> list[str]:
    return [symbol.strip().upper() for symbol in value.split(",") if symbol.strip()]


def main() -> int:
    args = parse_args()
    try:
        source_names = parse_source_names(args.sources)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    symbols = parse_symbols(args.symbols)
    if not symbols:
        print("No valid symbols supplied.", file=sys.stderr)
        return 2

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_store = RawProbeStore(args.raw_base_dir)
    adapters = create_adapters(source_names, raw_store=raw_store)
    results: list[SourceProbeResult] = []

    for adapter in adapters:
        try:
            result = adapter.probe(symbols=symbols, start=args.start, end=args.end, run_id=run_id)
        except Exception as exc:  # pragma: no cover - defensive isolation for live probes
            result = SourceProbeResult(
                source_name=adapter.source_name,
                adapter_name=adapter.adapter_name,
                access_status=AccessStatus.ERROR,
                auth_status="probe_exception",
                endpoint_or_surface="probe()",
                datasets=[],
                sample_symbols=symbols,
                sample_start=args.start,
                sample_end=args.end,
                errors=[str(exc)],
                next_action="Fix adapter probe error before retrying.",
            )
        results.append(result)

    write_source_probe_report(
        report_path=args.report_out,
        run_id=run_id,
        symbols=symbols,
        start=args.start,
        end=args.end,
        results=results,
    )

    print(f"run_id={run_id}")
    for result in results:
        raw_count = len(result.raw_paths)
        print(f"{result.source_name}: {result.access_status.value} auth={result.auth_status} raw_samples={raw_count}")
    print(f"report={args.report_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
