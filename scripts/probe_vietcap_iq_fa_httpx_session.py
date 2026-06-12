from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SYMBOL = "VCI"
DEFAULT_SECTION = "BALANCE_SHEET"
DEFAULT_USER_AGENT = "vsf-source-probe/0.1 vietcap-iq-fa-diagnostic"
DEFAULT_DATASET = "vietcap_iq_fa_financial_statement_balance_sheet_httpx_session"
DEFAULT_OUTPUT_ROOT = ROOT / "data/raw/httpx_diagnostic/source=vietcap_iq"
SOURCE_NAME = "vietcap_iq"

SEARCH_BAR_URL = "https://iq.vietcap.com.vn/api/iq-insight-service/v2/company/search-bar?language=1"
SEARCH_BAR_DATASET = "vietcap_iq_company_search_bar_httpx_parity"
FA_DIRECT_DATASET = "vietcap_iq_fa_financial_statement_balance_sheet_direct_parity"

# Referer style templates; {symbol} is substituted at runtime.
_REFERER_STYLES: dict[str, str] = {
    "trading-company-page": (
        "https://trading.vietcap.com.vn/iq/company"
        "?ticker={symbol}&tab=overview&isIndex=false"
    ),
    "iq-main-page": "https://iq.vietcap.com.vn/",
    "none": "",
}


def build_default_page_url(symbol: str) -> str:
    return (
        f"https://trading.vietcap.com.vn/iq/company"
        f"?ticker={symbol}&tab=financial&isIndex=false&financialTab=financialStatement"
    )


def build_default_api_url(symbol: str, section: str) -> str:
    return (
        f"https://iq.vietcap.com.vn/api/iq-insight-service/v1/company"
        f"/{symbol}/financial-statement?section={section}"
    )


def build_warmup_urls(symbol: str) -> list[str]:
    return [
        "https://trading.vietcap.com.vn/api/configuration-service/v1/non-authen/app-config",
        "https://trading.vietcap.com.vn/api/price/marketStatus/getAll",
        "https://trading.vietcap.com.vn/api/market-data-service/v1/data-version",
        "https://iq.vietcap.com.vn/api/iq-insight-service/v2/company/search-bar?language=1",
        f"https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/details?ticker={symbol}",
    ]


