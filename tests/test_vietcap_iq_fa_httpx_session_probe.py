from __future__ import annotations

import json
from pathlib import Path

import httpx

from scripts.probe_vietcap_iq_fa_httpx_session import (
    DEFAULT_USER_AGENT,
    build_default_api_url,
    build_default_page_url,
    build_warmup_urls,
    run_httpx_session_diagnostic,
)


PAGE_URL = build_default_page_url("VCI")
API_URL = build_default_api_url("VCI", "BALANCE_SHEET")
DATASET = "vietcap_iq_fa_financial_statement_balance_sheet_httpx_session"
EXPECTED_URL_ORDER = [PAGE_URL] + build_warmup_urls("VCI") + [API_URL]


# --- build helper tests ---


def test_build_default_page_url_uses_symbol() -> None:
    url = build_default_page_url("FPT")
    assert "ticker=FPT" in url
    assert "trading.vietcap.com.vn" in url


def test_build_default_api_url_uses_symbol_and_section() -> None:
    url = build_default_api_url("FPT", "BALANCE_SHEET")
    assert "/company/FPT/" in url
    assert "section=BALANCE_SHEET" in url
    assert "iq.vietcap.com.vn" in url


def test_build_warmup_urls_uses_symbol() -> None:
    urls = build_warmup_urls("FPT")
    assert any("ticker=FPT" in u for u in urls)
    assert not any("ticker=VCI" in u for u in urls)


# --- UA / guardrail tests ---


def test_default_user_agent_is_real_browser_string() -> None:
    assert "browser-like user agent" not in DEFAULT_USER_AGENT
    assert "Mozilla/5.0" in DEFAULT_USER_AGENT
    assert "Chrome" in DEFAULT_USER_AGENT


# --- session behaviour tests ---


def test_httpx_session_visits_page_then_warmups_then_api(tmp_path: Path) -> None:
    seen_urls: list[str] = []
    captured_api_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen_urls.append(url)
        if url == PAGE_URL:
            return httpx.Response(200, headers={"set-cookie": "sessionid=SECRET_COOKIE"}, text="<html></html>")
        if url == API_URL:
            captured_api_headers.update(
                {key.lower(): value for key, value in request.headers.items()}
            )
            return httpx.Response(
                200,
                headers={"content-type": "application/json; charset=utf-8"},
                json={
                    "serverDateTime": "2026-06-08T00:00:00Z",
                    "traceId": "trace",
                    "status": 200,
                    "code": "OK",
                    "msg": None,
                    "exception": None,
                    "successful": True,
                    "data": {"rows": [{"period": "2025Q4", "value": 1}]},
                },
            )
        return httpx.Response(200, headers={"content-type": "application/json"}, json={})

    transport = httpx.MockTransport(handler)

    result = run_httpx_session_diagnostic(
        symbol="VCI",
        page_url=PAGE_URL,
        api_url=API_URL,
        dataset=DATASET,
        output_root=tmp_path,
        timeout_seconds=30,
        run_id="run1",
        client_factory=lambda **kwargs: httpx.Client(transport=transport, **kwargs),
    )

    assert seen_urls == EXPECTED_URL_ORDER
    assert "authorization" not in result["manual_header_names"]
    assert "Cookie" not in result["manual_header_names"]
    assert result["manual_cookie_header_set"] is False
    assert result["manual_authorization_header_set"] is False
    assert "authorization" not in captured_api_headers
    assert result["access_status"] == "verified"
    assert result["response_top_level_keys"] == [
        "code", "data", "exception", "msg", "serverDateTime", "status", "successful", "traceId",
    ]
    assert result["data_type"] == "dict"
    assert result["data_keys"] == ["rows"]
    assert Path(result["raw_path"]).exists()
    assert Path(result["metadata_path"]).exists()
    assert "SECRET_COOKIE" not in Path(result["metadata_path"]).read_text(encoding="utf-8")
    assert len(result["warmup_statuses"]) == len(build_warmup_urls("VCI"))


