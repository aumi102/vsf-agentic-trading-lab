from __future__ import annotations

import json
import ssl
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.source_adapters.base import AccessStatus
from trading_agent.source_adapters.config import ProbeTarget, load_probe_targets
from trading_agent.source_adapters.fred_adapter import FredAdapter
from trading_agent.source_adapters.hose_adapter import HoseAdapter
from trading_agent.source_adapters.raw_store import RawProbeStore
from trading_agent.source_adapters.vietcap_iq_adapter import VietcapIqAdapter


def test_example_config_loads() -> None:
    targets = load_probe_targets(ROOT / "config" / "source_probe_targets.example.json")

    assert set(targets) == {"hose", "vietcap_iq", "vbma", "fred"}
    assert targets["hose"][0].name == "hose_listed_stock_universe_api_candidate"
    assert targets["hose"][1].name == "hose_daily_quote_report_completed_day_candidate"
    assert targets["hose"][1].method == "POST"
    assert targets["hose"][1].body_json == {}
    assert targets["hose"][1].expected_content_type_contains == ["application/json"]
    assert targets["hose"][1].expected_body_startswith_json is True
    assert "Request Rejected" in targets["hose"][1].reject_body_contains
    assert "daily_quote_reports" in targets["hose"][1].likely_canonical_tables
    assert targets["vietcap_iq"][0].name == "vietcap_iq_company_search_bar_universe_candidate"
    assert targets["vietcap_iq"][0].expected_content_type_contains == ["application/json"]
    assert "securities_master" in targets["vietcap_iq"][0].likely_canonical_tables
    price_chart_target = next(target for target in targets["vietcap_iq"] if target.name == "vietcap_iq_company_price_chart_fpt_candidate")
    assert "FPT/price-chart" in price_chart_target.url
    assert "ohlcv_bars" in price_chart_target.likely_canonical_tables
    reports_target = next(target for target in targets["vietcap_iq"] if target.name == "vietcap_iq_reports_candidate")
    assert reports_target.auth_env == "VIETCAP_IQ_TOKEN"
    assert targets["fred"][0].auth_env == "FRED_API_KEY"
    assert targets["fred"][0].auth_in == "query"
    assert targets["fred"][0].auth_param == "api_key"
    assert targets["fred"][0].expected_content_type_contains == ["application/json"]
    assert targets["hose"][0].verify_ssl is True
    assert targets["vbma"][0].verify_ssl is False
    assert targets["vbma"][0].headers["User-Agent"] == "vsf-source-probe/0.1"


def test_placeholder_url_is_skipped_without_network() -> None:
    target = ProbeTarget(
        source_name="hose",
        name="placeholder",
        dataset="placeholder",
        url="https://example.com/replace-with-hose-url",
    )
    adapter = HoseAdapter()

    result = adapter.probe_configured_targets([target], ["FPT"], "2024-01-01", "2024-01-02", "run1")[0]

    assert result.access_status == AccessStatus.NOT_CONFIGURED
    assert result.target_skipped_reason == "placeholder_url"
    assert result.raw_paths == []


def test_http_200_json_body_passes_when_expected_json_configured(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "trading_agent.source_adapters.base.urlopen",
        _fake_urlopen_factory(
            body=b'{"data":{"list":[]},"success":true,"message":null}',
            content_type="application/json; charset=utf-8",
        ),
    )
    target = ProbeTarget(
        source_name="hose",
        name="json_target",
        dataset="hose_listed_stock_universe",
        url="https://api.hsx.vn/l/api/v1/1/securities/stock?pageIndex=1&pageSize=30",
        expected_content_type_contains=["application/json"],
        expected_body_startswith_json=True,
        reject_body_contains=["Request Rejected"],
    )

    result = HoseAdapter(raw_store=RawProbeStore(tmp_path)).probe_configured_targets(
        [target], ["FPT"], "2024-01-01", "2024-01-02", "run1"
    )[0]

    assert result.access_status == AccessStatus.VERIFIED
    metadata = json.loads(Path(result.metadata_paths[0]).read_text(encoding="utf-8"))
    assert metadata["access_status"] == "verified"
    assert metadata["status"] == "success"


