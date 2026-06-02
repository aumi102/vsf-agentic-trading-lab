from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.source_adapters.base import AccessStatus
from trading_agent.source_adapters.registry import ADAPTERS, DEFAULT_SOURCES, create_adapters, parse_source_names
from trading_agent.source_adapters.ssi_fastconnect_adapter import SsiFastConnectAdapter
from trading_agent.source_adapters.vnstock_reference_adapter import VnstockReferenceAdapter


def test_registry_returns_all_expected_adapters() -> None:
    expected = {"hose", "ssi_fastconnect", "fiingroup", "vietcap", "vbma", "fred", "vnstock_reference"}

    assert set(ADAPTERS) == expected
    assert set(DEFAULT_SOURCES) == expected
    assert len(create_adapters(["hose", "fred"])) == 2


def test_parse_source_names_supports_all_and_comma_list() -> None:
    assert parse_source_names("hose,fred") == ["hose", "fred"]
    assert set(parse_source_names("all")) == set(DEFAULT_SOURCES)


def test_missing_credentials_return_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("SSI_FASTCONNECT_BASE_URL", raising=False)
    monkeypatch.delenv("SSI_FASTCONNECT_TOKEN", raising=False)

    result = SsiFastConnectAdapter().probe(["FPT"], "2024-01-01", "2024-01-02", "run1")

    assert result.access_status == AccessStatus.NOT_CONFIGURED
    assert result.auth_status == "missing_config"


def test_vnstock_reference_is_marked_non_canonical(monkeypatch) -> None:
    from trading_agent.data_sources import vnstock_client

    class FakeFetch:
        ok = True
        data = pd.DataFrame({"symbol": ["FPT"], "organ_name": ["FPT Corp"]})

    class FakeClient:
        def get_listing_all_symbols(self):
            return FakeFetch()

    monkeypatch.setattr(vnstock_client, "VnstockClient", FakeClient)

    result = VnstockReferenceAdapter().probe(["FPT"], "2024-01-01", "2024-01-02", "run1")

    assert result.source_name == "vnstock_reference"
    assert result.access_status == AccessStatus.VERIFIED
    assert "vnstock_reference_not_canonical" in result.warnings
    assert "not canonical" in result.terms_notes.lower()
