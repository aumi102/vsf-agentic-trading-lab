from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SRC = ROOT / "src"
for path in (SCRIPTS, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import audit_hose_quote_report_historical_dates as historical
from trading_agent.source_adapters.base import AccessStatus, SourceProbeResult
from trading_agent.source_adapters.config import ProbeTarget


def test_historical_audit_handles_multiple_requested_dates(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(historical.HoseAdapter, "_probe_configured_target", fake_probe)
    listed_dir = write_listed_universe(tmp_path, ["FPT", "VNM"])
    output_dir = tmp_path / "audit"
    target = base_target()

    summary = historical.run_historical_audit(
        dates=["2026-06-02", "2026-06-03", "2026-05-30"],
        base_target=target,
        output_dir=output_dir,
        run_id="test_run",
        listed_universe_dir=listed_dir,
    )

    assert summary["requested_dates"] == ["2026-06-02", "2026-06-03", "2026-05-30"]
    assert summary["status_counts"] == {"empty_data": 1, "rejected_response": 1, "verified_json": 1}
    assert summary["live_data_fetched"] is True


def test_verified_json_date_records_stock_only_counts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(historical.HoseAdapter, "_probe_configured_target", fake_probe)
    listed_dir = write_listed_universe(tmp_path, ["FPT", "VNM"])

    summary = historical.run_historical_audit(
        dates=["2026-06-02"],
        base_target=base_target(),
        output_dir=tmp_path / "audit",
        run_id="test_run",
        listed_universe_dir=listed_dir,
    )

    result = summary["date_results"][0]
    assert result["status"] == "verified_json"
    assert result["full_row_count"] == 3
    assert result["full_unique_symbol_count"] == 3
    assert result["stock_only_row_count"] == 2
    assert result["stock_only_unique_symbol_count"] == 2
    assert result["excluded_symbol_count"] == 1
    assert result["quality_fail_count"] == 0


def test_empty_data_date_does_not_fail_audit(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(historical.HoseAdapter, "_probe_configured_target", fake_probe)

    summary = historical.run_historical_audit(
        dates=["2026-06-03"],
        base_target=base_target(),
        output_dir=tmp_path / "audit",
        run_id="test_run",
        listed_universe_dir=None,
    )

    result = summary["date_results"][0]
    assert result["status"] == "empty_data"
    assert result["full_row_count"] == 0
    assert result["quality_fail_count"] is None if "quality_fail_count" in result else True


def test_rejected_response_date_is_recorded(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(historical.HoseAdapter, "_probe_configured_target", fake_probe)

    summary = historical.run_historical_audit(
        dates=["2026-05-30"],
        base_target=base_target(),
        output_dir=tmp_path / "audit",
        run_id="test_run",
        listed_universe_dir=None,
    )

    result = summary["date_results"][0]
    assert result["status"] == "rejected_response"
    assert result["errors"] == ["response_body_contains_rejected_marker:Request Rejected"]


def test_rejected_small_empty_json_is_classified_as_empty_data(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(historical.HoseAdapter, "_probe_configured_target", fake_probe_rejected_empty_json)

    summary = historical.run_historical_audit(
        dates=["2026-05-30"],
        base_target=base_target(),
        output_dir=tmp_path / "audit",
        run_id="test_run",
        listed_universe_dir=None,
    )

    result = summary["date_results"][0]
    assert result["status"] == "empty_data"
    assert result["access_status"] == "rejected_response"
    assert result["errors"] == ["response_body_too_small:41<100"]
    assert result["full_row_count"] == 0


def test_report_and_summary_do_not_include_secret_header_values(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(historical.HoseAdapter, "_probe_configured_target", fake_probe)
    target = base_target()
    target = ProbeTarget(
        **{
            **target.__dict__,
            "headers": {"type": "SECRET_TYPE_VALUE", "Cookie": "SECRET_COOKIE_VALUE"},
        }
    )
    summary = historical.run_historical_audit(
        dates=["2026-06-02"],
        base_target=target,
        output_dir=tmp_path / "audit",
        run_id="test_run",
        listed_universe_dir=write_listed_universe(tmp_path, ["FPT"]),
    )

    text = json.dumps(summary, ensure_ascii=False) + historical.build_report(summary)

    assert "SECRET_TYPE_VALUE" not in text
    assert "SECRET_COOKIE_VALUE" not in text


def test_target_for_date_preserves_post_body_and_rewrites_date() -> None:
    target = historical.target_for_date(base_target(), "2026-06-04")

    assert target.method == "POST"
    assert target.body_json == {}
    assert "date=2026-06-04" in target.url
    assert target.expected_body_startswith_json is True
    assert "Request Rejected" in target.reject_body_contains


def fake_probe(self, target: ProbeTarget, *, symbols: list[str], start: str, end: str, run_id: str) -> SourceProbeResult:
    date = start
    base = Path(self.raw_store.base_dir) / f"source=hose" / f"run_id={run_id}" / f"{target.dataset}"
    base.mkdir(parents=True, exist_ok=True)
    raw_path = base / "payload.json"
    metadata_path = base / "metadata.json"

    if date == "2026-06-02":
        payload = {"data": [quote_row("FPT"), quote_row("VNM"), quote_row("CFPT2517")], "success": True, "message": None}
        raw_path.write_text(json.dumps(payload), encoding="utf-8")
        metadata = metadata_for(raw_path, target, date)
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        return SourceProbeResult(
            source_name="hose",
            adapter_name="HoseAdapter",
            access_status=AccessStatus.VERIFIED,
            auth_status="configured_target",
            endpoint_or_surface=target.url,
            datasets=[target.dataset],
            sample_start=date,
            sample_end=date,
            http_status=200,
            content_type="application/json; charset=utf-8",
            raw_paths=[str(raw_path)],
            metadata_paths=[str(metadata_path)],
        )
    if date == "2026-06-03":
        payload = {"data": [], "success": True, "message": None}
        raw_path.write_text(json.dumps(payload), encoding="utf-8")
        metadata = metadata_for(raw_path, target, date)
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        return SourceProbeResult(
            source_name="hose",
            adapter_name="HoseAdapter",
            access_status=AccessStatus.VERIFIED,
            auth_status="configured_target",
            endpoint_or_surface=target.url,
            datasets=[target.dataset],
            sample_start=date,
            sample_end=date,
            http_status=200,
            content_type="application/json; charset=utf-8",
            raw_paths=[str(raw_path)],
            metadata_paths=[str(metadata_path)],
        )
    return SourceProbeResult(
        source_name="hose",
        adapter_name="HoseAdapter",
        access_status=AccessStatus.REJECTED_RESPONSE,
        auth_status="configured_target",
        endpoint_or_surface=target.url,
        datasets=[target.dataset],
        sample_start=date,
        sample_end=date,
        http_status=200,
        content_type="text/html; charset=utf-8",
        errors=["response_body_contains_rejected_marker:Request Rejected"],
    )


def fake_probe_rejected_empty_json(self, target: ProbeTarget, *, symbols: list[str], start: str, end: str, run_id: str) -> SourceProbeResult:
    base = Path(self.raw_store.base_dir) / f"source=hose" / f"run_id={run_id}" / f"{target.dataset}"
    base.mkdir(parents=True, exist_ok=True)
    raw_path = base / "payload.json"
    metadata_path = base / "metadata.json"
    raw_path.write_text(json.dumps({"data": [], "success": True, "message": None}), encoding="utf-8")
    metadata_path.write_text(json.dumps(metadata_for(raw_path, target, start)), encoding="utf-8")
    return SourceProbeResult(
        source_name="hose",
        adapter_name="HoseAdapter",
        access_status=AccessStatus.REJECTED_RESPONSE,
        auth_status="configured_target",
        endpoint_or_surface=target.url,
        datasets=[target.dataset],
        sample_start=start,
        sample_end=end,
        http_status=200,
        content_type="application/json; charset=utf-8",
        raw_paths=[str(raw_path)],
        metadata_paths=[str(metadata_path)],
        errors=["response_body_too_small:41<100"],
        warnings=["response_body_too_small:41<100"],
    )


def metadata_for(raw_path: Path, target: ProbeTarget, date: str) -> dict[str, object]:
    return {
        "source_name": "hose",
        "adapter_name": "HoseAdapter",
        "dataset": target.dataset,
        "endpoint_or_surface": target.url,
        "request_params": {
            "target_name": target.name,
            "method": target.method,
            "body_present": True,
            "body_size_bytes": 2,
            "header_names": sorted(target.headers.keys()),
        },
        "content_hash": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        "raw_path": str(raw_path),
        "access_status": "verified",
        "status": "success",
        "terms_notes": "test fixture",
        "crawled_at": f"{date}T00:00:00+00:00",
    }


def base_target() -> ProbeTarget:
    return ProbeTarget(
        source_name="hose",
        name="hose_daily_quote_report_completed_day_candidate",
        dataset="hose_daily_quote_report",
        url="https://api.hsx.vn/mk/api/v1/market/quote-report?tradingBy=VNINDEX&date=2026-06-02",
        method="POST",
        body_json={},
        expected_content_type_contains=["application/json"],
        expected_body_startswith_json=True,
        reject_body_contains=["Request Rejected", "The requested URL was rejected"],
        headers={"Content-Type": "application/json", "type": "LOCAL_ONLY"},
        config_file="config/source_probe_targets.local.json",
    )


def quote_row(symbol: str) -> dict[str, object]:
    return {
        "id": f"row-{symbol}",
        "securitySymbol": symbol,
        "securityName": None,
        "isin": None,
        "bloomberg": None,
        "changePrice": "0.10",
        "priorClosePrice": "10.00",
        "openPrice": "10.10",
        "highPrice": "10.50",
        "lowPrice": "9.80",
        "closePrice": "10.20",
        "changePriceRatio": "1.00",
        "mainVolume": "1,000.00",
        "mainValue": "10,200.00",
        "averagePrice": "10.20",
        "ceiling": "11.00",
        "floor": "9.00",
    }


def write_listed_universe(tmp_path: Path, symbols: list[str]) -> Path:
    listed_dir = tmp_path / "listed"
    listed_dir.mkdir(exist_ok=True)
    pd.DataFrame({"symbol": symbols}).to_csv(listed_dir / "symbol_universe.csv", index=False)
    return listed_dir