def test_post_target_sends_body_json_as_request_body_bytes(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout, context=None):
        captured["method"] = request.get_method()
        captured["data"] = request.data
        captured["content_type"] = request.get_header("Content-type")
        return _fake_response(body=b'{"rows":[]}', content_type="application/json; charset=utf-8")

    monkeypatch.setattr("trading_agent.source_adapters.base.urlopen", fake_urlopen)
    target = ProbeTarget(
        source_name="hose",
        name="quote_report_post",
        dataset="hose_daily_quote_report",
        url="https://api.hsx.vn/mk/api/v1/market/quote-report?tradingBy=VNINDEX&date=2026-06-02",
        method="POST",
        body_json={},
        headers={"Accept": "application/json"},
        expected_content_type_contains=["application/json"],
        expected_body_startswith_json=True,
    )

    result = HoseAdapter(raw_store=RawProbeStore(tmp_path)).probe_configured_targets(
        [target], ["FPT"], "2024-01-01", "2024-01-02", "run1"
    )[0]

    assert result.access_status == AccessStatus.VERIFIED
    assert captured["method"] == "POST"
    assert captured["data"] == b"{}"
    assert captured["content_type"] == "application/json"
    metadata = json.loads(Path(result.metadata_paths[0]).read_text(encoding="utf-8"))
    assert metadata["request_params"]["method"] == "POST"
    assert metadata["request_params"]["body_present"] is True
    assert metadata["request_params"]["body_size_bytes"] == 2
    assert metadata["request_params"]["body_json_keys"] == []


def test_get_target_remains_without_request_body(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout, context=None):
        captured["method"] = request.get_method()
        captured["data"] = request.data
        return _fake_response(body=b'{"ok": true}', content_type="application/json")

    monkeypatch.setattr("trading_agent.source_adapters.base.urlopen", fake_urlopen)
    target = ProbeTarget(
        source_name="hose",
        name="listed_get",
        dataset="hose_listed_stock_universe",
        url="https://api.hsx.vn/l/api/v1/1/securities/stock?pageIndex=1&pageSize=30",
        method="GET",
        expected_body_startswith_json=True,
    )

    result = HoseAdapter(raw_store=RawProbeStore(tmp_path)).probe_configured_targets(
        [target], ["FPT"], "2024-01-01", "2024-01-02", "run1"
    )[0]

    assert result.access_status == AccessStatus.VERIFIED
    assert captured["method"] == "GET"
    assert captured["data"] is None


def test_http_200_rejection_html_is_rejected_when_marker_configured(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "trading_agent.source_adapters.base.urlopen",
        _fake_urlopen_factory(
            body=b"<html><body>The requested URL was rejected.</body></html>",
            content_type="text/html; charset=utf-8",
        ),
    )
    target = ProbeTarget(
        source_name="hose",
        name="quote_report",
        dataset="hose_daily_quote_report",
        url="https://api.hsx.vn/mk/api/v1/market/quote-report?tradingBy=VNINDEX&date=2026-06-02",
        expected_content_type_contains=["application/json"],
        expected_body_startswith_json=True,
        reject_body_contains=["Request Rejected", "The requested URL was rejected"],
    )

    result = HoseAdapter(raw_store=RawProbeStore(tmp_path)).probe_configured_targets(
        [target], ["FPT"], "2024-01-01", "2024-01-02", "run1"
    )[0]

    assert result.access_status == AccessStatus.REJECTED_RESPONSE
    assert any("response_content_type_missing:application/json" in error for error in result.errors)
    assert any("response_body_not_json" in error for error in result.errors)
    assert any("response_body_contains_rejected_marker:The requested URL was rejected" in error for error in result.errors)
    assert result.raw_paths
    metadata = json.loads(Path(result.metadata_paths[0]).read_text(encoding="utf-8"))
    assert metadata["access_status"] == "rejected_response"
    assert metadata["status"] == "rejected_response"
    assert "requested URL was rejected" in metadata["error"]


