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
            source_name="vietcap_iq",
            adapter_name="VietcapIqAdapter",
            access_status=AccessStatus.NOT_CONFIGURED,
            auth_status="missing_url",
            endpoint_or_surface="VIETCAP_IQ_PROBE_URL not configured",
            likely_canonical_tables=["company_profiles", "financial_statement_items", "financial_ratios", "company_reports", "report_documents"],
            next_action="configure Vietcap IQ target",
        ),
        SourceProbeResult(
            source_name="vbma",
            adapter_name="VbmaAdapter",
            access_status=AccessStatus.MANUAL_ONLY,
            auth_status="manual_or_unknown",
            endpoint_or_surface="VBMA_PROBE_URL not configured",
            likely_canonical_tables=["bond_auctions", "yield_curve_points"],
            next_action="manual inspect",
        ),
        SourceProbeResult(
            source_name="fred",
            adapter_name="FredAdapter",
            access_status=AccessStatus.NOT_CONFIGURED,
            auth_status="missing_api_key",
            endpoint_or_surface="FRED_API_KEY not configured",
            likely_canonical_tables=["macro_series", "macro_observations", "macro_features"],
            next_action="configure key",
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
        config_file="config/source_probe_targets.local.json",
        config_status="missing",
    )

    text = report_path.read_text(encoding="utf-8")
    assert "targets_config" in text
    assert "Canonical Stock Data Readiness For HSX/HOSE" in text
    assert "Company/Financial Reports Readiness For Vietcap IQ" in text
    assert "Bonds/Macro Local Readiness For VBMA" in text
    assert "Global Macro Readiness For FRED" in text
    assert "`hose`" in text
    assert "`manual_only`" in text
    assert "`vietcap_iq`" in text
    assert "`fred`" in text
    assert "`not_configured`" in text
    assert "none verified yet" in text


def test_cli_symbol_parsing() -> None:
    assert parse_symbols(" fpt, VNM ,,") == ["FPT", "VNM"]
