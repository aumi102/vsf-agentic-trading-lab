from __future__ import annotations

import json
from pathlib import Path

from trading_agent.ingestion.sources.vietcap_iq_gap_chart import (
    HttpResponse,
    fetch_vietcap_iq_gap_chart_live,
)


def test_live_adapter_without_allow_network_makes_no_request(tmp_path: Path) -> None:
    calls = []

    def fake_post(url, body_json, headers, timeout_seconds):
        calls.append(url)
        raise AssertionError("network call must not happen")

    result = fetch_vietcap_iq_gap_chart_live(
        ["FPT"],
        output_base_dir=tmp_path / "raw",
        allow_network=False,
        http_post=fake_post,
    )

    assert result["status"] == "error"
    assert calls == []
    assert "No network request was made." in result["caveats"][0]


def test_live_adapter_success_writes_payload_and_metadata(tmp_path: Path) -> None:
    payload = [_payload("FPT", bars=3)]

    def fake_post(url, body_json, headers, timeout_seconds):
        assert body_json["symbols"] == ["FPT"]
        assert body_json["countBack"] == 3
        assert "User-Agent" in headers
        return HttpResponse(200, "application/json", json.dumps(payload).encode("utf-8"))

    result = fetch_vietcap_iq_gap_chart_live(
        ["FPT"],
        output_base_dir=tmp_path / "raw",
        count_back=3,
        allow_network=True,
        http_post=fake_post,
        run_id="run1",
    )

    assert result["status"] == "ok"
    assert result["symbols_loaded"] == ["FPT"]
    item = result["payloads"][0]
    raw_path = Path(item["raw_path"])
    metadata_path = Path(item["metadata_path"])
    assert raw_path.exists()
    assert metadata_path.exists()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["source_name"] == "vietcap_iq"
    assert metadata["symbol"] == "FPT"
    assert metadata["request_params"]["body_json"]["countBack"] == 3
    assert metadata["row_count"] == 3
    assert metadata["status"] == "success"
    assert metadata["content_hash"] == item["content_hash"]
    assert metadata["caveats"]
    metadata_text = metadata_path.read_text(encoding="utf-8")
    forbidden = ["Cookie", "Authorization", "Bearer", "token", "secret"]
    assert not any(value in metadata_text for value in forbidden)


def test_live_adapter_partial_response_is_structured(tmp_path: Path) -> None:
    calls = []

    def fake_post(url, body_json, headers, timeout_seconds):
        calls.append(body_json["symbols"][0])
        if body_json["symbols"] == ["FPT"]:
            return HttpResponse(200, "application/json", json.dumps([_payload("FPT", bars=1)]).encode("utf-8"))
        return HttpResponse(403, "application/json", b'{"error":"forbidden"}')

    result = fetch_vietcap_iq_gap_chart_live(
        ["FPT", "HPG"],
        output_base_dir=tmp_path / "raw",
        count_back=1,
        allow_network=True,
        http_post=fake_post,
        run_id="run2",
    )

    assert calls == ["FPT", "HPG"]
    assert result["status"] == "partial_ok"
    assert result["symbols_loaded"] == ["FPT"]
    assert result["symbols_failed"] == ["HPG"]
    assert any("HPG fetch status" in caveat for caveat in result["caveats"])


def test_live_adapter_error_response_has_no_traceback(tmp_path: Path) -> None:
    def fake_post(url, body_json, headers, timeout_seconds):
        raise RuntimeError("offline")

    result = fetch_vietcap_iq_gap_chart_live(
        ["FPT"],
        output_base_dir=tmp_path / "raw",
        allow_network=True,
        http_post=fake_post,
        run_id="run3",
    )

    assert result["status"] == "error"
    assert result["symbols_failed"] == ["FPT"]
    assert result["payloads"][0]["status"] == "error"
    assert Path(result["payloads"][0]["metadata_path"]).exists()
    assert "offline" in result["caveats"][0]


def test_live_adapter_rejects_more_than_three_symbols(tmp_path: Path) -> None:
    calls = []

    def fake_post(url, body_json, headers, timeout_seconds):
        calls.append(body_json)
        raise AssertionError("max-symbol guard must run before http_post")

    result = fetch_vietcap_iq_gap_chart_live(
        ["FPT", "VNM", "VCB", "MSN"],
        output_base_dir=tmp_path / "raw",
        allow_network=True,
        http_post=fake_post,
    )

    assert result["status"] == "error"
    assert calls == []
    assert "at most 3 symbols" in result["caveats"][0]


def test_live_adapter_non_json_body_returns_structured_failure(tmp_path: Path) -> None:
    def fake_post(url, body_json, headers, timeout_seconds):
        return HttpResponse(200, "text/html", b"<html>blocked</html>")

    result = fetch_vietcap_iq_gap_chart_live(
        ["FPT"],
        output_base_dir=tmp_path / "raw",
        allow_network=True,
        http_post=fake_post,
        run_id="run4",
    )

    assert result["status"] == "error"
    assert result["symbols_failed"] == ["FPT"]
    assert result["payloads"][0]["status"] == "rejected_response"
    metadata = json.loads(Path(result["payloads"][0]["metadata_path"]).read_text(encoding="utf-8"))
    assert metadata["status"] == "rejected_response"
    assert metadata["raw_path"].endswith("payload.json")


def _payload(symbol: str, *, bars: int) -> dict[str, object]:
    return {
        "symbol": symbol,
        "t": [1767225600 + 86400 * i for i in range(bars)],
        "o": [10.0 + i for i in range(bars)],
        "h": [11.0 + i for i in range(bars)],
        "l": [9.0 + i for i in range(bars)],
        "c": [10.5 + i for i in range(bars)],
        "v": [1000 + i for i in range(bars)],
        "accumulatedVolume": [1000 + i for i in range(bars)],
        "accumulatedValue": [10000 + i for i in range(bars)],
    }