def test_fpt_symbol_uses_consistent_urls_in_request_order(tmp_path: Path) -> None:
    fpt_page_url = build_default_page_url("FPT")
    fpt_api_url = build_default_api_url("FPT", "BALANCE_SHEET")
    fpt_warmup_urls = build_warmup_urls("FPT")
    expected_order = [fpt_page_url] + fpt_warmup_urls + [fpt_api_url]
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen_urls.append(url)
        if url == fpt_page_url:
            return httpx.Response(200, text="<html></html>")
        if url == fpt_api_url:
            return httpx.Response(403, headers={"content-type": "text/html"}, text="forbidden")
        return httpx.Response(200, headers={"content-type": "application/json"}, json={})

    transport = httpx.MockTransport(handler)

    result = run_httpx_session_diagnostic(
        symbol="FPT",
        page_url=fpt_page_url,
        api_url=fpt_api_url,
        dataset=DATASET,
        output_root=tmp_path,
        timeout_seconds=30,
        run_id="run_fpt",
        client_factory=lambda **kwargs: httpx.Client(transport=transport, **kwargs),
    )

    assert seen_urls == expected_order
    assert result["symbol"] == "FPT"
    assert any("ticker=FPT" in u for u in seen_urls)
    assert not any("ticker=VCI" in u for u in seen_urls)


def test_warmup_statuses_recorded_without_cookie_values(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == PAGE_URL:
            return httpx.Response(200, headers={"set-cookie": "sessionid=SECRET_COOKIE"}, text="<html></html>")
        if url == API_URL:
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json={"data": [], "status": 200},
            )
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "set-cookie": "wu=WARMUP_SECRET"},
            json={},
        )

    transport = httpx.MockTransport(handler)

    result = run_httpx_session_diagnostic(
        symbol="VCI",
        page_url=PAGE_URL,
        api_url=API_URL,
        dataset=DATASET,
        output_root=tmp_path,
        timeout_seconds=30,
        run_id="run_wu",
        client_factory=lambda **kwargs: httpx.Client(transport=transport, **kwargs),
    )

    assert len(result["warmup_statuses"]) == len(build_warmup_urls("VCI"))
    for ws in result["warmup_statuses"]:
        assert set(ws.keys()) == {"url_path", "status", "content_type"}
        assert "WARMUP_SECRET" not in str(ws)
    metadata_text = Path(result["metadata_path"]).read_text(encoding="utf-8")
    assert "WARMUP_SECRET" not in metadata_text
    assert "SECRET_COOKIE" not in metadata_text


def test_skip_warmup_omits_warmup_requests(tmp_path: Path) -> None:
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        if str(request.url) == PAGE_URL:
            return httpx.Response(200, text="<html></html>")
        return httpx.Response(200, headers={"content-type": "application/json"}, json={"data": {}})

    transport = httpx.MockTransport(handler)

    run_httpx_session_diagnostic(
        symbol="VCI",
        page_url=PAGE_URL,
        api_url=API_URL,
        dataset=DATASET,
        output_root=tmp_path,
        timeout_seconds=30,
        run_id="run_skip",
        skip_warmup=True,
        client_factory=lambda **kwargs: httpx.Client(transport=transport, **kwargs),
    )

    assert seen_urls == [PAGE_URL, API_URL]


def test_httpx_session_403_marks_auth_required_and_does_not_save_payload(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == PAGE_URL:
            return httpx.Response(200, headers={"set-cookie": "sessionid=SECRET_COOKIE"}, text="<html></html>")
        if url == API_URL:
            return httpx.Response(403, headers={"content-type": "application/json"}, json={"error": "forbidden"})
        return httpx.Response(200, headers={"content-type": "application/json"}, json={})

    transport = httpx.MockTransport(handler)

    result = run_httpx_session_diagnostic(
        symbol="VCI",
        page_url=PAGE_URL,
        api_url=API_URL,
        dataset=DATASET,
        output_root=tmp_path,
        timeout_seconds=30,
        run_id="run2",
        client_factory=lambda **kwargs: httpx.Client(transport=transport, **kwargs),
    )

    assert result["access_status"] == "auth_required"
    assert result["api_http_status"] == 403
    assert result["raw_path"] == ""
    assert result["metadata_path"]
    assert not (tmp_path / "run_id=run2" / DATASET / "payload.json").exists()
    metadata_text = Path(result["metadata_path"]).read_text(encoding="utf-8")
    metadata = json.loads(metadata_text)
    assert metadata["cookies_saved"] is False
    assert metadata["authorization_saved"] is False
    assert "SECRET_COOKIE" not in metadata_text
    assert len(metadata["warmup_statuses"]) == len(build_warmup_urls("VCI"))
