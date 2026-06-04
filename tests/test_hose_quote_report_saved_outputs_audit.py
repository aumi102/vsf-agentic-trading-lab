from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import audit_hose_quote_report_saved_outputs as saved_audit


def test_saved_outputs_audit_summarizes_runs(tmp_path: Path) -> None:
    base_dir = tmp_path / "hose_quote_report"
    run_dir = write_run(base_dir, "20260603T094855Z")

    summary = saved_audit.build_saved_outputs_audit(base_dir)

    assert summary["run_count"] == 1
    assert summary["live_data_fetched"] is False
    assert summary["units_unconfirmed_any"] is True
    run = summary["runs"][0]
    assert run["run_id"] == run_dir.name
    assert run["trading_dates"] == ["2026-06-02"]
    assert run["data_statuses"] == ["final_candidate"]
    assert run["daily_quote_reports_count"] == 662
    assert run["units_unconfirmed"] is True


def test_saved_outputs_audit_reads_stock_only_summary(tmp_path: Path) -> None:
    base_dir = tmp_path / "hose_quote_report"
    write_run(base_dir, "20260603T094855Z", stock_only=True)

    summary = saved_audit.build_saved_outputs_audit(base_dir)
    run = summary["runs"][0]

    assert run["stock_only_exists"] is True
    assert run["stock_only_rows"] == 403
    assert run["stock_only_unique_symbols"] == 403
    assert run["excluded_rows"] == 259
    assert run["stock_only_run_quality_status"] == "pass"


def test_saved_outputs_audit_ignores_non_run_stock_only_dir(tmp_path: Path) -> None:
    base_dir = tmp_path / "hose_quote_report"
    write_run(base_dir, "20260603T094855Z")
    (base_dir / "stock_only").mkdir()

    summary = saved_audit.build_saved_outputs_audit(base_dir)

    assert summary["run_count"] == 1


def write_run(base_dir: Path, run_id: str, *, stock_only: bool = False) -> Path:
    run_dir = base_dir / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "validation_summary.json").write_text(
        json.dumps(
            {
                "parsed_payloads": [
                    {
                        "trading_date": "2026-06-02",
                        "data_status": "final_candidate",
                    }
                ],
                "daily_price_bars_count": 662,
                "daily_quote_reports_count": 662,
                "market_ohlcv_snapshots_count": 662,
                "quality_pass_count": 0,
                "quality_warn_count": 662,
                "quality_fail_count": 0,
                "quality_reason_counts": {
                    "warning_source_units_unconfirmed": 662,
                    "warning_no_trade_zero_ohlc": 58,
                },
                "limitations": ["Source units are not fully confirmed."],
            }
        ),
        encoding="utf-8",
    )
    if stock_only:
        stock_dir = run_dir / "stock_only"
        stock_dir.mkdir()
        (stock_dir / "stock_only_filter_summary.json").write_text(
            json.dumps(
                {
                    "stock_only_rows": 403,
                    "stock_only_unique_symbols": 403,
                    "excluded_rows": 259,
                    "excluded_unique_symbols": 259,
                    "run_quality_status": "pass",
                }
            ),
            encoding="utf-8",
        )
    return run_dir
