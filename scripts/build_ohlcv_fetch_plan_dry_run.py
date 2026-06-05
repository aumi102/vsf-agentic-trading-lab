from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_INPUTS = [
    "tradable_universe/symbol_universe_tradable.csv",
    "tradable_universe/instrument_universe_tradable.csv",
]
DEFAULT_OUTPUT_BASE = ROOT / "data/processed/dry_run/ohlcv_fetch_plan"
UNKNOWN_SECTOR_WARNING_THRESHOLD = 0.25
LOW_SLEEP_WARNING_THRESHOLD = 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a dry-run OHLCV full-history fetch plan from the Vietcap IQ listed-market fetch universe.")
    parser.add_argument("--vietcap-universe-dir", default="", help="Input Vietcap IQ universe dry-run directory. Defaults to latest complete run.")
    parser.add_argument("--output-dir", default="", help="Output directory. Defaults to data/processed/dry_run/ohlcv_fetch_plan/<run_id>.")
    parser.add_argument("--sleep-min-seconds", type=float, default=1.5)
    parser.add_argument("--sleep-max-seconds", type=float, default=5.0)
    parser.add_argument("--max-symbols", type=int, default=0, help="Optional max symbols for small demo planning.")
    parser.add_argument("--resume-from-checkpoint", default="", help="Optional previous fetch_checkpoint.json path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        input_dir = Path(args.vietcap_universe_dir) if args.vietcap_universe_dir else latest_vietcap_universe_dir(ROOT / "data/processed/dry_run/vietcap_iq_universe")
        output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_BASE / run_id
        result = build_ohlcv_fetch_plan(
            input_dir=input_dir,
            output_dir=output_dir,
            run_id=run_id,
            sleep_min_seconds=args.sleep_min_seconds,
            sleep_max_seconds=args.sleep_max_seconds,
            max_symbols=args.max_symbols if args.max_symbols > 0 else None,
            resume_checkpoint_path=Path(args.resume_from_checkpoint) if args.resume_from_checkpoint else None,
        )
    except Exception as exc:
        print(f"ohlcv_fetch_plan_dry_run_failed={exc}", file=sys.stderr)
        return 1

    summary = result["summary"]
    print(f"run_id={summary['run_id']}")
    print(f"source_universe_dir={summary['source_universe_dir']}")
    print(f"output_dir={summary['output_dir']}")
    print(f"fetch_plan={result['plan_path']}")
    print(f"fetch_checkpoint={result['checkpoint_path']}")
    print(f"fetch_plan_summary={result['summary_path']}")
    print(f"fetch_plan_report={result['report_path']}")
    print(f"run_status={summary['run_status']}")
    print(f"total_symbols={summary['total_symbols']}")
    print(f"pending_symbols={summary['pending_symbols']}")
    print(f"completed_symbols={summary['completed_symbols']}")
    print(f"failed_symbols={summary['failed_symbols']}")
    print(f"sector_counts={json.dumps(summary['sector_counts'], sort_keys=True)}")
    return 0


def build_ohlcv_fetch_plan(
    *,
    input_dir: Path,
    output_dir: Path,
    run_id: str,
    sleep_min_seconds: float,
    sleep_max_seconds: float,
    max_symbols: int | None = None,
    resume_checkpoint_path: Path | None = None,
) -> dict[str, Any]:
    validate_sleep(sleep_min_seconds, sleep_max_seconds)
    validate_input_dir(input_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    symbols = pd.read_csv(input_dir / "tradable_universe/symbol_universe_tradable.csv")
    instruments = pd.read_csv(input_dir / "tradable_universe/instrument_universe_tradable.csv")
    rows = build_plan_rows(
        symbols=symbols,
        instruments=instruments,
        input_dir=input_dir,
        created_at=datetime.now(timezone.utc).isoformat(),
        sleep_min_seconds=sleep_min_seconds,
        sleep_max_seconds=sleep_max_seconds,
        max_symbols=max_symbols,
    )
    if rows.empty:
        raise ValueError("No listed-market fetch universe rows found for OHLCV planning.")

    resume_checkpoint = load_resume_checkpoint(resume_checkpoint_path)
    rows = apply_resume_checkpoint(rows, resume_checkpoint)

    summary = build_summary(
        run_id=run_id,
        input_dir=input_dir,
        output_dir=output_dir,
        rows=rows,
        sleep_min_seconds=sleep_min_seconds,
        sleep_max_seconds=sleep_max_seconds,
        resume_checkpoint_path=resume_checkpoint_path,
    )
    checkpoint = build_checkpoint(summary, rows)

    plan_path = output_dir / "fetch_plan.csv"
    checkpoint_path = output_dir / "fetch_checkpoint.json"
    summary_path = output_dir / "fetch_plan_summary.json"
    report_path = output_dir / "fetch_plan_report.md"

    rows.to_csv(plan_path, index=False)
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2, ensure_ascii=False), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    report_path.write_text(build_report(summary), encoding="utf-8")

    return {
        "plan": rows,
        "summary": summary,
        "checkpoint": checkpoint,
        "plan_path": plan_path,
        "checkpoint_path": checkpoint_path,
        "summary_path": summary_path,
        "report_path": report_path,
    }


def build_plan_rows(
    *,
    symbols: pd.DataFrame,
    instruments: pd.DataFrame,
    input_dir: Path,
    created_at: str,
    sleep_min_seconds: float,
    sleep_max_seconds: float,
    max_symbols: int | None,
) -> pd.DataFrame:
    if "symbol" not in symbols.columns:
        raise ValueError("symbol_universe_tradable.csv must include symbol.")

    symbol_rows = symbols.copy()
    symbol_rows["symbol_norm"] = symbol_rows["symbol"].map(_normalize_text)
    symbol_rows["exchange_norm"] = symbol_rows.get("exchange_or_floor", pd.Series(dtype=object)).map(_normalize_text)

    instrument_columns = ["symbol", "exchange_or_floor", "icb_lv1_raw", "icb_lv2_raw"]
    available_instrument_columns = [column for column in instrument_columns if column in instruments.columns]
    instrument_rows = instruments[available_instrument_columns].copy() if available_instrument_columns else pd.DataFrame()
    if not instrument_rows.empty:
        instrument_rows["symbol_norm"] = instrument_rows["symbol"].map(_normalize_text)
        instrument_rows["exchange_norm"] = instrument_rows.get("exchange_or_floor", pd.Series(dtype=object)).map(_normalize_text)
        merge_columns = [column for column in ["symbol_norm", "exchange_norm", "icb_lv1_raw", "icb_lv2_raw"] if column in instrument_rows.columns]
        symbol_rows = symbol_rows.merge(instrument_rows[merge_columns].drop_duplicates(["symbol_norm", "exchange_norm"]), on=["symbol_norm", "exchange_norm"], how="left")

    symbol_rows["sector_group"] = symbol_rows.get("icb_lv1_raw", pd.Series(index=symbol_rows.index, dtype=object)).map(_normalize_sector)
    symbol_rows["sector_subgroup"] = symbol_rows.get("icb_lv2_raw", pd.Series(index=symbol_rows.index, dtype=object)).map(_normalize_sector)
    symbol_rows = symbol_rows[symbol_rows["symbol_norm"] != ""].copy()
    symbol_rows = symbol_rows.sort_values(["sector_group", "symbol_norm", "exchange_norm"], kind="stable").reset_index(drop=True)
    if max_symbols is not None:
        symbol_rows = symbol_rows.head(max_symbols).copy()

    records: list[dict[str, Any]] = []
    for planned_order, row in enumerate(symbol_rows.itertuples(index=False), start=1):
        symbol = getattr(row, "symbol_norm")
        exchange = getattr(row, "exchange_norm")
        sector_group = getattr(row, "sector_group")
        records.append(
            {
                "plan_row_id": make_plan_row_id(symbol, exchange),
                "symbol": symbol,
                "exchange_or_floor": exchange,
                "sector_group": sector_group,
                "sector_subgroup": getattr(row, "sector_subgroup"),
                "fetch_scope": "full_history",
                "price_bases": "adjusted_and_unadjusted_if_available",
                "planned_order": planned_order,
                "planned_sleep_min_seconds": sleep_min_seconds,
                "planned_sleep_max_seconds": sleep_max_seconds,
                "status": "pending",
                "attempt_count": 0,
                "last_error": "",
                "source_universe_dir": str(input_dir),
                "created_at": created_at,
            }
        )
    return pd.DataFrame.from_records(records)


def apply_resume_checkpoint(rows: pd.DataFrame, checkpoint: dict[str, Any] | None) -> pd.DataFrame:
    if not checkpoint:
        return rows
    completed = {_normalize_text(symbol) for symbol in checkpoint.get("completed_symbol_list", [])}
    failed = {_normalize_text(symbol) for symbol in checkpoint.get("failed_symbol_list", [])}
    if not completed and not failed:
        return rows
    rows = rows.copy()
    completed_mask = rows["symbol"].isin(completed)
    failed_mask = rows["symbol"].isin(failed)
    rows.loc[completed_mask, "status"] = "completed"
    rows.loc[completed_mask, "attempt_count"] = 1
    rows.loc[failed_mask & ~completed_mask, "status"] = "failed"
    rows.loc[failed_mask & ~completed_mask, "attempt_count"] = 1
    rows.loc[failed_mask & ~completed_mask, "last_error"] = "resumed_failed_symbol"
    return rows


def build_summary(
    *,
    run_id: str,
    input_dir: Path,
    output_dir: Path,
    rows: pd.DataFrame,
    sleep_min_seconds: float,
    sleep_max_seconds: float,
    resume_checkpoint_path: Path | None,
) -> dict[str, Any]:
    status_counts = _value_counts(rows["status"])
    sector_counts = _value_counts(rows["sector_group"])
    warnings: list[str] = []
    unknown_count = int(sector_counts.get("UNKNOWN", 0))
    if sleep_min_seconds < LOW_SLEEP_WARNING_THRESHOLD:
        warnings.append("warning_sleep_min_below_one_second")
    if len(rows) > 0 and unknown_count / len(rows) > UNKNOWN_SECTOR_WARNING_THRESHOLD:
        warnings.append("warning_many_unknown_sector_groups")
    run_status = "warn" if warnings else "pass"

    return {
        "run_id": run_id,
        "run_status": run_status,
        "warnings": warnings,
        "source_universe_dir": str(input_dir),
        "output_dir": str(output_dir),
        "resume_checkpoint_path": str(resume_checkpoint_path) if resume_checkpoint_path else "",
        "total_symbols": int(len(rows)),
        "completed_symbols": int(status_counts.get("completed", 0)),
        "failed_symbols": int(status_counts.get("failed", 0)),
        "pending_symbols": int(status_counts.get("pending", 0)),
        "current_sector": next_pending_sector(rows),
        "next_planned_order": next_pending_order(rows),
        "sleep_min_seconds": sleep_min_seconds,
        "sleep_max_seconds": sleep_max_seconds,
        "no_live_fetch": True,
        "fetch_scope": "full_history",
        "price_bases": "adjusted_and_unadjusted_if_available",
        "sector_counts": sector_counts,
        "status_counts": status_counts,
        "unknown_sector_count": unknown_count,
        "limitations": [
            "This is a planning dry run only. No live OHLCV endpoint was called.",
            "The input rows are listed-market fetch universe rows, not final tradable assets.",
            "Final liquidity and strategy filters are deferred to the strategy phase.",
            "Actual fetcher cache format, retry policy, and sleep distribution still need implementation.",
        ],
    }


def build_checkpoint(summary: dict[str, Any], rows: pd.DataFrame) -> dict[str, Any]:
    completed_symbols = rows.loc[rows["status"] == "completed", "symbol"].astype(str).tolist()
    failed_symbols = rows.loc[rows["status"] == "failed", "symbol"].astype(str).tolist()
    return {
        "run_id": summary["run_id"],
        "source_universe_dir": summary["source_universe_dir"],
        "total_symbols": summary["total_symbols"],
        "completed_symbols": summary["completed_symbols"],
        "failed_symbols": summary["failed_symbols"],
        "pending_symbols": summary["pending_symbols"],
        "completed_symbol_list": completed_symbols,
        "failed_symbol_list": failed_symbols,
        "current_sector": summary["current_sector"],
        "next_planned_order": summary["next_planned_order"],
        "sleep_min_seconds": summary["sleep_min_seconds"],
        "sleep_max_seconds": summary["sleep_max_seconds"],
        "no_live_fetch": True,
    }


def build_report(summary: dict[str, Any]) -> str:
    lines = [
        "# OHLCV Fetch Plan Dry-Run Report",
        "",
        f"- run_id: `{summary['run_id']}`",
        f"- run_status: `{summary['run_status']}`",
        f"- source_universe_dir: `{summary['source_universe_dir']}`",
        f"- output_dir: `{summary['output_dir']}`",
        f"- no_live_fetch: `{summary['no_live_fetch']}`",
        f"- fetch_scope: `{summary['fetch_scope']}`",
        f"- price_bases: `{summary['price_bases']}`",
        f"- sleep range seconds: `{summary['sleep_min_seconds']} - {summary['sleep_max_seconds']}`",
        "",
        "## Counts",
        "",
        "| Metric | Count |",
        "|---|---:|",
        f"| Total symbols | {summary['total_symbols']} |",
        f"| Pending symbols | {summary['pending_symbols']} |",
        f"| Completed symbols | {summary['completed_symbols']} |",
        f"| Failed symbols | {summary['failed_symbols']} |",
        f"| Unknown sector symbols | {summary['unknown_sector_count']} |",
        "",
        "## Sector Counts",
        "",
        "| Sector | Count |",
        "|---|---:|",
    ]
    for sector, count in summary["sector_counts"].items():
        lines.append(f"| `{sector}` | {count} |")

    lines.extend(["", "## Warnings", ""])
    if summary["warnings"]:
        for warning in summary["warnings"]:
            lines.append(f"- `{warning}`")
    else:
        lines.append("- none")

    lines.extend(["", "## Limitations", ""])
    for limitation in summary["limitations"]:
        lines.append(f"- {limitation}")
    return "\n".join(lines) + "\n"


def validate_input_dir(input_dir: Path) -> None:
    missing = [name for name in REQUIRED_INPUTS if not (input_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"Missing required listed-market fetch universe files in {input_dir}: {', '.join(missing)}")


def validate_sleep(sleep_min_seconds: float, sleep_max_seconds: float) -> None:
    if sleep_min_seconds < 0 or sleep_max_seconds < 0:
        raise ValueError("Sleep values must be non-negative.")
    if sleep_min_seconds > sleep_max_seconds:
        raise ValueError("sleep_min_seconds must be less than or equal to sleep_max_seconds.")


def latest_vietcap_universe_dir(base_dir: Path) -> Path:
    if not base_dir.exists():
        raise FileNotFoundError(f"Vietcap IQ universe dry-run base directory not found: {base_dir}")
    candidates = [path for path in base_dir.iterdir() if path.is_dir() and all((path / name).exists() for name in REQUIRED_INPUTS)]
    if not candidates:
        raise FileNotFoundError(f"No complete Vietcap IQ listed-market fetch universe directory found under {base_dir}.")
    candidates.sort(key=lambda path: path.name, reverse=True)
    return candidates[0]


def load_resume_checkpoint(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def next_pending_sector(rows: pd.DataFrame) -> str:
    pending = rows[rows["status"] == "pending"]
    if pending.empty:
        return ""
    return str(pending.sort_values("planned_order").iloc[0]["sector_group"])


def next_pending_order(rows: pd.DataFrame) -> int | None:
    pending = rows[rows["status"] == "pending"]
    if pending.empty:
        return None
    return int(pending["planned_order"].min())


def make_plan_row_id(symbol: str, exchange_or_floor: str) -> str:
    return f"ohlcv_plan:{exchange_or_floor}:{symbol}"


def _normalize_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().upper()


def _normalize_sector(value: object) -> str:
    text = _normalize_text(value)
    if text.startswith("{") and text.endswith("}"):
        try:
            data = json.loads(str(value))
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            name = _normalize_text(data.get("name") or data.get("NAME"))
            code = _normalize_text(data.get("code") or data.get("CODE"))
            if name and code:
                return f"{code}:{name}"
            if name:
                return name
            if code:
                return code
    return text if text else "UNKNOWN"


def _value_counts(series: pd.Series) -> dict[str, int]:
    return {str(key): int(value) for key, value in series.fillna("UNKNOWN").astype(str).value_counts().sort_index().items()}


if __name__ == "__main__":
    raise SystemExit(main())
