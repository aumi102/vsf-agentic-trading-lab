from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SOURCE = "vietcap_iq_gap_chart"
SOURCE_NAME = "vietcap_iq"
ENDPOINT = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart"
DEFAULT_COUNT_BACK = 5000
DEFAULT_TIME_FRAME = "ONE_DAY"
DEFAULT_MAX_LIVE_SYMBOLS = 3
TERMS_NOTES = (
    "Controlled Vietcap Trading gap-chart live adapter. Explicit small-symbol "
    "runs only; no full-universe crawl, scheduler, DB migration, or backtest."
)


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    content_type: str
    body: bytes


def fetch_vietcap_iq_gap_chart_live(
    symbols: list[str],
    *,
    output_base_dir: str | Path,
    count_back: int = DEFAULT_COUNT_BACK,
    allow_network: bool = False,
    timeout_seconds: int = 20,
    max_symbols: int = DEFAULT_MAX_LIVE_SYMBOLS,
    http_post: Callable[[str, dict[str, Any], dict[str, str], int], HttpResponse] | None = None,
    run_id: str | None = None,
    to_epoch_seconds: int | None = None,
) -> dict[str, Any]:
    requested = _normalize_symbols(symbols)
    caveats: list[str] = []
    if not requested:
        return _result("error", requested, [], [], [], ["At least one symbol is required."])
    if not allow_network:
        return _result(
            "error",
            requested,
            [],
            requested,
            [],
            ["Live adapter requires explicit allow_network=True. No network request was made."],
        )
    if len(requested) > max_symbols:
        return _result(
            "error",
            requested,
            [],
            requested,
            [],
            [f"Live adapter supports at most {max_symbols} symbols per run."],
        )
    if count_back <= 0:
        return _result("error", requested, [], requested, [], ["count_back must be positive."])
    if timeout_seconds <= 0:
        return _result("error", requested, [], requested, [], ["timeout_seconds must be positive."])

    adapter_run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    to_epoch = int(to_epoch_seconds) if to_epoch_seconds is not None else int(datetime.now(timezone.utc).timestamp())
    output_dir = Path(output_base_dir) / adapter_run_id
    post = http_post or _post_json
    payloads: list[dict[str, object]] = []
    loaded: list[str] = []
    failed: list[str] = []

    for symbol in requested:
        dataset = _dataset_name(symbol=symbol, count_back=count_back)
        body_json = _request_body(symbol=symbol, count_back=count_back, to_epoch_seconds=to_epoch)
        try:
            response = post(ENDPOINT, body_json, _headers(symbol), timeout_seconds)
            record = _write_symbol_output(
                output_dir=output_dir,
                symbol=symbol,
                dataset=dataset,
                body_json=body_json,
                response=response,
                run_id=adapter_run_id,
            )
            payloads.append(record)
            if record["status"] == "success":
                loaded.append(symbol)
            else:
                failed.append(symbol)
                caveats.append(f"{symbol} fetch status: {record['status']}.")
        except Exception as exc:  # pragma: no cover - defensive network isolation
            failed.append(symbol)
            payloads.append(
                _write_error_metadata(
                    output_dir=output_dir,
                    symbol=symbol,
                    dataset=dataset,
                    body_json=body_json,
                    run_id=adapter_run_id,
                    error=str(exc),
                )
            )
            caveats.append(f"{symbol} fetch error: {exc}")

    status = "ok" if loaded and not failed else "partial_ok" if loaded else "error"
    return _result(status, requested, loaded, failed, payloads, caveats)