def test_post_html_rejection_becomes_rejected_response(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "trading_agent.source_adapters.base.urlopen",
        _fake_urlopen_factory(
            body=b"<html><body>Request Rejected</body></html>",
            content_type="text/html; charset=utf-8",
        ),
    )
    target = ProbeTarget(
        source_name="hose",
        name="quote_report_post",
        dataset="hose_daily_quote_report",
        url="https://api.hsx.vn/mk/api/v1/market/quote-report?tradingBy=VNINDEX&date=2026-06-02",
        method="POST",
        body_json={},
        expected_content_type_contains=["application/json"],
        expected_body_startswith_json=True,
        reject_body_contains=["Request Rejected"],
    )

    result = HoseAdapter(raw_store=RawProbeStore(tmp_path)).probe_configured_targets(
        [target], ["FPT"], "2024-01-01", "2024-01-02", "run1"
    )[0]

    assert result.access_status == AccessStatus.REJECTED_RESPONSE
    assert "response_body_not_json" in result.errors
    assert any("response_body_contains_rejected_marker:Request Rejected" == error for error in result.errors)


def test_unsupported_methods_still_return_unsupported_method() -> None:
    target = ProbeTarget(
        source_name="hose",
        name="bad_method",
        dataset="bad",
        url="https://api.hsx.vn/test",
        method="PUT",
    )

    result = HoseAdapter().probe_configured_targets([target], ["FPT"], "2024-01-01", "2024-01-02", "run1")[0]

    assert result.access_status == AccessStatus.NOT_CONFIGURED
    assert result.auth_status == "unsupported_method"
    assert result.target_skipped_reason == "unsupported_method:PUT"


def test_simple_target_without_validation_remains_backward_compatible(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "trading_agent.source_adapters.base.urlopen",
        _fake_urlopen_factory(
            body=b"<html><body>Any body is acceptable without validation.</body></html>",
            content_type="text/html",
        ),
    )
    target = ProbeTarget(
        source_name="hose",
        name="legacy_simple_target",
        dataset="legacy",
        url="https://api.hsx.vn/legacy",
    )

    result = HoseAdapter(raw_store=RawProbeStore(tmp_path)).probe_configured_targets(
        [target], ["FPT"], "2024-01-01", "2024-01-02", "run1"
    )[0]

    assert result.access_status == AccessStatus.VERIFIED


def test_auth_env_missing_returns_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("VIETCAP_IQ_TOKEN", raising=False)
    targets = load_probe_targets(ROOT / "config" / "source_probe_targets.example.json")
    target = next(target for target in targets["vietcap_iq"] if target.name == "vietcap_iq_reports_candidate")
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

    def fake_urlopen(request, timeout, context=None):
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
    assert "super-secret-fred-key" not in result.endpoint_or_surface
    metadata = json.loads(Path(result.metadata_paths[0]).read_text(encoding="utf-8"))
    metadata_text = json.dumps(metadata)
    assert "super-secret-fred-key" not in metadata_text
    assert metadata["request_params"]["auth_env"] == "FRED_API_KEY"
    assert metadata["request_params"]["auth_param"] == "api_key"


def test_sensitive_query_params_redacted_even_without_auth_param(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "trading_agent.source_adapters.base.urlopen",
        _fake_urlopen_factory(body=b'{"ok": true}', content_type="application/json"),
    )
    target = ProbeTarget(
        source_name="hose",
        name="sensitive_query",
        dataset="test",
        url="https://api.hsx.vn/test?api_key=SECRET&token=SECRET2&safe=value",
        expected_body_startswith_json=True,
    )

    result = HoseAdapter(raw_store=RawProbeStore(tmp_path)).probe_configured_targets(
        [target], ["FPT"], "2024-01-01", "2024-01-02", "run1"
    )[0]

    metadata_text = Path(result.metadata_paths[0]).read_text(encoding="utf-8")
    assert "SECRET" not in result.endpoint_or_surface
    assert "SECRET" not in metadata_text
    assert "safe=value" in result.endpoint_or_surface


