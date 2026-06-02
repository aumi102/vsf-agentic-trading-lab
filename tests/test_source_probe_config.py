from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.source_adapters.base import AccessStatus
from trading_agent.source_adapters.config import load_probe_targets
from trading_agent.source_adapters.fred_adapter import FredAdapter
from trading_agent.source_adapters.hose_adapter import HoseAdapter
from trading_agent.source_adapters.raw_store import RawProbeStore
from trading_agent.source_adapters.vietcap_iq_adapter import VietcapIqAdapter


def test_example_config_loads() -> None:
    targets = load_probe_targets(ROOT / "config" / "source_probe_targets.example.json")

    assert set(targets) == {"hose", "vietcap_iq", "vbma", "fred"}
    assert targets["hose"][0].name == "hose_market_data_candidate"
    assert "daily_prices" in targets["hose"][0].likely_canonical_tables
    assert "order_book_snapshots" in targets["hose"][0].likely_canonical_tables
    assert targets["vietcap_iq"][0].auth_env == "VIETCAP_IQ_TOKEN"
    assert targets["fred"][0].auth_env == "FRED_API_KEY"
    assert targets["fred"][0].auth_in == "query"
    assert targets["fred"][0].auth_param == "api_key"


def test_placeholder_url_is_skipped_without_network() -> None:
    targets = load_probe_targets(ROOT / "config" / "source_probe_targets.example.json")
    adapter = HoseAdapter()

    result = adapter.probe_configured_targets(targets["hose"], ["FPT"], "2024-01-01", "2024-01-02", "run1")[0]

    assert result.access_status == AccessStatus.NOT_CONFIGURED
    assert result.target_skipped_reason == "placeholder_url"
    assert result.raw_paths == []


def test_auth_env_missing_returns_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("VIETCAP_IQ_TOKEN", raising=False)
    targets = load_probe_targets(ROOT / "config" / "source_probe_targets.example.json")
    target = targets["vietcap_iq"][0]
    target = target.__class__(
        **{
            **target.__dict__,
            "url": "https://configured.example.test/vietcap-iq",
        }
    )

    result = VietcapIqAdapter().probe_configured_targets([target], ["FPT"], "2024-01-01", "2024-01-02", "run1")[0]

    assert result.access_status == AccessStatus.NOT_CONFIGURED
    assert result.auth_status == "missing_auth_env"
    assert result.auth_env_missing == "VIETCAP_IQ_TOKEN"
    assert result.raw_paths == []


def test_invalid_json_config_fails_clearly(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{bad json", encoding="utf-8")

    try:
        load_probe_targets(path)
    except ValueError as exc:
        assert "Invalid source probe config JSON" in str(exc)
    else:
        raise AssertionError("Expected invalid JSON to raise ValueError")


def test_query_auth_appends_token_internally_and_redacts_metadata(monkeypatch, tmp_path: Path) -> None:
    class FakeHeaders:
        def get(self, key: str, default: str = "") -> str:
            return "application/json" if key == "content-type" else default

    class FakeResponse:
        status = 200
        headers = FakeHeaders()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self) -> bytes:
            return b'{"observations":[{"date":"2024-01-01","value":"4.0"}]}'

    requested_urls: list[str] = []

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        return FakeResponse()

    monkeypatch.setenv("FRED_API_KEY", "super-secret-fred-key")
    monkeypatch.setattr("trading_agent.source_adapters.base.urlopen", fake_urlopen)
    targets = load_probe_targets(ROOT / "config" / "source_probe_targets.example.json")
    target = targets["fred"][0].__class__(
        **{
            **targets["fred"][0].__dict__,
            "url": "https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&file_type=json&limit=5",
        }
    )

    result = FredAdapter(raw_store=RawProbeStore(tmp_path)).probe_configured_targets(
        [target], ["FPT"], "2024-01-01", "2024-01-02", "run1"
    )[0]

    assert result.access_status == AccessStatus.VERIFIED
    assert result.auth_in == "query"
    assert result.auth_param == "api_key"
    assert "api_key=super-secret-fred-key" in requested_urls[0]
    metadata = json.loads(Path(result.metadata_paths[0]).read_text(encoding="utf-8"))
    metadata_text = json.dumps(metadata)
    assert "super-secret-fred-key" not in metadata_text
    assert metadata["request_params"]["auth_env"] == "FRED_API_KEY"
    assert metadata["request_params"]["auth_param"] == "api_key"