def _post_json(url: str, body_json: dict[str, Any], headers: dict[str, str], timeout_seconds: int) -> HttpResponse:
    body_bytes = json.dumps(body_json, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body_bytes, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return HttpResponse(
                status_code=int(getattr(response, "status", 0) or 0),
                content_type=response.headers.get("content-type", ""),
                body=response.read(),
            )
    except HTTPError as exc:
        return HttpResponse(
            status_code=exc.code,
            content_type=exc.headers.get("content-type", "") if exc.headers else "",
            body=exc.read(),
        )
    except (TimeoutError, URLError, OSError) as exc:
        raise RuntimeError(f"request_error:{exc}") from exc


def _write_symbol_output(
    *,
    output_dir: Path,
    symbol: str,
    dataset: str,
    body_json: dict[str, Any],
    response: HttpResponse,
    run_id: str,
) -> dict[str, object]:
    dataset_dir = output_dir / dataset
    dataset_dir.mkdir(parents=True, exist_ok=True)
    payload_path = dataset_dir / "payload.json"
    payload_text, parsed_json = _payload_text(response.body)
    payload_path.write_text(payload_text, encoding="utf-8")
    content_hash = hashlib.sha256(payload_path.read_bytes()).hexdigest()
    status = "success" if _classify_access_status(response) == "verified" else _classify_access_status(response)
    metadata = {
        "source_name": SOURCE_NAME,
        "adapter_name": "controlled_live_gap_chart_adapter",
        "dataset": dataset,
        "symbol": symbol,
        "endpoint_or_surface": ENDPOINT,
        "request_params": {
            "method": "POST",
            "body_json": body_json,
            "header_names": sorted(_headers(symbol).keys()),
        },
        "request_body": body_json,
        "run_id": run_id,
        "access_status": _classify_access_status(response),
        "auth_mode": "browser_like_headers_no_credentials",
        "http_status": response.status_code,
        "content_type": response.content_type,
        "content_hash": content_hash,
        "byte_size": len(response.body),
        "raw_path": str(payload_path),
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "row_count": _row_count(parsed_json),
        "caveats": _metadata_caveats(status),
        "terms_notes": TERMS_NOTES,
    }
    metadata_path = dataset_dir / "metadata.json"
    _write_json(metadata_path, metadata)
    return {
        "symbol": symbol,
        "raw_path": str(payload_path),
        "metadata_path": str(metadata_path),
        "content_hash": content_hash,
        "row_count": metadata["row_count"],
        "status": status,
    }


def _write_error_metadata(
    *,
    output_dir: Path,
    symbol: str,
    dataset: str,
    body_json: dict[str, Any],
    run_id: str,
    error: str,
) -> dict[str, object]:
    dataset_dir = output_dir / dataset
    dataset_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = dataset_dir / "metadata.json"
    metadata = {
        "source_name": SOURCE_NAME,
        "adapter_name": "controlled_live_gap_chart_adapter",
        "dataset": dataset,
        "symbol": symbol,
        "endpoint_or_surface": ENDPOINT,
        "request_params": {"method": "POST", "body_json": body_json},
        "request_body": body_json,
        "run_id": run_id,
        "access_status": "error",
        "auth_mode": "browser_like_headers_no_credentials",
        "http_status": None,
        "content_type": "",
        "content_hash": "",
        "byte_size": 0,
        "raw_path": "",
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "status": "error",
        "row_count": 0,
        "error": error,
        "caveats": [f"fetch_error:{error}"],
        "terms_notes": TERMS_NOTES,
    }
    _write_json(metadata_path, metadata)
    return {
        "symbol": symbol,
        "raw_path": "",
        "metadata_path": str(metadata_path),
        "content_hash": "",
        "row_count": 0,
        "status": "error",
    }


def _request_body(*, symbol: str, count_back: int, to_epoch_seconds: int) -> dict[str, Any]:
    return {
        "symbols": [symbol],
        "timeFrame": DEFAULT_TIME_FRAME,
        "countBack": int(count_back),
        "to": int(to_epoch_seconds),
    }


def _headers(symbol: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
        "Content-Type": "application/json",
        "Origin": "https://trading.vietcap.com.vn",
        "Referer": f"https://trading.vietcap.com.vn/iq/company?ticker={symbol}&tab=overview&isIndex=false",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36 vsf-controlled-fetch/0.1",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }


def _classify_access_status(response: HttpResponse) -> str:
    if response.status_code in {401, 403}:
        return "auth_required"
    if response.status_code < 200 or response.status_code >= 300:
        return "error"
    try:
        json.loads(response.body.decode("utf-8-sig"))
    except json.JSONDecodeError:
        return "rejected_response"
    return "verified"


def _payload_text(body: bytes) -> tuple[str, Any | None]:
    text = body.decode("utf-8-sig", errors="replace")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text, None
    return json.dumps(parsed, indent=2, ensure_ascii=False), parsed


def _row_count(payload: Any | None) -> int:
    if isinstance(payload, list):
        count = 0
        for item in payload:
            if isinstance(item, dict) and isinstance(item.get("t"), list):
                count += len(item["t"])
            else:
                count += 1
        return count
    return 1 if payload is not None else 0


def _dataset_name(*, symbol: str, count_back: int) -> str:
    return f"vietcap_iq_gap_chart_{symbol.lower()}_countback_{int(count_back)}"


def _metadata_caveats(status: str) -> list[str]:
    caveats = [
        "Controlled live adapter; explicit small-symbol runs only.",
        "No full-universe crawl, scheduler, broker execution, or trading action.",
    ]
    if status != "success":
        caveats.append(f"Payload status is {status}; parser/ingestion may skip it.")
    return caveats


def _normalize_symbols(symbols: list[str]) -> list[str]:
    seen = set()
    normalized = []
    for item in symbols:
        symbol = str(item or "").strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            normalized.append(symbol)
    return normalized


def _result(
    status: str,
    requested: list[str],
    loaded: list[str],
    failed: list[str],
    payloads: list[dict[str, object]],
    caveats: list[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "source": SOURCE,
        "mode": "live",
        "symbols_requested": requested,
        "symbols_loaded": sorted(loaded),
        "symbols_failed": sorted(failed),
        "payloads": payloads,
        "caveats": caveats,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
