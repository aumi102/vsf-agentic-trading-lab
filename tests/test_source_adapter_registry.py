from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.source_adapters.base import AccessStatus
from trading_agent.source_adapters.fred_adapter import FredAdapter
from trading_agent.source_adapters.registry import ADAPTERS, DEFAULT_SOURCES, create_adapters, parse_source_names
from trading_agent.source_adapters.vbma_adapter import VbmaAdapter
from trading_agent.source_adapters.vietcap_iq_adapter import VietcapIqAdapter


def test_registry_default_sources_are_focused_four() -> None:
    expected = {"hose", "vietcap_iq", "vbma", "fred"}

    assert set(ADAPTERS) == expected
    assert set(DEFAULT_SOURCES) == expected
    assert set(parse_source_names("all")) == expected
    assert {"ssi_fastconnect", "fiingroup", "vnstock_reference"}.isdisjoint(parse_source_names("all"))
    assert len(create_adapters(["hose", "fred"])) == 2


def test_parse_source_names_supports_focused_comma_list() -> None:
    assert parse_source_names("hose,fred,vietcap_iq") == ["hose", "fred", "vietcap_iq"]


def test_vietcap_iq_likely_tables_are_company_financial_report_tables(monkeypatch) -> None:
    monkeypatch.delenv("VIETCAP_IQ_PROBE_URL", raising=False)
    monkeypatch.delenv("VIETCAP_PROBE_URL", raising=False)

    result = VietcapIqAdapter().probe(["FPT"], "2024-01-01", "2024-01-02", "run1")

    assert result.source_name == "vietcap_iq"
    assert set(result.likely_canonical_tables) == {
        "company_profiles",
        "financial_statement_items",
        "financial_ratios",
        "company_reports",
        "report_documents",
    }


def test_fred_missing_api_key_returns_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("FRED_API_KEY", raising=False)

    result = FredAdapter().probe(["FPT"], "2024-01-01", "2024-01-02", "run1")

    assert result.access_status == AccessStatus.NOT_CONFIGURED
    assert result.auth_status == "missing_api_key"


def test_vbma_no_url_returns_manual_only(monkeypatch) -> None:
    monkeypatch.delenv("VBMA_PROBE_URL", raising=False)

    result = VbmaAdapter().probe(["FPT"], "2024-01-01", "2024-01-02", "run1")

    assert result.access_status == AccessStatus.MANUAL_ONLY
