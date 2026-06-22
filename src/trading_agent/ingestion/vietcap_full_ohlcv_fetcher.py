"""Vietcap full-universe daily OHLCV fetcher (sequential, non-async).

Reuses the two endpoints already verified in this repo:

  * Universe : https://iq.vietcap.com.vn/api/iq-insight-service/v2/company/search-bar?language=1
               (saved sample parsed by vietcap_iq_universe_parser; ~2083 rows)
  * OHLCV    : https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart
               POST {"symbols":[SYM],"timeFrame":"ONE_DAY","countBack":N,"to":epoch}

The gap-chart payload returns a single OHLC series that already appears
split/dividend back-adjusted, but exposes NO separate raw-vs-adjusted field.
Per the no-fabrication rule we therefore record adjustment_factor=1.0 and
adjustment_status="adjusted_price_missing_warn" and store the same source
series in both the raw and adjusted columns. The adjustment helper still
implements the from-adjusted-close branch so a future source that *does*
expose an adjusted close drops in without code changes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# --- Verified endpoints ------------------------------------------------------
UNIVERSE_URL = "https://iq.vietcap.com.vn/api/iq-insight-service/v2/company/search-bar?language=1"
OHLCV_ENDPOINT = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart"

SOURCE_NAME = "vietcap_iq"
SOURCE_ID = "vietcap_iq_gap_chart"
PRICE_BASIS = "source_reported"
PARSER_VERSION = "vietcap_full_ohlcv_fetcher_v1"
DEFAULT_TIME_FRAME = "ONE_DAY"

# HOSE / HNX / UPCOM are the listed, tradable boards. OTC / OTHER / STOP and
# index rows are excluded (matches the repo's tradable-universe filter).
TRADABLE_FLOORS = {"HOSE", "HNX", "UPCOM"}

# Canonical column order written to the QuestDB CSV (matched to table by name).
DAILY_PRICES_COLUMNS = [
    "trade_date",
    "security_id",
    "symbol",
    "exchange",
    "open",
    "high",
    "low",
    "close",
    "adjusted_open",
    "adjusted_high",
    "adjusted_low",
    "adjusted_close",
    "volume",
    "value",
    "adjustment_factor",
    "price_basis",
    "adjustment_status",
    "quality_status",
    "source_id",
    "raw_path",
    "ingested_at",
]


# --- HTTP helpers ------------------------------------------------------------
@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    content_type: str
    body: bytes


def _browser_headers(referer: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
        "Origin": "https://trading.vietcap.com.vn",
        "Referer": referer,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125 Safari/537.36 vsf-full-ingest/0.1"
        ),
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }


def ohlcv_headers(symbol: str) -> dict[str, str]:
    headers = _browser_headers(
        f"https://trading.vietcap.com.vn/iq/company?ticker={symbol}&tab=overview&isIndex=false"
    )
    headers["Content-Type"] = "application/json"
    return headers


def universe_headers() -> dict[str, str]:
    return _browser_headers("https://trading.vietcap.com.vn/")


def _http_get(url: str, headers: dict[str, str], timeout_seconds: int) -> HttpResponse:
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return HttpResponse(
                status_code=int(getattr(response, "status", 0) or 0),
                content_type=response.headers.get("content-type", ""),
                body=response.read(),
            )
    except HTTPError as exc:
        return HttpResponse(exc.code, exc.headers.get("content-type", "") if exc.headers else "", exc.read())
    except (TimeoutError, URLError, OSError) as exc:
        raise RuntimeError(f"request_error:{exc}") from exc


def _http_post_json(url: str, body: dict[str, Any], headers: dict[str, str], timeout_seconds: int) -> HttpResponse:
    body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body_bytes, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return HttpResponse(
                status_code=int(getattr(response, "status", 0) or 0),
                content_type=response.headers.get("content-type", ""),
                body=response.read(),
            )
    except HTTPError as exc:
        return HttpResponse(exc.code, exc.headers.get("content-type", "") if exc.headers else "", exc.read())
    except (TimeoutError, URLError, OSError) as exc:
        raise RuntimeError(f"request_error:{exc}") from exc


# --- Universe ----------------------------------------------------------------
def fetch_universe_payload(timeout_seconds: int = 30) -> tuple[dict[str, Any], int, bytes]:
    response = _http_get(UNIVERSE_URL, universe_headers(), timeout_seconds)
    text = response.body.decode("utf-8-sig", errors="replace")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"universe_payload_not_json:http_{response.status_code}:{exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("universe_payload_not_object")
    return payload, response.status_code, response.body


def extract_universe(payload: dict[str, Any]) -> dict[str, Any]:
    """Filter the search-bar payload into a tradable, de-duplicated universe.

    Returns a dict with the tradable rows plus diagnostic counts so callers can
    print/raise on coverage.
    """
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise RuntimeError("universe_payload_missing_data_list")

    total_raw = len(rows)
    excluded_index = 0
    excluded_floor = 0
    excluded_invalid = 0
    seen: set[str] = set()
    tradable: list[dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            excluded_invalid += 1
            continue
        symbol = str(row.get("code") or "").strip().upper()
        floor = str(row.get("floor") or "").strip().upper()
        is_index = bool(row.get("isIndex"))
        if not symbol:
            excluded_invalid += 1
            continue
        if is_index:
            excluded_index += 1
            continue
        if floor not in TRADABLE_FLOORS:
            excluded_floor += 1
            continue
        if symbol in seen:
            continue
        seen.add(symbol)
        tradable.append(
            {
                "symbol": symbol,
                "security_id": f"{SOURCE_NAME}:{symbol}",
                "exchange": floor,
                "company_name": str(row.get("name") or "").strip(),
                "short_name": str(row.get("shortName") or "").strip(),
                "company_type_code": str(row.get("comTypeCode") or "").strip(),
            }
        )

    tradable.sort(key=lambda item: item["symbol"])
    return {
        "tradable": tradable,
        "total_raw_rows": total_raw,
        "unique_tradable_symbols": len(tradable),
        "excluded_index_rows": excluded_index,
        "excluded_non_tradable_floor_rows": excluded_floor,
        "excluded_invalid_rows": excluded_invalid,
    }


# --- OHLCV fetch -------------------------------------------------------------
@dataclass
class SymbolFetchResult:
    symbol: str
    status: str  # ok | rate_limited | timeout | http_error | empty | bad_json
    http_status: int | None
    body: bytes | None
    error: str | None = None


def ohlcv_request_body(symbol: str, count_back: int, to_epoch: int) -> dict[str, Any]:
    return {
        "symbols": [symbol],
        "timeFrame": DEFAULT_TIME_FRAME,
        "countBack": int(count_back),
        "to": int(to_epoch),
    }


def fetch_symbol_ohlcv(
    symbol: str,
    *,
    count_back: int,
    to_epoch: int,
    timeout_seconds: int = 30,
) -> SymbolFetchResult:
    """Single sequential gap-chart fetch with rate-limit classification."""
    body = ohlcv_request_body(symbol, count_back, to_epoch)
    try:
        response = _http_post_json(OHLCV_ENDPOINT, body, ohlcv_headers(symbol), timeout_seconds)
    except RuntimeError as exc:
        text = str(exc)
        status = "timeout" if "timed out" in text.lower() or "timeout" in text.lower() else "http_error"
        return SymbolFetchResult(symbol, status, None, None, text)

    if response.status_code in {429, 403, 503}:
        return SymbolFetchResult(symbol, "rate_limited", response.status_code, response.body)
    if response.status_code < 200 or response.status_code >= 300:
        return SymbolFetchResult(symbol, "http_error", response.status_code, response.body)

    try:
        json.loads(response.body.decode("utf-8-sig"))
    except json.JSONDecodeError as exc:
        return SymbolFetchResult(symbol, "bad_json", response.status_code, response.body, str(exc))
    return SymbolFetchResult(symbol, "ok", response.status_code, response.body)


# --- Parse + adjust + validate ----------------------------------------------
def compute_adjustment(
    open_: float,
    high: float,
    low: float,
    close: float,
    adjusted_close: float | None,
) -> tuple[float, float, float, float, float, str]:
    """Return (adj_open, adj_high, adj_low, adj_close, factor, status).

    Honest handling per the no-fabrication rule:
      * adjusted_close present and != close  -> scale OHL by factor
      * adjusted_close present and == close  -> no_adjustment_needed
      * adjusted_close missing               -> copy raw, factor 1.0, warn
    """
    if adjusted_close is None:
        return open_, high, low, close, 1.0, "adjusted_price_missing_warn"
    if close is None or close <= 0:
        return open_, high, low, close, 1.0, "adjusted_price_missing_warn"
    if abs(adjusted_close - close) < 1e-9:
        return open_, high, low, close, 1.0, "no_adjustment_needed"
    factor = adjusted_close / close
    return open_ * factor, high * factor, low * factor, adjusted_close, factor, "adjusted_from_source_adjusted_close"


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:  # NaN
        return None
    return result


def _validate_ohlc(o: float | None, h: float | None, l: float | None, c: float | None, v: float | None) -> list[str]:
    reasons: list[str] = []
    if None in (o, h, l, c):
        reasons.append("missing_ohlc")
        return reasons
    if h < l:
        reasons.append("high_lt_low")
    if h < max(o, c):
        reasons.append("high_lt_max_open_close")
    if l > min(o, c):
        reasons.append("low_gt_min_open_close")
    if v is not None and v < 0:
        reasons.append("negative_volume")
    return reasons


@dataclass
class ParseResult:
    rows: list[dict[str, Any]] = field(default_factory=list)        # valid, ready to ingest
    quarantined: list[dict[str, Any]] = field(default_factory=list)  # failed validation
    adjusted_from_source: int = 0
    no_adjustment_needed: int = 0
    adjusted_missing_warn: int = 0
    duplicates_dropped: int = 0
    out_of_range_dropped: int = 0


def parse_symbol_payload(
    symbol: str,
    security_id: str,
    exchange: str,
    body: bytes,
    *,
    from_date: str,
    to_date: str,
    raw_path: str,
    ingested_at: str,
) -> ParseResult:
    """Parse one gap-chart payload into canonical, validated, adjusted rows."""
    result = ParseResult()
    payload = json.loads(body.decode("utf-8-sig"))
    if not isinstance(payload, list) or not payload:
        return result
    obj = payload[0]
    if not isinstance(obj, dict):
        return result

    times = obj.get("t") or []
    opens = obj.get("o") or []
    highs = obj.get("h") or []
    lows = obj.get("l") or []
    closes = obj.get("c") or []
    volumes = obj.get("v") or []
    values = obj.get("accumulatedValue") or []
    n = min(len(times), len(opens), len(highs), len(lows), len(closes))

    seen_dates: set[str] = set()
    for i in range(n):
        epoch = _to_float(times[i])
        if epoch is None or epoch <= 0:
            continue
        try:
            trade_day = datetime.fromtimestamp(epoch, timezone.utc).date().isoformat()
        except (OSError, OverflowError, ValueError):
            continue
        if trade_day < from_date or trade_day > to_date:
            result.out_of_range_dropped += 1
            continue
        if trade_day in seen_dates:
            result.duplicates_dropped += 1
            continue
        seen_dates.add(trade_day)

        o = _to_float(opens[i])
        h = _to_float(highs[i])
        l = _to_float(lows[i])
        c = _to_float(closes[i])
        v = _to_float(volumes[i]) if i < len(volumes) else None
        val = _to_float(values[i]) if i < len(values) else None

        # gap-chart exposes no separate adjusted close -> adjusted_close=None.
        adj_o, adj_h, adj_l, adj_c, factor, adj_status = compute_adjustment(o, h, l, c, None)
        if adj_status == "adjusted_from_source_adjusted_close":
            result.adjusted_from_source += 1
        elif adj_status == "no_adjustment_needed":
            result.no_adjustment_needed += 1
        else:
            result.adjusted_missing_warn += 1

        reasons = _validate_ohlc(o, h, l, c, v)
        record = {
            "trade_date": f"{trade_day}T00:00:00.000000Z",
            "security_id": security_id,
            "symbol": symbol,
            "exchange": exchange,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "adjusted_open": adj_o,
            "adjusted_high": adj_h,
            "adjusted_low": adj_l,
            "adjusted_close": adj_c,
            "volume": v,
            "value": val,
            "adjustment_factor": factor,
            "price_basis": PRICE_BASIS,
            "adjustment_status": adj_status,
            "quality_status": "fail" if reasons else "pass",
            "source_id": SOURCE_ID,
            "raw_path": raw_path,
            "ingested_at": ingested_at,
        }
        if reasons:
            record["quality_reasons"] = ";".join(reasons)
            result.quarantined.append(record)
        else:
            result.rows.append(record)

    result.rows.sort(key=lambda r: r["trade_date"])
    return result


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def make_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
