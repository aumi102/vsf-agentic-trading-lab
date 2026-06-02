from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.probe_sources import parse_symbols
from trading_agent.source_adapters.base import AccessStatus, SourceProbeResult
from trading_agent.source_adapters.reporting import write_source_probe_report


def test_report_writer_includes_all_source_statuses(tmp_path: Path) -> None:
    results = [
        SourceProbeResult(
            source_name="hose",
            adapter_name="HoseAdapter",
            access_status=AccessStatus.MANUAL_ONLY,
            auth_status="manual_or_unknown",
            endpoint_or_surface="HOSE_PROBE_URL not configured",
            likely_canonical_tables=["daily_prices"],
            next_action="manual inspect",
        ),
        SourceProbeResult(
            source_name="fred",
            adapter_name="FredAdapter",
            access_status=AccessStatus.NOT_CONFIGURED,
            auth_status="missing_api_key",
            endpoint_or_surface="FRED_API_KEY not configured",
            likely_canonical_tables=["macro_series", "macro_observations"],
            next_action="configure key",
        ),
        SourceProbeResult(
            source_name="vnstock_reference",
            adapter_name="VnstockReferenceAdapter",
            access_status=AccessStatus.VERIFIED,
            auth_status="library_available_not_provider_verified",
            endpoint_or_surface="vnstock listing_all_symbols",
            likely_canonical_tables=["securities", "daily_prices"],
            warnings=["vnstock_reference_not_canonical"],
            next_action="fallback only",
        ),
    ]
    report_path = tmp_path / "source_probe_report.md"

    write_source_probe_report(
        report_path=report_path,
        run_id="run1",
        symbols=["FPT", "VNM"],
        start="2024-01-01",
        end="2024-01-02",
        results=results,
    )

    text = report_path.read_text(encoding="utf-8")
    assert "`hose`" in text
    assert "`manual_only`" in text
    assert "`fred`" in text
    assert "`not_configured`" in text
    assert "`vnstock_reference` is prototype/fallback only" in text
    assert "none verified yet" in text


def test_cli_symbol_parsing() -> None:
    assert parse_symbols(" fpt, VNM ,,") == ["FPT", "VNM"]