def build_referer(style: str, symbol: str) -> str:
    template = _REFERER_STYLES.get(style, "")
    return template.format(symbol=symbol) if template else ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Vietcap IQ FA httpx browser-session warm-up diagnostic."
    )
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--section", default=DEFAULT_SECTION)
    parser.add_argument("--page-url", default=None)
    parser.add_argument("--api-url", default=None)
    parser.add_argument("--dataset", default=None)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--skip-warmup", action="store_true", default=False)
    parser.add_argument(
        "--diagnostic-target",
        choices=["fa", "search-bar", "fa-direct"],
        default="fa",
        help=(
            "'fa' runs the full FA httpx warm-up session; "
            "'search-bar' runs a direct parity probe on the search-bar URL; "
            "'fa-direct' runs a clean single-request probe on the FA endpoint."
        ),
    )
    parser.add_argument(
        "--referer-style",
        choices=["trading-company-page", "iq-main-page", "none"],
        default="trading-company-page",
        help="Referer header style for search-bar and fa-direct targets.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    symbol = args.symbol.strip().upper()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if args.diagnostic_target == "search-bar":
        dataset = args.dataset or SEARCH_BAR_DATASET
        try:
            result = run_search_bar_parity_diagnostic(
                symbol=symbol,
                target_url=SEARCH_BAR_URL,
                dataset=dataset,
                output_root=Path(args.output_root),
                timeout_seconds=args.timeout_seconds,
                run_id=run_id,
                user_agent=args.user_agent,
                referer_style=args.referer_style,
            )
        except Exception as exc:  # pragma: no cover - defensive CLI isolation
            print(f"vietcap_iq_search_bar_parity_failed={exc}", file=sys.stderr)
            return 1

        _print_parity_result(result)
        return 0

    if args.diagnostic_target == "fa-direct":
        api_url = args.api_url or build_default_api_url(symbol, args.section)
        dataset = args.dataset or FA_DIRECT_DATASET
        try:
            result = run_fa_direct_parity_diagnostic(
                symbol=symbol,
                section=args.section,
                target_url=api_url,
                dataset=dataset,
                output_root=Path(args.output_root),
                timeout_seconds=args.timeout_seconds,
                run_id=run_id,
                user_agent=args.user_agent,
                referer_style=args.referer_style,
            )
        except Exception as exc:  # pragma: no cover - defensive CLI isolation
            print(f"vietcap_iq_fa_direct_parity_failed={exc}", file=sys.stderr)
            return 1

        _print_parity_result(result)
        return 0

    # fa mode
    page_url = args.page_url or build_default_page_url(symbol)
    api_url = args.api_url or build_default_api_url(symbol, args.section)
    dataset = args.dataset or DEFAULT_DATASET
    try:
        result = run_httpx_session_diagnostic(
            symbol=symbol,
            page_url=page_url,
            api_url=api_url,
            dataset=dataset,
            output_root=Path(args.output_root),
            timeout_seconds=args.timeout_seconds,
            run_id=run_id,
            user_agent=args.user_agent,
            skip_warmup=args.skip_warmup,
        )
    except Exception as exc:  # pragma: no cover - defensive CLI isolation
        print(f"vietcap_iq_fa_httpx_session_failed={exc}", file=sys.stderr)
        return 1

    print(f"run_id={result['run_id']}")
    print(f"symbol={result['symbol']}")
    print(f"dataset={result['dataset']}")
    print(f"output_dir={result['output_dir']}")
    print(f"page_http_status={result['page_http_status']}")
    for ws in result["warmup_statuses"]:
        print(f"warmup url={ws['url_path']} status={ws['status']} content_type={ws['content_type']}")
    print(f"api_http_status={result['api_http_status']}")
    print(f"access_status={result['access_status']}")
    print(f"api_content_type={result['api_content_type']}")
    print(f"raw_path={result['raw_path'] or 'none'}")
    print(f"metadata_path={result['metadata_path']}")
    print(f"response_top_level_type={result['response_top_level_type']}")
    print(f"response_top_level_keys={','.join(result['response_top_level_keys'])}")
    print(f"data_type={result['data_type']}")
    print(f"data_length={result['data_length'] if result['data_length'] is not None else 'none'}")
    print(f"data_keys={','.join(result['data_keys'])}")
    return 0


def _print_parity_result(result: dict[str, Any]) -> None:
    print(f"run_id={result['run_id']}")
    print(f"symbol={result['symbol']}")
    print(f"diagnostic_target={result['diagnostic_target']}")
    print(f"referer_style={result['referer_style']}")
    print(f"dataset={result['dataset']}")
    print(f"output_dir={result['output_dir']}")
    print(f"http_status={result['http_status']}")
    print(f"access_status={result['access_status']}")
    print(f"content_type={result['content_type']}")
    print(f"raw_path={result['raw_path'] or 'none'}")
    print(f"metadata_path={result['metadata_path']}")
    print(f"response_top_level_type={result['response_top_level_type']}")
    print(f"response_top_level_keys={','.join(result['response_top_level_keys'])}")
    print(f"data_type={result['data_type']}")
    print(f"data_length={result['data_length'] if result['data_length'] is not None else 'none'}")
    print(f"data_keys={','.join(result['data_keys'])}")


def run_search_bar_parity_diagnostic(
    *,
    symbol: str,
    target_url: str,
    dataset: str,
    output_root: Path,
    timeout_seconds: float,
    run_id: str,
    user_agent: str = DEFAULT_USER_AGENT,
    referer_style: str = "trading-company-page",
    client_factory: Callable[..., httpx.Client] = httpx.Client,
) -> dict[str, Any]:
    """Direct, fresh httpx GET to the search-bar URL — no prior page load or warm-up."""
    dataset_dir = output_root / f"run_id={safe_path_part(run_id)}" / safe_path_part(dataset)
    dataset_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    errors: list[str] = []
    status: int | None = None
    content_type = ""
    parsed_payload: Any = None
    raw_path = ""
    byte_size = 0
    content_hash = ""
    access_status = "error"

    referer = build_referer(referer_style, symbol)
    hdrs = build_search_bar_headers(referer, user_agent)

    try:
        with client_factory(timeout=timeout_seconds, follow_redirects=True) as client:
            response = client.get(target_url, headers=hdrs)
            status = response.status_code
            content_type = response.headers.get("content-type", "")
            if response.status_code in {401, 403}:
                access_status = "auth_required"
                errors.append(f"HTTP Error {response.status_code}")
            elif response.status_code != 200:
                access_status = "error"
                errors.append(f"HTTP Error {response.status_code}")
            elif "json" not in content_type.lower():
                access_status = "error"
                errors.append(f"response_content_type_not_json:{content_type}")
            else:
                parsed_payload = response.json()
                payload_bytes = json.dumps(parsed_payload, indent=2, ensure_ascii=False).encode("utf-8")
                byte_size = len(payload_bytes)
                content_hash = hashlib.sha256(payload_bytes).hexdigest()
                payload_path = dataset_dir / "payload.json"
                payload_path.write_bytes(payload_bytes)
                raw_path = str(payload_path)
                access_status = "verified"
                warnings.append("raw_sample_captured_but_schema_not_promoted")
    except httpx.HTTPError as exc:
        access_status = "error"
        errors.append(str(exc))

    shape = inspect_payload_shape(parsed_payload)
    metadata_path = dataset_dir / "metadata.json"
    metadata = {
        "run_id": run_id,
        "source_name": SOURCE_NAME,
        "symbol": symbol.strip().upper(),
        "diagnostic_target": "search-bar",
        "target_url": target_url,
        "referer_style": referer_style,
        "dataset": dataset,
        "http_status": status,
        "content_type": content_type,
        "access_status": access_status,
        "raw_path": raw_path,
        "metadata_path": str(metadata_path),
        "byte_size": byte_size,
        "content_hash": content_hash,
        "response_top_level_type": shape["response_top_level_type"],
        "response_top_level_keys": shape["response_top_level_keys"],
        "data_type": shape["data_type"],
        "data_keys": shape["data_keys"],
        "data_length": shape["data_length"],
        "manual_header_names": sorted(hdrs.keys()),
        "manual_cookie_header_set": False,
        "manual_authorization_header_set": False,
        "cookies_saved": False,
        "authorization_saved": False,
        "warnings": warnings,
        "errors": errors,
        "terms_notes": (
            "Httpx search-bar parity diagnostic only. No manual Cookie or Authorization headers, "
            "no parser, no DB write, no backtest."
        ),
        "crawled_at": datetime.now(timezone.utc).isoformat(),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    result = dict(metadata)
    result["output_dir"] = str(dataset_dir)
    return result


def run_fa_direct_parity_diagnostic(
    *,
    symbol: str,
    section: str,
    target_url: str,
    dataset: str,
    output_root: Path,
    timeout_seconds: float,
    run_id: str,
    user_agent: str = DEFAULT_USER_AGENT,
    referer_style: str = "trading-company-page",
    client_factory: Callable[..., httpx.Client] = httpx.Client,
) -> dict[str, Any]:
    """Fresh httpx GET to the FA endpoint — no prior page load or warm-up, 8-header clean profile."""
    dataset_dir = output_root / f"run_id={safe_path_part(run_id)}" / safe_path_part(dataset)
    dataset_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    errors: list[str] = []
    status: int | None = None
    content_type = ""
    parsed_payload: Any = None
    raw_path = ""
    byte_size = 0
    content_hash = ""
    access_status = "error"

    referer = build_referer(referer_style, symbol)
    hdrs = build_search_bar_headers(referer, user_agent)

    try:
        with client_factory(timeout=timeout_seconds, follow_redirects=True) as client:
            response = client.get(target_url, headers=hdrs)
            status = response.status_code
            content_type = response.headers.get("content-type", "")
            if response.status_code in {401, 403}:
                access_status = "auth_required"
                errors.append(f"HTTP Error {response.status_code}")
            elif response.status_code != 200:
                access_status = "error"
                errors.append(f"HTTP Error {response.status_code}")
            elif "json" not in content_type.lower():
                access_status = "error"
                errors.append(f"response_content_type_not_json:{content_type}")
            else:
                parsed_payload = response.json()
                payload_bytes = json.dumps(parsed_payload, indent=2, ensure_ascii=False).encode("utf-8")
                byte_size = len(payload_bytes)
                content_hash = hashlib.sha256(payload_bytes).hexdigest()
                payload_path = dataset_dir / "payload.json"
                payload_path.write_bytes(payload_bytes)
                raw_path = str(payload_path)
                access_status = "verified"
                warnings.append("raw_sample_captured_but_schema_not_promoted")
    except httpx.HTTPError as exc:
        access_status = "error"
        errors.append(str(exc))

    shape = inspect_payload_shape(parsed_payload)
    metadata_path = dataset_dir / "metadata.json"
    metadata = {
        "run_id": run_id,
        "source_name": SOURCE_NAME,
        "symbol": symbol.strip().upper(),
        "section": section,
        "diagnostic_target": "fa-direct",
        "target_url": target_url,
        "referer_style": referer_style,
        "dataset": dataset,
        "http_status": status,
        "content_type": content_type,
        "access_status": access_status,
        "raw_path": raw_path,
        "metadata_path": str(metadata_path),
        "byte_size": byte_size,
        "content_hash": content_hash,
        "response_top_level_type": shape["response_top_level_type"],
        "response_top_level_keys": shape["response_top_level_keys"],
        "data_type": shape["data_type"],
        "data_keys": shape["data_keys"],
        "data_length": shape["data_length"],
        "manual_header_names": sorted(hdrs.keys()),
        "manual_cookie_header_set": False,
        "manual_authorization_header_set": False,
        "cookies_saved": False,
        "authorization_saved": False,
        "warnings": warnings,
        "errors": errors,
        "terms_notes": (
            "Httpx FA direct clean-profile parity diagnostic only. No manual Cookie or Authorization headers, "
            "no warm-up, no parser, no DB write, no backtest."
        ),
        "crawled_at": datetime.now(timezone.utc).isoformat(),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    result = dict(metadata)
    result["output_dir"] = str(dataset_dir)
    return result


def run_httpx_session_diagnostic(
    *,
    symbol: str,
    page_url: str,
    api_url: str,
    dataset: str,
    output_root: Path,
    timeout_seconds: float,
    run_id: str,
    user_agent: str = DEFAULT_USER_AGENT,
    skip_warmup: bool = False,
    client_factory: Callable[..., httpx.Client] = httpx.Client,
) -> dict[str, Any]:
    dataset_dir = output_root / f"run_id={safe_path_part(run_id)}" / safe_path_part(dataset)
    dataset_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    errors: list[str] = []
    page_status: int | None = None
    api_status: int | None = None
    api_content_type = ""
    parsed_payload: Any = None
    raw_path = ""
    byte_size = 0
    content_hash = ""
    access_status = "error"
    warmup_statuses: list[dict[str, Any]] = []

    warmup_urls = [] if skip_warmup else build_warmup_urls(symbol)

    try:
        with client_factory(timeout=timeout_seconds, follow_redirects=True) as client:
            page_response = client.get(page_url, headers=page_headers(user_agent))
            page_status = page_response.status_code

            for wu_url in warmup_urls:
                wu_resp = client.get(wu_url, headers=json_headers(page_url, user_agent))
                warmup_statuses.append({
                    "url_path": wu_url,
                    "status": wu_resp.status_code,
                    "content_type": wu_resp.headers.get("content-type", ""),
                })

            api_response = client.get(api_url, headers=json_headers(page_url, user_agent))
            api_status = api_response.status_code
            api_content_type = api_response.headers.get("content-type", "")
            if api_response.status_code in {401, 403}:
                access_status = "auth_required"
                errors.append(f"HTTP Error {api_response.status_code}")
            elif api_response.status_code != 200:
                access_status = "error"
                errors.append(f"HTTP Error {api_response.status_code}")
            elif "json" not in api_content_type.lower():
                access_status = "error"
                errors.append(f"response_content_type_not_json:{api_content_type}")
            else:
                parsed_payload = api_response.json()
                payload_bytes = json.dumps(parsed_payload, indent=2, ensure_ascii=False).encode("utf-8")
                byte_size = len(payload_bytes)
                content_hash = hashlib.sha256(payload_bytes).hexdigest()
                payload_path = dataset_dir / "payload.json"
                payload_path.write_bytes(payload_bytes)
                raw_path = str(payload_path)
                access_status = "verified"
                warnings.append("raw_sample_captured_but_schema_not_promoted")
    except httpx.HTTPError as exc:
        access_status = "error"
        errors.append(str(exc))

    shape = inspect_payload_shape(parsed_payload)
    metadata_path = dataset_dir / "metadata.json"
    metadata = {
        "run_id": run_id,
        "source_name": SOURCE_NAME,
        "symbol": symbol.strip().upper(),
        "page_url": page_url,
        "api_url": api_url,
        "dataset": dataset,
        "page_http_status": page_status,
        "warmup_statuses": warmup_statuses,
        "api_http_status": api_status,
        "api_content_type": api_content_type,
        "access_status": access_status,
        "raw_path": raw_path,
        "metadata_path": str(metadata_path),
        "byte_size": byte_size,
        "content_hash": content_hash,
        "response_top_level_type": shape["response_top_level_type"],
        "response_top_level_keys": shape["response_top_level_keys"],
        "data_type": shape["data_type"],
        "data_keys": shape["data_keys"],
        "data_length": shape["data_length"],
        "manual_header_names": sorted(json_headers(page_url, user_agent).keys()),
        "manual_cookie_header_set": False,
        "manual_authorization_header_set": False,
        "cookies_saved": False,
        "authorization_saved": False,
        "warnings": warnings,
        "errors": errors,
        "terms_notes": (
            "Httpx browser-session warm-up diagnostic only. No manual Cookie or Authorization headers, "
            "no parser, no DB write, no backtest."
        ),
        "crawled_at": datetime.now(timezone.utc).isoformat(),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    result = dict(metadata)
    result["output_dir"] = str(dataset_dir)
    return result


def build_search_bar_headers(referer: str, user_agent: str) -> dict[str, str]:
    """Headers matching the previously successful source-probe search-bar profile (no sec-ch-ua*)."""
    headers: dict[str, str] = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
        "User-Agent": user_agent,
        "Origin": "https://trading.vietcap.com.vn",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def page_headers(user_agent: str) -> dict[str, str]:
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
        "User-Agent": user_agent,
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Upgrade-Insecure-Requests": "1",
    }


def json_headers(page_url: str, user_agent: str) -> dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
        "User-Agent": user_agent,
        "Origin": "https://trading.vietcap.com.vn",
        "Referer": page_url,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "sec-ch-ua": '"Microsoft Edge";v="148", "Chromium";v="148", "Not_A Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }


def inspect_payload_shape(payload: Any) -> dict[str, Any]:
    top_level_type = type(payload).__name__ if payload is not None else "none"
    top_level_keys: list[str] = sorted(str(key) for key in payload.keys()) if isinstance(payload, dict) else []
    data = payload.get("data") if isinstance(payload, dict) else None
    data_type = type(data).__name__ if data is not None else "none"
    data_keys: list[str] = sorted(str(key) for key in data.keys()) if isinstance(data, dict) else []
    data_length = len(data) if isinstance(data, list) else None
    return {
        "response_top_level_type": top_level_type,
        "response_top_level_keys": top_level_keys,
        "data_type": data_type,
        "data_keys": data_keys,
        "data_length": data_length,
    }


def safe_path_part(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "_.=-" else "_" for ch in value.strip()) or "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