def test_post_metadata_does_not_leak_header_values_or_sensitive_body_values(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "trading_agent.source_adapters.base.urlopen",
        _fake_urlopen_factory(body=b'{"ok": true}', content_type="application/json"),
    )
    target = ProbeTarget(
        source_name="hose",
        name="post_secret_body",
        dataset="test",
        url="https://api.hsx.vn/test",
        method="POST",
        headers={"Cookie": "SESSION=SECRETCOOKIE", "type": "SECRET_TYPE_HEADER", "Accept": "application/json"},
        body_json={"token": "SECRET_BODY_TOKEN", "query": "not-secret"},
        expected_body_startswith_json=True,
    )

    result = HoseAdapter(raw_store=RawProbeStore(tmp_path)).probe_configured_targets(
        [target], ["FPT"], "2024-01-01", "2024-01-02", "run1"
    )[0]

    metadata = json.loads(Path(result.metadata_paths[0]).read_text(encoding="utf-8"))
    metadata_text = json.dumps(metadata)
    assert "SECRETCOOKIE" not in metadata_text
    assert "SECRET_TYPE_HEADER" not in metadata_text
    assert "SECRET_BODY_TOKEN" not in metadata_text
    assert metadata["request_params"]["header_names"] == ["Accept", "Content-Type", "Cookie", "User-Agent", "type"]
    assert metadata["request_params"]["body_json_keys"] == ["query", "token"]
    assert metadata["request_params"]["body_json_sensitive_keys_redacted"] == ["token"]


def test_vbma_configured_target_passes_verify_false_and_headers(monkeypatch, tmp_path: Path) -> None:
    class FakeHeaders:
        def get(self, key: str, default: str = "") -> str:
            return "text/csv" if key == "content-type" else default

    class FakeResponse:
        status = 200
        headers = FakeHeaders()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self) -> bytes:
            return "auction_date,issuer,winning_yield\n2024-01-01,MOF,2.5\n".encode("utf-8")

    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout, context=None):
        captured["url"] = request.full_url
        captured["context"] = context
        captured["user_agent"] = request.get_header("User-agent")
        captured["referer"] = request.get_header("Referer")
        captured["accept"] = request.get_header("Accept")
        return FakeResponse()

    monkeypatch.setattr("trading_agent.source_adapters.base.urlopen", fake_urlopen)
    targets = load_probe_targets(ROOT / "config" / "source_probe_targets.example.json")

    from trading_agent.source_adapters.vbma_adapter import VbmaAdapter

    result = VbmaAdapter(raw_store=RawProbeStore(tmp_path)).probe_configured_targets(
        targets["vbma"], ["FPT"], "2024-01-01", "2024-01-02", "run1"
    )[0]

    assert result.access_status == AccessStatus.VERIFIED
    assert result.verify_ssl is False
    assert isinstance(captured["context"], ssl.SSLContext)
    assert captured["context"].verify_mode == ssl.CERT_NONE
    assert captured["user_agent"] == "vsf-source-probe/0.1"
    assert captured["referer"] == "https://vbma.org.vn/vi/market-data/primary-market"
    assert captured["accept"] == "text/csv,*/*"

    metadata = json.loads(Path(result.metadata_paths[0]).read_text(encoding="utf-8"))
    assert metadata["request_params"]["verify_ssl"] is False
    assert metadata["request_params"]["header_names"] == ["Accept", "Referer", "User-Agent"]


def _fake_urlopen_factory(body: bytes, content_type: str):
    class FakeHeaders:
        def get(self, key: str, default: str = "") -> str:
            return content_type if key.lower() == "content-type" else default

    class FakeResponse:
        status = 200
        headers = FakeHeaders()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self) -> bytes:
            return body

    def fake_urlopen(request, timeout, context=None):
        return FakeResponse()

    return fake_urlopen


def _fake_response(body: bytes, content_type: str):
    class FakeHeaders:
        def get(self, key: str, default: str = "") -> str:
            return content_type if key.lower() == "content-type" else default

    class FakeResponse:
        status = 200
        headers = FakeHeaders()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self) -> bytes:
            return body

    return FakeResponse()
