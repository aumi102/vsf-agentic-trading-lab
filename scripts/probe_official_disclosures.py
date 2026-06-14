"""Controlled probe for official disclosure surfaces (HOSE, HNX, company IR).

Plan mode (default) builds a fetch plan without making network calls.
Execute mode (--execute) fetches configured targets sequentially with rate limiting.
Force mode (--execute --force) re-fetches already completed targets.

Targets without a configured URL are listed in the plan as NOT_CONFIGURED and are
skipped during execute. Supply real URLs via --targets-config JSON.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import html as html_lib
import json
import re
import random
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.source_adapters.disclosure_adapter import (
    BRONZE_PARSER_VERSION,
    BRONZE_SCHEMA_VERSION,
    DisclosureRecord,
    DisclosureTarget,
    assign_pit_status,
    check_disclosure_quality,
)


MIN_SLEEP_SECONDS = 2.0
MAX_REQUESTS_DEFAULT = 5
DEFAULT_MAX_RECORDS_PER_TARGET = 20

_DEFAULT_REQUEST_HEADERS: dict[str, str] = {
    "User-Agent": "vsf-agentic-trading-lab/0.1 official-source-probe",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8",
    "Connection": "close",
}
DEFAULT_SYMBOLS = "FPT,VCI"
DEFAULT_OUTPUT_BASE = ROOT / "data/raw/official_disclosures"
DEFAULT_BRONZE_BASE = ROOT / "data/bronze/official_disclosures"

_FPT_OFFICIAL_DOMAIN = "fpt.com"
_VCI_OFFICIAL_DOMAIN = "www.vietcap.com.vn"
_PROJECT_USER_AGENT = _DEFAULT_REQUEST_HEADERS["User-Agent"]
_SAFE_CONFIG_HEADERS = frozenset({"Accept", "Accept-Language", "Connection", "User-Agent"})
_FORBIDDEN_CONFIG_KEYS = frozenset({
    "ssl_verify",
    "verify",
    "insecure",
    "cookie",
    "authorization",
    "proxy-authorization",
})
_SECRET_KEY_FRAGMENTS = ("token", "api_key", "password", "client_secret", "session")
_BROWSER_UA_MARKERS = ("Mozilla", "Chrome", "Chromium", "Safari", "Firefox", "Edge", "Edg/")
_DOCUMENT_URL_MISSING = "document_url_missing"

# Matches a single FPT IR disclosure block: link+title+date.
# FPT IR uses Sitecore CMS. Structure confirmed from fpt.com/en/ir/information-disclosures.
_DISCLOSURE_BLOCK_RE = re.compile(
    r'<div class="media-download-section-key-information-content">\s*'
    r'<a class="media-download-section-key-information-content-subtitle"\s+'
    r'href="([^"]+)"[^>]*>\s*([^<]+?)\s*</a>'
    r'.*?Updated:\s*(\d{1,2}/\d{1,2}/\d{4})',
    re.DOTALL,
)

# Vietcap IR detail-page patterns
_VCI_DATE_RE = re.compile(
    r'\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})\b',
    re.IGNORECASE,
)
_VCI_H1_RE = re.compile(r'<h1[^>]*>\s*([^<]+?)\s*</h1>', re.IGNORECASE | re.DOTALL)
_VCI_H2_RE = re.compile(r'<h2[^>]*>\s*([^<]+?)\s*</h2>', re.IGNORECASE | re.DOTALL)
_VCI_TITLE_TAG_RE = re.compile(r'<title[^>]*>\s*([^<]+?)\s*</title>', re.IGNORECASE)
_VCI_PDF_RE = re.compile(r'href="([^"]*\.pdf[^"]*)"', re.IGNORECASE)
_ANCHOR_RE = re.compile(
    r'<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_HREF_RE = re.compile(r'\bhref\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_VI_DATE_RE = re.compile(r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b')

GUARDRAILS = [
    "No network requests unless --execute is supplied.",
    "Targets without a configured URL are skipped; status=not_configured.",
    "Requests processed sequentially with concurrency=1.",
    "Random sleep applied between execute-mode requests.",
    "Raw payload and metadata captured before parsing.",
    "No database write, migration, backtest, or full-universe fetch.",
    "No secret values written to output files.",
]

_TARGETS_SCHEMA_VERSION = "disclosure_targets_config_v1"

# Access statuses that produce no disclosure records.
_PROBE_ONLY_STATUSES: frozenset[str] = frozenset({
    "blocked", "auth_required", "rejected_response",
    "not_configured", "error", "js_app_shell",
})


@dataclass(frozen=True)
class DocumentUrlValidation:
    url: str
    warning_code: str = ""


# ---------------------------------------------------------------------------
# HTTP primitives
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    content_type: str
    body: bytes
    response_headers: dict[str, str]


def get_url(
    url: str,
    headers: dict[str, str],
    *,
    timeout: int = 20,
) -> HttpResponse:
    merged = {**_DEFAULT_REQUEST_HEADERS, **headers}
    request = Request(url, headers=merged, method="GET")
    try:
        with urlopen(request, timeout=timeout) as resp:
            return HttpResponse(
                status_code=int(getattr(resp, "status", 0) or 0),
                content_type=resp.headers.get("content-type", ""),
                body=resp.read(),
                response_headers={k: v for k, v in resp.headers.items()},
            )
    except HTTPError as exc:
        return HttpResponse(
            status_code=exc.code,
            content_type=exc.headers.get("content-type", "") if exc.headers else "",
            body=exc.read() or b"",
            response_headers={k: v for k, v in (exc.headers or {}).items()},
        )
    except (TimeoutError, URLError, OSError) as exc:
        raise RuntimeError(f"request_error:{exc}") from exc


def classify_access_status(response: HttpResponse) -> str:
    if response.status_code in {401, 403}:
        return "auth_required"
    if response.status_code == 0 or response.status_code >= 500:
        return "error"
    if response.status_code < 200 or response.status_code >= 300:
        return "rejected_response"
    # HTTP 200-range: check for JS-only SPA shell (cannot serve structured data without JS).
    ct = response.content_type.lower()
    if "html" in ct and len(response.body) < 8000:
        body_text = response.body.decode("utf-8", errors="replace")
        body_lc = body_text.lower()
        if (
            "you need to enable javascript" in body_lc
            or "enable javascript to run this app" in body_lc
            or (
                len(response.body) < 5000
                and any(marker in body_text for marker in ('id="root"', 'id="app"', 'id="HOSE"', 'id="HNX"'))
            )
        ):
            return "js_app_shell"
    return "verified"


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

def build_default_targets(symbols: list[str]) -> list[DisclosureTarget]:
    targets: list[DisclosureTarget] = []
    for symbol in symbols:
        sym = symbol.upper().strip()
        targets.append(DisclosureTarget(
            source_family="hose",
            exchange="HOSE",
            official_domain="www.hsx.vn",
            adapter_name="hose_disclosure_adapter_v1",
            dataset=f"hose_disclosures_{sym.lower()}",
            symbol=sym,
            url="",
            terms_notes=(
                "HOSE official disclosure page. React SPA — structured disclosure API not "
                "resolvable from static JS. Official parent page captured as html_ajax_shell."
            ),
        ))
        targets.append(DisclosureTarget(
            source_family="hnx",
            exchange="HNX",
            official_domain="www.hnx.vn",
            adapter_name="hnx_disclosure_adapter_v1",
            dataset=f"hnx_disclosures_{sym.lower()}",
            symbol=sym,
            url="",
            terms_notes=(
                "HNX official disclosure page. jQuery AJAX — disclosures loaded dynamically. "
                "Official parent page captured; disclosure feed endpoint unresolved."
            ),
        ))
    targets.append(DisclosureTarget(
        source_family="company_ir",
        exchange="HOSE",
        official_domain=_FPT_OFFICIAL_DOMAIN,
        adapter_name="company_ir_fpt_v1",
        dataset="company_ir_fpt_disclosures",
        symbol="FPT",
        url="",
        terms_notes=(
            "FPT Corporation official IR page (positive control). "
            "Server-rendered Sitecore CMS. Supply URL via targets-config to enable. "
            "Confirmed URL: fpt.com/en/ir/information-disclosures."
        ),
    ))
    targets.append(DisclosureTarget(
        source_family="company_ir",
        exchange="HOSE",
        official_domain=_VCI_OFFICIAL_DOMAIN,
        adapter_name="company_ir_vietcap_v1",
        dataset="company_ir_vci_fy2025_fs",
        symbol="VCI",
        url="",
        terms_notes=(
            "VCI (Viet Capital Securities) official IR — FY2025 Financial Statements detail page. "
            "www.vietcap.com.vn verified as official VCI domain."
        ),
    ))
    targets.append(DisclosureTarget(
        source_family="company_ir",
        exchange="HOSE",
        official_domain=_VCI_OFFICIAL_DOMAIN,
        adapter_name="company_ir_vietcap_v1",
        dataset="company_ir_vci_q1_2026_fs",
        symbol="VCI",
        url="",
        terms_notes=(
            "VCI (Viet Capital Securities) official IR — Q1 2026 Financial Statements detail page. "
            "www.vietcap.com.vn verified as official VCI domain."
        ),
    ))
    return targets


def apply_targets_config(
    targets: list[DisclosureTarget],
    config: dict[str, Any],
) -> list[DisclosureTarget]:
    """Overlay existing targets and append explicit validated targets by dataset."""
    validate_targets_config(config)
    overrides: dict[str, dict[str, Any]] = {}
    for entry in config.get("targets", []):
        dataset = entry.get("dataset", "")
        if dataset:
            overrides[dataset] = entry
    result: list[DisclosureTarget] = []
    for t in targets:
        ov = overrides.get(t.dataset, {})
        if ov:
            updates = {
                k: ov[k]
                for k in (
                    "source_family",
                    "exchange",
                    "official_domain",
                    "adapter_name",
                    "dataset",
                    "symbol",
                    "url",
                    "method",
                    "headers",
                    "request_params",
                    "terms_notes",
                )
                if k in ov
            }
            official_domain = str(updates.get("official_domain", t.official_domain)).strip()
            url = str(updates.get("url", t.url)).strip()
            _validate_target_url(url, official_domain, dataset=t.dataset)
            if "headers" in updates:
                updates["headers"] = _validate_safe_headers(updates["headers"], dataset=t.dataset)
            t = dataclasses.replace(t, **updates)
        result.append(t)
    existing = {t.dataset for t in result}
    for dataset, ov in overrides.items():
        if dataset in existing:
            continue
        if not _looks_like_additional_target(ov):
            continue
        result.append(_target_from_config_entry(ov))
    return result


def _looks_like_additional_target(entry: dict[str, Any]) -> bool:
    return any(
        str(entry.get(name, "")).strip()
        for name in ("source_family", "exchange", "adapter_name", "symbol", "official_domain")
    )


def _target_from_config_entry(entry: dict[str, Any]) -> DisclosureTarget:
    dataset = str(entry.get("dataset", "")).strip()
    if not dataset:
        raise ValueError("Additional target requires dataset")
    required = ("source_family", "exchange", "official_domain", "adapter_name", "symbol", "url")
    missing = [name for name in required if not str(entry.get(name, "")).strip()]
    if missing:
        raise ValueError(f"Additional target {dataset} missing required field(s): {missing}")
    official_domain = str(entry["official_domain"]).strip()
    url = str(entry["url"]).strip()
    _validate_target_url(url, official_domain, dataset=dataset)
    headers = _validate_safe_headers(entry.get("headers", {}), dataset=dataset) if "headers" in entry else {}
    request_params = entry.get("request_params", {})
    if not isinstance(request_params, dict):
        raise ValueError(f"request_params for {dataset} must be an object")
    return DisclosureTarget(
        source_family=str(entry["source_family"]).strip(),
        exchange=str(entry["exchange"]).strip(),
        official_domain=official_domain,
        adapter_name=str(entry["adapter_name"]).strip(),
        dataset=dataset,
        symbol=str(entry["symbol"]).strip().upper(),
        url=url,
        method=str(entry.get("method", "GET")).strip() or "GET",
        headers=headers,
        request_params=request_params,
        terms_notes=str(entry.get("terms_notes", "")).strip(),
    )


def load_targets_config(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid targets config JSON at {path}: {exc}") from exc


def validate_targets_config(config: dict[str, Any]) -> None:
    _validate_config_tree(config)
    targets = config.get("targets", [])
    if targets is None:
        return
    if not isinstance(targets, list):
        raise ValueError("targets config field must be a list")
    for idx, entry in enumerate(targets):
        if not isinstance(entry, dict):
            raise ValueError(f"targets[{idx}] must be an object")
        dataset = str(entry.get("dataset", f"index_{idx}"))
        if "headers" in entry:
            _validate_safe_headers(entry["headers"], dataset=dataset)
        official_domain = str(entry.get("official_domain", "")).strip()
        url = str(entry.get("url", "")).strip()
        if url and official_domain:
            _validate_target_url(url, official_domain, dataset=dataset)


def validate_pit_breadth_registry(config: dict[str, Any]) -> None:
    """Validate the PIT breadth registry without making network calls."""
    _validate_config_tree(config)
    targets = config.get("targets", [])
    if not isinstance(targets, list) or not targets:
        raise ValueError("pit breadth registry requires a non-empty targets list")
    seen: set[tuple[str, str]] = set()
    required = (
        "symbol",
        "issuer_name",
        "sector",
        "exchange",
        "target_period",
        "target_document_type",
        "official_source_family",
        "official_domain",
        "url",
        "adapter",
        "parser",
        "expected_max_requests",
        "current_access_status",
        "notes",
    )
    for idx, entry in enumerate(targets):
        if not isinstance(entry, dict):
            raise ValueError(f"targets[{idx}] must be an object")
        missing = [name for name in required if not str(entry.get(name, "")).strip()]
        if missing:
            raise ValueError(f"targets[{idx}] missing required field(s): {missing}")
        symbol = str(entry["symbol"]).strip().upper()
        period = str(entry["target_period"]).strip().lower()
        key = (symbol, period)
        if key in seen:
            raise ValueError(f"Duplicate symbol/period target: {symbol} {period}")
        seen.add(key)
        url = str(entry["url"]).strip()
        official_domain = str(entry["official_domain"]).strip()
        _validate_target_url(url, official_domain, dataset=f"{symbol}_{period}")
        source_type = str(entry.get("official_source_family", "")).strip().lower()
        if source_type.startswith("secondary") or "aggregator" in source_type:
            raise ValueError(f"Secondary canonical source rejected for {symbol} {period}")
        if "headers" in entry:
            _validate_safe_headers(entry["headers"], dataset=f"{symbol}_{period}")


def _validate_config_tree(value: Any, path: str = "config") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_str = str(key)
            key_lc = key_str.strip().lower()
            if key_lc in _FORBIDDEN_CONFIG_KEYS:
                raise ValueError(f"Forbidden config key at {path}.{key_str}: {key_str}")
            if any(fragment in key_lc for fragment in _SECRET_KEY_FRAGMENTS):
                raise ValueError(f"Secret-like config key at {path}.{key_str}: {key_str}")
            _validate_config_tree(nested, f"{path}.{key_str}")
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            _validate_config_tree(item, f"{path}[{idx}]")


def _validate_safe_headers(headers: Any, *, dataset: str) -> dict[str, str]:
    if not isinstance(headers, dict):
        raise ValueError(f"headers for {dataset} must be an object")
    safe: dict[str, str] = {}
    for key, value in headers.items():
        name = str(key).strip()
        if name not in _SAFE_CONFIG_HEADERS:
            raise ValueError(f"Forbidden header for {dataset}: {name}")
        value_str = str(value).strip()
        if name == "User-Agent":
            value_lc = value_str.lower()
            if any(marker.lower() in value_lc for marker in _BROWSER_UA_MARKERS):
                raise ValueError(f"Browser impersonation User-Agent rejected for {dataset}")
            if value_str != _PROJECT_USER_AGENT:
                raise ValueError(f"User-Agent for {dataset} must equal the project User-Agent")
        safe[name] = value_str
    return safe


def _validate_target_url(url: str, official_domain: str, *, dataset: str) -> None:
    if not url:
        return
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"Target URL for {dataset} must use https")
    if not parsed.hostname:
        raise ValueError(f"Target URL for {dataset} is malformed")
    if parsed.hostname.lower() != official_domain.lower():
        raise ValueError(
            f"Target URL host for {dataset} must match official_domain={official_domain}"
        )


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

def build_fetch_plan(
    *,
    targets: list[DisclosureTarget],
    max_requests: int,
    sleep_min_seconds: float,
    sleep_max_seconds: float,
    execute: bool,
    force: bool,
    run_id: str,
    output_base: Path,
    bronze_base: Path,
    checkpoint_path: Path,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    configured = [t for t in targets if t.is_configured]
    not_configured = [t for t in targets if not t.is_configured]

    planned_requests = configured[:max_requests]
    capped = len(configured) > max_requests

    request_items = []
    for i, target in enumerate(planned_requests, start=1):
        request_items.append({
            "planned_order": i,
            "dataset": target.dataset,
            "source_family": target.source_family,
            "exchange": target.exchange,
            "symbol": target.symbol,
            "url": target.url,
            "method": target.method,
            "output_dir": str(output_base / run_id / target.dataset),
            "bronze_dir": str(bronze_base / run_id / target.dataset),
        })

    skipped_items = [
        {"dataset": t.dataset, "reason": "not_configured", "source_family": t.source_family, "symbol": t.symbol}
        for t in not_configured
    ]
    if capped:
        for t in configured[max_requests:]:
            skipped_items.append({
                "dataset": t.dataset,
                "reason": "max_requests_reached",
                "source_family": t.source_family,
                "symbol": t.symbol,
            })

    summary: dict[str, Any] = {
        "run_id": run_id,
        "started_at": started_at,
        "mode": "execute" if execute else "plan_only",
        "network_requests_made": False,
        "output_base": str(output_base),
        "bronze_base": str(bronze_base),
        "checkpoint_path": str(checkpoint_path),
        "total_targets": len(targets),
        "configured_targets": len(configured),
        "planned_request_count": len(planned_requests),
        "max_requests": max_requests,
        "sleep_min_seconds": sleep_min_seconds,
        "sleep_max_seconds": sleep_max_seconds,
        "force": force,
        "completed_datasets": [],
        "failed_datasets": [],
        "pending_datasets": [item["dataset"] for item in request_items],
        "guardrails": GUARDRAILS,
    }
    return {
        "summary": summary,
        "requests": request_items,
        "skipped": skipped_items,
    }


def build_plan_report(plan: dict[str, Any]) -> str:
    summary = plan["summary"]
    lines = [
        "# Official Disclosure Probe Plan",
        "",
        f"- run_id: `{summary['run_id']}`",
        f"- mode: `{summary['mode']}`",
        f"- total_targets: {summary['total_targets']}",
        f"- configured_targets: {summary['configured_targets']}",
        f"- planned_request_count: {summary['planned_request_count']}",
        f"- max_requests: {summary['max_requests']}",
        f"- sleep_range_seconds: `{summary['sleep_min_seconds']} - {summary['sleep_max_seconds']}`",
        "",
        "## Planned Requests",
        "",
        "| Order | Symbol | Exchange | Dataset | URL |",
        "|---:|---|---|---|---|",
    ]
    for item in plan["requests"]:
        url_display = item["url"][:60] + "…" if len(item["url"]) > 60 else item["url"] or "(not configured)"
        lines.append(
            f"| {item['planned_order']} | `{item['symbol']}` | {item['exchange']} "
            f"| `{item['dataset']}` | {url_display} |"
        )
    if plan["skipped"]:
        lines.extend(["", "## Skipped Targets", ""])
        for item in plan["skipped"]:
            lines.append(f"- `{item['dataset']}` ({item['source_family']}/{item['symbol']}): {item['reason']}")
    lines.extend(["", "## Guardrails", ""])
    for g in summary["guardrails"]:
        lines.append(f"- {g}")
    if plan.get("parse_summaries"):
        lines.extend([
            "",
            "## Parse Summaries",
            "",
            "| Dataset | Access | HTTP | Parser | Parse status | Bronze records | Warnings | Errors |",
            "|---|---|---:|---|---|---:|---|---|",
        ])
        for item in plan["parse_summaries"]:
            warnings = ",".join(item.get("warning_codes", []))
            errors = ",".join(item.get("error_codes", []))
            lines.append(
                f"| `{item['dataset']}` | `{item['access_status']}` | {item['http_status']} "
                f"| `{item['parser_name']}` | `{item['parse_status']}` "
                f"| {item['bronze_record_count']} | `{warnings}` | `{errors}` |"
            )
    if summary["mode"] == "plan_only":
        lines.extend(["", "No network requests were made."])
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------

def build_checkpoint(
    *,
    run_id: str,
    started_at: str,
    completed_datasets: list[str],
    failed_datasets: list[str],
    pending_datasets: list[str],
    plan_path: str,
    parse_summaries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "started_at": started_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "completed_datasets": completed_datasets,
        "failed_datasets": failed_datasets,
        "pending_datasets": pending_datasets,
        "plan_path": plan_path,
        "parse_summaries": parse_summaries or [],
    }


def load_checkpoint(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _replace_parse_summary(
    parse_summaries: list[dict[str, Any]],
    parse_summary: dict[str, Any],
) -> None:
    dataset = parse_summary.get("dataset")
    parse_summaries[:] = [
        item for item in parse_summaries
        if item.get("dataset") != dataset
    ]
    parse_summaries.append(parse_summary)


# ---------------------------------------------------------------------------
# Raw evidence capture
# ---------------------------------------------------------------------------

def capture_raw_evidence(
    *,
    output_dir: Path,
    target: DisclosureTarget,
    response: HttpResponse,
    run_id: str,
) -> tuple[Path, Path]:
    """Write payload + metadata; return (payload_path, metadata_path)."""
    output_dir.mkdir(parents=True, exist_ok=True)

    content_type = response.content_type.lower()
    if "json" in content_type:
        ext = "json"
        try:
            payload_text = json.dumps(json.loads(response.body.decode("utf-8-sig")), indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload_text = response.body.decode("utf-8-sig", errors="replace")
    elif "html" in content_type:
        ext = "html"
        payload_text = response.body.decode("utf-8-sig", errors="replace")
    else:
        ext = "bin"
        payload_text = response.body.decode("utf-8-sig", errors="replace")

    payload_path = output_dir / f"payload.{ext}"
    payload_path.write_text(payload_text, encoding="utf-8")

    body_sha256 = hashlib.sha256(response.body).hexdigest()
    access_status = classify_access_status(response)

    metadata: dict[str, Any] = {
        "source_family": target.source_family,
        "exchange": target.exchange,
        "official_domain": target.official_domain,
        "adapter_name": target.adapter_name,
        "dataset": target.dataset,
        "symbol": target.symbol,
        "url": target.url,
        "method": target.method,
        "run_id": run_id,
        "access_status": access_status,
        "http_status": response.status_code,
        "content_type": response.content_type,
        "body_sha256": body_sha256,
        "byte_size": len(response.body),
        "raw_path": str(payload_path),
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "terms_notes": target.terms_notes,
    }
    metadata_path = output_dir / "metadata.json"
    _write_json(metadata_path, metadata)

    request_doc: dict[str, Any] = {
        "method": target.method,
        "url": target.url,
        "header_names": sorted(target.headers.keys()),
        "request_params": target.request_params,
    }
    _write_json(output_dir / "request.json", request_doc)

    return payload_path, metadata_path


# ---------------------------------------------------------------------------
# FPT IR HTML parser
# ---------------------------------------------------------------------------

def _normalize_document_url(
    href: str,
    *,
    official_domain: str,
    allowed_hosts: set[str] | None = None,
) -> DocumentUrlValidation:
    raw = (href or "").strip()
    if not raw:
        return DocumentUrlValidation("", _DOCUMENT_URL_MISSING)
    if raw.startswith("//"):
        return DocumentUrlValidation("", "invalid_document_url")
    if raw.startswith("/"):
        return DocumentUrlValidation(f"https://{official_domain}{raw}")

    parsed = urlparse(raw)
    if parsed.scheme.lower() in {"javascript", "data", "file"}:
        return DocumentUrlValidation("", "unsafe_document_url_scheme")
    if not parsed.scheme or not parsed.netloc:
        return DocumentUrlValidation("", "invalid_document_url")
    if parsed.scheme.lower() != "https":
        return DocumentUrlValidation("", "unsafe_document_url_scheme")
    if parsed.username or parsed.password:
        return DocumentUrlValidation("", "off_domain_document_url")
    host = (parsed.hostname or "").lower()
    if not host:
        return DocumentUrlValidation("", "invalid_document_url")
    approved = {official_domain.lower(), *(allowed_hosts or set())}
    if host not in approved:
        return DocumentUrlValidation("", "off_domain_document_url")
    return DocumentUrlValidation(raw)


def _normalize_fpt_url_with_warning(href: str) -> DocumentUrlValidation:
    return _normalize_document_url(href, official_domain=_FPT_OFFICIAL_DOMAIN)


def _normalize_fpt_url(href: str) -> str:
    return _normalize_fpt_url_with_warning(href).url


def _parse_fpt_date(date_str: str) -> str:
    """Parse M/D/YYYY from FPT IR page into YYYY-MM-DD. Returns '' on failure."""
    try:
        return datetime.strptime(date_str.strip(), "%m/%d/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _infer_fpt_doc_category(title: str, href: str) -> str:
    title_lc = title.lower()
    href_lc = href.lower()
    if "annual report" in title_lc or "annual-report" in href_lc:
        return "annual_report"
    if ("financial statement" in title_lc or "financial-statement" in href_lc) and any(
        q in title_lc or q in href_lc for q in ("quarter", "q1", "q2", "q3", "q4")
    ):
        return "quarterly_financial_statement"
    if "financial statement" in title_lc or "financial-statement" in href_lc:
        return "financial_statement"
    if "resolution" in title_lc:
        return "board_resolution"
    return "disclosure"


_HTML_ENTITY_MAP = {
    "&#39;": "'", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
    "&nbsp;": " ", "&#x27;": "'", "&#x2F;": "/",
}


def _decode_html_entities(text: str) -> str:
    for entity, char in _HTML_ENTITY_MAP.items():
        text = text.replace(entity, char)
    return html_lib.unescape(text)


def _fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", ascii_text).strip().lower()


def _parse_vietnamese_date(date_str: str) -> str:
    match = _VI_DATE_RE.search(date_str or "")
    if not match:
        return ""
    day, month, year = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    try:
        return datetime(year, month, day).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _first_vi_date(context: str) -> str:
    for match in _VI_DATE_RE.finditer(context or ""):
        parsed = _parse_vietnamese_date(match.group(0))
        if parsed:
            return parsed
    return ""


def _infer_company_ir_doc_category(target: DisclosureTarget) -> str:
    expected = str(target.request_params.get("expected_period_type", "")).strip().lower()
    if expected == "annual":
        return "annual_financial_statement"
    if expected == "quarterly":
        return "quarterly_financial_statement"
    return "financial_statement"


def _company_ir_semantics_match(target: DisclosureTarget, title: str, href: str, context: str) -> bool:
    folded = _fold_text(f"{title} {href}")
    expected_period = str(target.request_params.get("expected_period_label", "")).strip().lower()
    expected_type = str(target.request_params.get("expected_period_type", "")).strip().lower()
    if any(marker in folded for marker in ("annual report", "bao cao thuong nien")):
        return False
    if not any(marker in folded for marker in ("bao cao tai chinh", "bctc", "financial statement")):
        return False
    if expected_type == "annual":
        return "2025" in folded and not any(q in folded for q in ("q1", "quy i", "quy 1", "quarter 1"))
    if expected_type == "quarterly":
        if "2026" not in folded:
            return False
        return any(q in folded for q in ("q1", "quy i", "quy 1", "quarter 1", "1st quarter"))
    if expected_period:
        return expected_period.replace(" ", "") in folded.replace(" ", "")
    return True


def _extract_company_ir_title(anchor_body: str, context: str) -> str:
    title = _compact_text(anchor_body)
    if title:
        return title
    return _compact_text(context)[:180]


def _normalize_company_ir_url_with_warning(href: str, target: DisclosureTarget) -> DocumentUrlValidation:
    allowed = {
        str(item).strip().lower()
        for item in target.request_params.get("allowed_document_domains", [])
        if str(item).strip()
    }
    return _normalize_document_url(href, official_domain=target.official_domain, allowed_hosts=allowed)


def parse_company_ir_listing_records(
    body: bytes,
    target: DisclosureTarget,
    payload_path: Path,
    metadata_path: Path,
    crawled_at: str,
    max_records: int = DEFAULT_MAX_RECORDS_PER_TARGET,
) -> list[DisclosureRecord]:
    """Parse simple company IR listing pages into target-bound financial statement records."""
    html = body.decode("utf-8", errors="replace")
    body_sha256 = hashlib.sha256(body).hexdigest()
    issuer_name = str(target.request_params.get("issuer_name") or target.symbol).strip()
    language = str(target.request_params.get("language") or "vi").strip()

    records: list[DisclosureRecord] = []
    seen_urls: set[str] = set()
    for match in _ANCHOR_RE.finditer(html):
        if len(records) >= max_records:
            break
        href_match = _HREF_RE.search(match.group("attrs"))
        if not href_match:
            continue
        href = href_match.group(1).strip()
        if not href.lower().split("?")[0].endswith(".pdf"):
            continue
        start = max(0, match.start() - 500)
        end = min(len(html), match.end() + 700)
        context_html = html[start:end]
        context_text = _compact_text(context_html)
        title = _extract_company_ir_title(match.group("body"), context_html)
        if not _company_ir_semantics_match(target, title, href, context_text):
            continue
        doc_validation = _normalize_company_ir_url_with_warning(href, target)
        if not doc_validation.url:
            continue
        if doc_validation.url in seen_urls:
            continue
        seen_urls.add(doc_validation.url)
        published_date = _first_vi_date(context_text)
        if not published_date:
            continue
        warning_codes: list[str] = []
        if doc_validation.warning_code:
            warning_codes.append(doc_validation.warning_code)
        attachment_name = doc_validation.url.split("/")[-1].split("?")[0]
        record_dict: dict[str, Any] = {
            "source_family": target.source_family,
            "exchange": target.exchange,
            "official_domain": target.official_domain,
            "adapter_name": target.adapter_name,
            "disclosure_id": f"{target.dataset}_{hashlib.sha256(doc_validation.url.encode()).hexdigest()[:12]}",
            "symbol": target.symbol,
            "issuer_name": issuer_name,
            "document_category": _infer_company_ir_doc_category(target),
            "title": title,
            "published_at": "",
            "published_date": published_date,
            "effective_at": "",
            "page_url": target.url,
            "document_url": doc_validation.url,
            "attachment_name": attachment_name,
            "attachment_type": "pdf",
            "language": language,
            "crawled_at": crawled_at,
            "raw_path": str(payload_path),
            "metadata_path": str(metadata_path),
            "body_sha256": body_sha256,
            "parser_version": BRONZE_PARSER_VERSION,
            "schema_version": BRONZE_SCHEMA_VERSION,
            "quality_status": "",
            "pit_status": assign_pit_status(
                published_at="",
                published_date=published_date,
                access_status="verified",
            ),
            "warning_codes": warning_codes,
            "error_codes": [],
        }
        quality_status, extra_warnings, extra_errors = check_disclosure_quality(record_dict)
        record_dict["quality_status"] = quality_status
        record_dict["warning_codes"] = sorted(set(warning_codes + extra_warnings))
        record_dict["error_codes"] = sorted(set(extra_errors))
        records.append(DisclosureRecord(**record_dict))
    return records


def parse_fpt_ir_html_records(
    body: bytes,
    target: DisclosureTarget,
    payload_path: Path,
    metadata_path: Path,
    crawled_at: str,
    max_records: int = DEFAULT_MAX_RECORDS_PER_TARGET,
) -> list[DisclosureRecord]:
    """Parse FPT official IR HTML into a list of DisclosureRecord (up to max_records).

    Returns [] if no items are found — no pseudo rows for non-matching pages.
    """
    html = body.decode("utf-8", errors="replace")
    body_sha256 = hashlib.sha256(body).hexdigest()
    matches = _DISCLOSURE_BLOCK_RE.findall(html)

    records: list[DisclosureRecord] = []
    seen_hrefs: set[str] = set()

    for href_raw, title_raw, date_raw in matches:
        if len(records) >= max_records:
            break
        href = href_raw.strip()
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)

        title = _decode_html_entities(title_raw.strip())
        if target.request_params.get("expected_period_type") and not _company_ir_semantics_match(
            target,
            title,
            href,
            title,
        ):
            continue
        doc_validation = _normalize_fpt_url_with_warning(href)
        doc_url = doc_validation.url
        published_date = _parse_fpt_date(date_raw)
        doc_category = _infer_fpt_doc_category(title, href)
        attachment_name = doc_url.split("/")[-1].split("?")[0] if doc_url else ""
        attachment_type = "pdf" if doc_url.lower().split("?")[0].endswith(".pdf") else ""

        disclosure_id = f"fpt_ir_{hashlib.sha256(doc_url.encode()).hexdigest()[:12]}"

        pit_status = assign_pit_status(published_at="", published_date=published_date, access_status="verified")

        warning_codes: list[str] = []
        error_codes: list[str] = []
        if not published_date:
            warning_codes.append("publication_date_unknown")
        if not title:
            warning_codes.append("title_missing")
        if doc_validation.warning_code:
            warning_codes.append(doc_validation.warning_code)

        record_dict: dict[str, Any] = {
            "source_family": target.source_family,
            "exchange": target.exchange,
            "official_domain": target.official_domain,
            "adapter_name": target.adapter_name,
            "disclosure_id": disclosure_id,
            "symbol": target.symbol,
            "issuer_name": "FPT Corporation",
            "document_category": doc_category,
            "title": title,
            "published_at": "",
            "published_date": published_date,
            "effective_at": "",
            "page_url": target.url,
            "document_url": doc_url,
            "attachment_name": attachment_name,
            "attachment_type": attachment_type,
            "language": "en",
            "crawled_at": crawled_at,
            "raw_path": str(payload_path),
            "metadata_path": str(metadata_path),
            "body_sha256": body_sha256,
            "parser_version": BRONZE_PARSER_VERSION,
            "schema_version": BRONZE_SCHEMA_VERSION,
            "quality_status": "",
            "pit_status": pit_status,
            "warning_codes": warning_codes,
            "error_codes": error_codes,
        }

        quality_status, extra_warnings, extra_errors = check_disclosure_quality(record_dict)
        record_dict["quality_status"] = quality_status
        record_dict["warning_codes"] = sorted(set(warning_codes + extra_warnings))
        record_dict["error_codes"] = sorted(set(error_codes + extra_errors))

        records.append(DisclosureRecord(**record_dict))

    return records


# ---------------------------------------------------------------------------
# Vietcap IR detail-page parser
# ---------------------------------------------------------------------------

def _normalize_vci_url_with_warning(href: str) -> DocumentUrlValidation:
    return _normalize_document_url(href, official_domain=_VCI_OFFICIAL_DOMAIN)


def _normalize_vci_url(href: str) -> str:
    return _normalize_vci_url_with_warning(href).url


def _parse_vci_date(date_str: str) -> str:
    """Parse 'D Mon YYYY' (e.g. '13 Feb 2026') from Vietcap IR page into YYYY-MM-DD."""
    try:
        return datetime.strptime(date_str.strip(), "%d %b %Y").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _infer_vci_doc_category(title: str, url: str) -> str:
    title_lc = title.lower()
    url_lc = url.lower()
    if "financial-year" in url_lc or ("annual" in title_lc and "financial" in title_lc):
        return "annual_financial_statement"
    for q in ("q1-", "q2-", "q3-", "q4-", "-q1", "-q2", "-q3", "-q4"):
        if q in url_lc or q in title_lc:
            return "quarterly_financial_statement"
    if "quarter" in title_lc or "quarter" in url_lc:
        return "quarterly_financial_statement"
    if "financial-statement" in url_lc or "financial statement" in title_lc:
        return "financial_statement"
    return "disclosure"


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value)


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", _decode_html_entities(_strip_tags(value))).strip()


def _extract_vci_detail_scope(html: str) -> str:
    start = html.find('<div class="detail-page-container"')
    if start < 0:
        return html
    end_candidates = [
        idx for idx in (
            html.find('<span class="d-none" id="parentUri"', start),
            html.find('<div class="footer', start),
            html.find('<div class="modal fade" id="login-form-modal"', start),
        )
        if idx > start
    ]
    end = min(end_candidates) if end_candidates else len(html)
    return html[start:end]


def _extract_vci_article_scope(detail_scope: str) -> str:
    article_match = re.search(
        r'<article[^>]*class="[^"]*\bbinding\b[^"]*\bfr-view\b[^"]*"[^>]*>(.*?)</article>',
        detail_scope,
        re.IGNORECASE | re.DOTALL,
    )
    return article_match.group(1) if article_match else detail_scope


def _extract_vci_title(detail_scope: str, html: str) -> str:
    for regex in (_VCI_H1_RE, _VCI_H2_RE):
        match = regex.search(detail_scope)
        if match:
            return _compact_text(match.group(1))
    title_match = _VCI_TITLE_TAG_RE.search(html)
    if title_match:
        raw = _decode_html_entities(title_match.group(1).strip())
        for sep in (" | ", " - ", " â€“ "):
            if sep in raw:
                raw = raw.split(sep)[0].strip()
        return _compact_text(raw)
    return ""


def _extract_vci_date(detail_scope: str) -> str:
    date_span = re.search(
        r'<span[^>]*class="[^"]*\bdate\b[^"]*"[^>]*>\s*([^<]+?)\s*</span>',
        detail_scope,
        re.IGNORECASE | re.DOTALL,
    )
    if date_span:
        return _parse_vci_date(_compact_text(date_span.group(1)))
    date_match = _VCI_DATE_RE.search(detail_scope)
    return _parse_vci_date(date_match.group(1)) if date_match else ""


def _expected_vci_semantics(target: DisclosureTarget) -> str:
    marker = f"{target.dataset} {target.url}".lower()
    if "q1_2026" in marker or "q1-2026" in marker:
        return "q1_2026"
    if "fy2025" in marker or "financial-year-of-2025" in marker:
        return "fy2025"
    return ""


def _vci_semantics_match(expected: str, title: str, document_url: str, article_text: str) -> bool:
    if not expected:
        return True
    text = f"{title} {document_url} {article_text}".lower()
    has_financial = "financial statement" in text or "financial statements" in text
    if expected == "fy2025":
        has_fy = (
            "financial year of 2025" in text
            or "financial statements 2025" in text
            or "fy2025" in text
        )
        has_quarter = any(q in text for q in ("q1", "q2", "q3", "q4", "quarter 1"))
        return has_financial and has_fy and not has_quarter
    if expected == "q1_2026":
        return has_financial and "2026" in text and ("q1" in text or "quarter 1" in text)
    return True


def parse_vci_ir_detail_records(
    body: bytes,
    target: DisclosureTarget,
    payload_path: Path,
    metadata_path: Path,
    crawled_at: str,
) -> list[DisclosureRecord]:
    """Parse a Vietcap IR detail page. Returns at most 1 DisclosureRecord per page.

    Returns [] if no title or date can be extracted from the page.
    """
    html = body.decode("utf-8", errors="replace")
    body_sha256 = hashlib.sha256(body).hexdigest()
    detail_scope = _extract_vci_detail_scope(html)
    article_scope = _extract_vci_article_scope(detail_scope)

    # Extract page title from h1, h2, or <title>
    title = ""
    h1_match = _VCI_H1_RE.search(html)
    if h1_match:
        title = _decode_html_entities(h1_match.group(1).strip())
    if not title:
        h2_match = _VCI_H2_RE.search(html)
        if h2_match:
            title = _decode_html_entities(h2_match.group(1).strip())
    if not title:
        title_match = _VCI_TITLE_TAG_RE.search(html)
        if title_match:
            raw = _decode_html_entities(title_match.group(1).strip())
            for sep in (" | ", " - ", " – "):
                if sep in raw:
                    raw = raw.split(sep)[0].strip()
            title = raw

    # Extract first date in "D Mon YYYY" format
    date_match = _VCI_DATE_RE.search(html)
    published_date = _parse_vci_date(date_match.group(1)) if date_match else ""
    title = _extract_vci_title(detail_scope, html)
    published_date = _extract_vci_date(detail_scope)

    # No meaningful content — return empty (no pseudo row)
    if not title and not published_date:
        return []

    # Extract first on-domain PDF URL
    document_url = ""
    for pdf_href in _VCI_PDF_RE.findall(html):
        normalized = _normalize_vci_url(pdf_href)
        if normalized:
            document_url = normalized
            break
    document_url = ""
    document_warning_codes: list[str] = []
    for pdf_href in _VCI_PDF_RE.findall(article_scope):
        normalized = _normalize_vci_url_with_warning(pdf_href)
        if normalized.url:
            document_url = normalized.url
            break
        if normalized.warning_code:
            document_warning_codes.append(normalized.warning_code)

    expected_semantics = _expected_vci_semantics(target)
    if not _vci_semantics_match(expected_semantics, title, document_url, _compact_text(article_scope)):
        return []

    doc_category = _infer_vci_doc_category(title, target.url)
    attachment_name = document_url.split("/")[-1].split("?")[0] if document_url else ""
    attachment_type = "pdf" if document_url.lower().split("?")[0].endswith(".pdf") else ""

    disclosure_id = f"vci_ir_{hashlib.sha256(target.url.encode()).hexdigest()[:12]}"

    pit_status = assign_pit_status(published_at="", published_date=published_date, access_status="verified")

    warning_codes: list[str] = []
    error_codes: list[str] = []
    if not published_date:
        warning_codes.append("publication_date_unknown")
    if not title:
        warning_codes.append("title_missing")
    if not document_url:
        warning_codes.append(document_warning_codes[0] if document_warning_codes else _DOCUMENT_URL_MISSING)

    record_dict: dict[str, Any] = {
        "source_family": target.source_family,
        "exchange": target.exchange,
        "official_domain": target.official_domain,
        "adapter_name": target.adapter_name,
        "disclosure_id": disclosure_id,
        "symbol": target.symbol,
        "issuer_name": "Viet Capital Securities",
        "document_category": doc_category,
        "title": title,
        "published_at": "",
        "published_date": published_date,
        "effective_at": "",
        "page_url": target.url,
        "document_url": document_url,
        "attachment_name": attachment_name,
        "attachment_type": attachment_type,
        "language": "en",
        "crawled_at": crawled_at,
        "raw_path": str(payload_path),
        "metadata_path": str(metadata_path),
        "body_sha256": body_sha256,
        "parser_version": BRONZE_PARSER_VERSION,
        "schema_version": BRONZE_SCHEMA_VERSION,
        "quality_status": "",
        "pit_status": pit_status,
        "warning_codes": warning_codes,
        "error_codes": error_codes,
    }

    quality_status, extra_warnings, extra_errors = check_disclosure_quality(record_dict)
    record_dict["quality_status"] = quality_status
    record_dict["warning_codes"] = sorted(set(warning_codes + extra_warnings))
    record_dict["error_codes"] = sorted(set(error_codes + extra_errors))

    return [DisclosureRecord(**record_dict)]


# ---------------------------------------------------------------------------
# Bronze parsing
# ---------------------------------------------------------------------------

def extract_disclosure_records(
    *,
    response: HttpResponse,
    target: DisclosureTarget,
    payload_path: Path,
    metadata_path: Path,
    crawled_at: str,
    max_records: int = DEFAULT_MAX_RECORDS_PER_TARGET,
) -> list[DisclosureRecord]:
    records, _summary = extract_disclosure_records_with_summary(
        response=response,
        target=target,
        payload_path=payload_path,
        metadata_path=metadata_path,
        crawled_at=crawled_at,
        max_records=max_records,
    )
    return records


def extract_disclosure_records_with_summary(
    *,
    response: HttpResponse,
    target: DisclosureTarget,
    payload_path: Path,
    metadata_path: Path,
    crawled_at: str,
    max_records: int = DEFAULT_MAX_RECORDS_PER_TARGET,
) -> tuple[list[DisclosureRecord], dict[str, Any]]:
    """Route to the appropriate parser; return a list of DisclosureRecord.

    Returns [] for probe-only statuses (shell, auth, blocked, error).
    Only actual disclosure items become DisclosureRecord entries.
    """
    access_status = classify_access_status(response)
    body_sha256 = hashlib.sha256(response.body).hexdigest()
    parser_name = _parser_name_for(target=target, response=response, access_status=access_status)
    if access_status in _PROBE_ONLY_STATUSES:
        warning_codes: list[str] = []
        error_codes: list[str] = []
        parse_status = "skipped"
        if access_status == "js_app_shell":
            warning_codes.append("js_app_shell_no_structured_data")
            parse_status = "no_structured_data"
        elif access_status == "auth_required":
            error_codes.append("auth_required_cannot_parse")
        elif access_status == "rejected_response":
            error_codes.append("rejected_response_cannot_parse")
        else:
            error_codes.append(f"fetch_status_{access_status}")
        return [], _build_parse_summary(
            target=target,
            access_status=access_status,
            http_status=response.status_code,
            parser_name=parser_name,
            parse_status=parse_status,
            records=[],
            warning_codes=warning_codes,
            error_codes=error_codes,
            raw_path=str(payload_path),
            metadata_path=str(metadata_path),
            body_sha256=body_sha256,
        )

    ct = response.content_type.lower()
    records: list[DisclosureRecord]
    if "html" in ct:
        if target.adapter_name == "company_ir_listing_v1":
            records = parse_company_ir_listing_records(
                body=response.body,
                target=target,
                payload_path=payload_path,
                metadata_path=metadata_path,
                crawled_at=crawled_at,
                max_records=max_records,
            )
        elif target.official_domain == _FPT_OFFICIAL_DOMAIN:
            records = parse_fpt_ir_html_records(
                body=response.body,
                target=target,
                payload_path=payload_path,
                metadata_path=metadata_path,
                crawled_at=crawled_at,
                max_records=max_records,
            )
        elif target.official_domain == _VCI_OFFICIAL_DOMAIN:
            records = parse_vci_ir_detail_records(
                body=response.body,
                target=target,
                payload_path=payload_path,
                metadata_path=metadata_path,
                crawled_at=crawled_at,
            )
        else:
            records = []
    else:
        records = [parse_to_bronze_record(
            response=response,
            target=target,
            payload_path=payload_path,
            metadata_path=metadata_path,
            crawled_at=crawled_at,
        )]

    warning_codes = sorted({code for record in records for code in record.warning_codes})
    error_codes = sorted({code for record in records for code in record.error_codes})
    parse_status = "parsed" if records else "no_matching_disclosures"
    if records and warning_codes:
        parse_status = "parsed_with_warnings"
    if not records:
        warning_codes.extend(_diagnose_no_record_parse_warnings(target, response.body))
        warning_codes = sorted(set(warning_codes))

    summary = _build_parse_summary(
        target=target,
        access_status=access_status,
        http_status=response.status_code,
        parser_name=parser_name,
        parse_status=parse_status,
        records=records,
        warning_codes=warning_codes,
        error_codes=error_codes,
        raw_path=str(payload_path),
        metadata_path=str(metadata_path),
        body_sha256=body_sha256,
    )
    return records, summary


def _parser_name_for(
    *,
    target: DisclosureTarget,
    response: HttpResponse | None = None,
    access_status: str = "",
) -> str:
    if access_status in _PROBE_ONLY_STATUSES:
        return "none"
    content_type = (response.content_type if response else "").lower()
    if "html" in content_type:
        if target.adapter_name == "company_ir_listing_v1":
            return "parse_company_ir_listing_records"
        if target.official_domain == _FPT_OFFICIAL_DOMAIN:
            return "parse_fpt_ir_html_records"
        if target.official_domain == _VCI_OFFICIAL_DOMAIN:
            return "parse_vci_ir_detail_records"
        return "none"
    return "parse_to_bronze_record"


def _diagnose_no_record_parse_warnings(target: DisclosureTarget, body: bytes) -> list[str]:
    if target.official_domain == _VCI_OFFICIAL_DOMAIN:
        html = body.decode("utf-8", errors="replace")
        detail_scope = _extract_vci_detail_scope(html)
        article_scope = _extract_vci_article_scope(detail_scope)
        title = _extract_vci_title(detail_scope, html)
        published_date = _extract_vci_date(detail_scope)
        document_url = ""
        for pdf_href in _VCI_PDF_RE.findall(article_scope):
            normalized = _normalize_vci_url_with_warning(pdf_href)
            if normalized.url:
                document_url = normalized.url
                break
        expected_semantics = _expected_vci_semantics(target)
        if title or published_date or document_url:
            if not _vci_semantics_match(
                expected_semantics,
                title,
                document_url,
                _compact_text(article_scope),
            ):
                return ["target_semantics_mismatch"]
        return ["no_matching_disclosures"]
    if target.official_domain == _FPT_OFFICIAL_DOMAIN:
        return ["no_matching_disclosures"]
    if target.adapter_name == "company_ir_listing_v1":
        return ["no_matching_financial_statement"]
    return ["no_structured_parser"]


def _build_parse_summary(
    *,
    target: DisclosureTarget,
    access_status: str,
    http_status: int,
    parser_name: str,
    parse_status: str,
    records: list[DisclosureRecord],
    warning_codes: list[str],
    error_codes: list[str],
    raw_path: str,
    metadata_path: str,
    body_sha256: str,
) -> dict[str, Any]:
    return {
        "dataset": target.dataset,
        "source_family": target.source_family,
        "official_domain": target.official_domain,
        "access_status": access_status,
        "http_status": http_status,
        "parser_name": parser_name,
        "parse_status": parse_status,
        "bronze_record_count": len(records),
        "warning_codes": sorted(set(warning_codes)),
        "error_codes": sorted(set(error_codes)),
        "raw_path": raw_path,
        "metadata_path": metadata_path,
        "body_sha256": body_sha256,
    }


def _build_error_parse_summary(
    *,
    target: DisclosureTarget,
    error: str,
    output_dir: Path,
) -> dict[str, Any]:
    return _build_parse_summary(
        target=target,
        access_status="error",
        http_status=0,
        parser_name="none",
        parse_status="fetch_error",
        records=[],
        warning_codes=[],
        error_codes=[error],
        raw_path="",
        metadata_path="",
        body_sha256="",
    )


def parse_to_bronze_record(
    *,
    response: HttpResponse,
    target: DisclosureTarget,
    payload_path: Path,
    metadata_path: Path,
    crawled_at: str,
) -> DisclosureRecord:
    body_sha256 = hashlib.sha256(response.body).hexdigest()
    access_status = classify_access_status(response)

    published_at = ""
    published_date = ""
    title = ""
    document_category = ""
    page_url = target.url
    document_url = ""
    language = "vi"
    issuer_name = ""
    effective_at = ""
    attachment_name = ""
    attachment_type = ""

    warning_codes: list[str] = []
    error_codes: list[str] = []

    if access_status == "verified":
        try:
            payload = json.loads(response.body.decode("utf-8-sig"))
            if isinstance(payload, dict):
                published_at = str(payload.get("publishedAt") or payload.get("publishDate") or "")
                published_date = str(payload.get("date") or payload.get("disclosureDate") or "")
                title = str(payload.get("title") or payload.get("subject") or "")
                issuer_name = str(payload.get("issuerName") or payload.get("companyName") or "")
                document_url = str(payload.get("fileUrl") or payload.get("documentUrl") or "")
                document_category = str(payload.get("category") or payload.get("docType") or "")
            elif isinstance(payload, list) and payload:
                warning_codes.append("multi_record_response_not_exploded")
        except (json.JSONDecodeError, UnicodeDecodeError):
            warning_codes.append("html_body_no_structured_parser")
    elif access_status == "js_app_shell":
        warning_codes.append("js_app_shell_no_structured_data")
    elif access_status == "auth_required":
        error_codes.append("auth_required_cannot_parse")
    elif access_status == "rejected_response":
        error_codes.append("rejected_response_cannot_parse")
    else:
        error_codes.append(f"fetch_status_{access_status}")

    pit_status = assign_pit_status(
        published_at=published_at,
        published_date=published_date,
        access_status=access_status,
    )

    disclosure_id = (
        f"{target.source_family}_{target.symbol}_{target.dataset}_{body_sha256[:12]}"
    )

    record_dict: dict[str, Any] = {
        "source_family": target.source_family,
        "exchange": target.exchange,
        "official_domain": target.official_domain,
        "adapter_name": target.adapter_name,
        "disclosure_id": disclosure_id,
        "symbol": target.symbol,
        "issuer_name": issuer_name,
        "document_category": document_category,
        "title": title,
        "published_at": published_at,
        "published_date": published_date,
        "effective_at": effective_at,
        "page_url": page_url,
        "document_url": document_url,
        "attachment_name": attachment_name,
        "attachment_type": attachment_type,
        "language": language,
        "crawled_at": crawled_at,
        "raw_path": str(payload_path),
        "metadata_path": str(metadata_path),
        "body_sha256": body_sha256,
        "parser_version": BRONZE_PARSER_VERSION,
        "schema_version": BRONZE_SCHEMA_VERSION,
        "quality_status": "",
        "pit_status": pit_status,
        "warning_codes": warning_codes,
        "error_codes": error_codes,
    }

    quality_status, extra_warnings, extra_errors = check_disclosure_quality(record_dict)
    record_dict["quality_status"] = quality_status
    record_dict["warning_codes"] = sorted(set(warning_codes + extra_warnings))
    record_dict["error_codes"] = sorted(set(error_codes + extra_errors))

    return DisclosureRecord(**record_dict)


def write_bronze_record(
    record: DisclosureRecord,
    bronze_dir: Path,
    index: int | None = None,
) -> Path:
    bronze_dir.mkdir(parents=True, exist_ok=True)
    fname = f"disclosure_record_{index:03d}.json" if index is not None else "disclosure_record.json"
    out_path = bronze_dir / fname
    _write_json(out_path, record.as_dict())
    return out_path


# ---------------------------------------------------------------------------
# Controlled probe execution
# ---------------------------------------------------------------------------

def run_disclosure_probe(
    *,
    targets: list[DisclosureTarget],
    max_requests: int,
    sleep_min_seconds: float,
    sleep_max_seconds: float,
    execute: bool,
    force: bool,
    run_id: str,
    output_base: Path,
    bronze_base: Path,
    max_records: int = DEFAULT_MAX_RECORDS_PER_TARGET,
    http_get: Callable[[str, dict[str, str]], HttpResponse] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    _validate_inputs(
        targets=targets,
        max_requests=max_requests,
        sleep_min_seconds=sleep_min_seconds,
        sleep_max_seconds=sleep_max_seconds,
        execute=execute,
    )
    output_base.mkdir(parents=True, exist_ok=True)
    run_output_dir = output_base / run_id
    checkpoint_path = run_output_dir / "checkpoint.json"
    plan_path = run_output_dir / "plan.json"
    report_path = run_output_dir / "plan_report.md"
    run_output_dir.mkdir(parents=True, exist_ok=True)

    plan = build_fetch_plan(
        targets=targets,
        max_requests=max_requests,
        sleep_min_seconds=sleep_min_seconds,
        sleep_max_seconds=sleep_max_seconds,
        execute=execute,
        force=force,
        run_id=run_id,
        output_base=output_base,
        bronze_base=bronze_base,
        checkpoint_path=checkpoint_path,
    )
    _write_json(plan_path, plan)
    report_path.write_text(build_plan_report(plan), encoding="utf-8")

    if not execute:
        return {
            "summary": plan["summary"],
            "plan": plan,
            "plan_path": plan_path,
            "report_path": report_path,
            "checkpoint_path": checkpoint_path,
        }

    prior = load_checkpoint(checkpoint_path)
    completed = set(prior.get("completed_datasets", []) if prior and not force else [])
    failed: set[str] = set(prior.get("failed_datasets", []) if prior and not force else [])

    random_source = rng or random.Random()

    parse_summaries: list[dict[str, Any]] = list(
        prior.get("parse_summaries", []) if prior and not force else []
    )

    checkpoint_doc = build_checkpoint(
        run_id=run_id,
        started_at=plan["summary"]["started_at"],
        completed_datasets=sorted(completed),
        failed_datasets=sorted(failed),
        pending_datasets=[r["dataset"] for r in plan["requests"] if r["dataset"] not in completed],
        plan_path=str(plan_path),
        parse_summaries=parse_summaries,
    )
    _write_json(checkpoint_path, checkpoint_doc)

    bronze_records: list[dict[str, Any]] = []

    for idx, request_item in enumerate(plan["requests"]):
        dataset = request_item["dataset"]
        if dataset in completed and not force:
            continue

        target = _find_target(targets, dataset)
        if target is None:
            failed.add(dataset)
            continue

        crawled_at = datetime.now(timezone.utc).isoformat()
        try:
            if http_get is not None:
                response = http_get(target.url, target.headers)
            else:
                response = get_url(target.url, target.headers)
            evidence_dir = Path(request_item["output_dir"])
            payload_path, metadata_path = capture_raw_evidence(
                output_dir=evidence_dir,
                target=target,
                response=response,
                run_id=run_id,
            )
            bronze_dir = Path(request_item["bronze_dir"])
            records, parse_summary = extract_disclosure_records_with_summary(
                response=response,
                target=target,
                payload_path=payload_path,
                metadata_path=metadata_path,
                crawled_at=crawled_at,
                max_records=max_records,
            )
            _replace_parse_summary(parse_summaries, parse_summary)
            _write_json(evidence_dir / "parse_summary.json", parse_summary)
            multi = len(records) > 1
            for rec_idx, record in enumerate(records):
                bronze_path = write_bronze_record(record, bronze_dir, index=rec_idx if multi else None)
                bronze_records.append({
                    "dataset": dataset,
                    "bronze_path": str(bronze_path),
                    "record": record.as_dict(),
                })

            _access = classify_access_status(response)
            if _access in ("verified", "js_app_shell"):
                completed.add(dataset)
                failed.discard(dataset)
            else:
                failed.add(dataset)
        except Exception as exc:
            failed.add(dataset)
            err_path = Path(request_item["output_dir"]) / "error.json"
            err_path.parent.mkdir(parents=True, exist_ok=True)
            _write_json(err_path, {"dataset": dataset, "error": str(exc), "run_id": run_id})
            parse_summary = _build_error_parse_summary(
                target=target,
                error=str(exc),
                output_dir=Path(request_item["output_dir"]),
            )
            _replace_parse_summary(parse_summaries, parse_summary)
            _write_json(Path(request_item["output_dir"]) / "parse_summary.json", parse_summary)

        pending = [
            r["dataset"] for r in plan["requests"]
            if r["dataset"] not in completed and r["dataset"] not in failed
        ]
        checkpoint_doc = build_checkpoint(
            run_id=run_id,
            started_at=plan["summary"]["started_at"],
            completed_datasets=sorted(completed),
            failed_datasets=sorted(failed),
            pending_datasets=pending,
            plan_path=str(plan_path),
            parse_summaries=parse_summaries,
        )
        _write_json(checkpoint_path, checkpoint_doc)

        remaining = plan["requests"][idx + 1:]
        if remaining:
            sleeper(random_source.uniform(sleep_min_seconds, sleep_max_seconds))

    summary = dict(plan["summary"])
    summary["network_requests_made"] = True
    summary["completed_datasets"] = sorted(completed)
    summary["failed_datasets"] = sorted(failed)
    summary["pending_datasets"] = [
        r["dataset"] for r in plan["requests"]
        if r["dataset"] not in completed and r["dataset"] not in failed
    ]
    plan["summary"] = summary
    plan["parse_summaries"] = parse_summaries
    _write_json(plan_path, plan)
    report_path.write_text(build_plan_report(plan), encoding="utf-8")

    return {
        "summary": summary,
        "plan": plan,
        "plan_path": plan_path,
        "report_path": report_path,
        "checkpoint_path": checkpoint_path,
        "bronze_records": bronze_records,
        "parse_summaries": parse_summaries,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_inputs(
    *,
    targets: list[DisclosureTarget],
    max_requests: int,
    sleep_min_seconds: float,
    sleep_max_seconds: float,
    execute: bool,
) -> None:
    if not targets:
        raise ValueError("At least one disclosure target is required.")
    if max_requests <= 0:
        raise ValueError("max_requests must be positive.")
    if sleep_min_seconds < MIN_SLEEP_SECONDS or sleep_max_seconds < MIN_SLEEP_SECONDS:
        raise ValueError(f"Sleep values must be at least {MIN_SLEEP_SECONDS}s.")
    if sleep_min_seconds > sleep_max_seconds:
        raise ValueError("sleep_min_seconds must be <= sleep_max_seconds.")
    if execute:
        configured_count = sum(1 for t in targets if t.is_configured)
        if configured_count > max_requests:
            raise ValueError(
                f"execute mode: {configured_count} configured targets exceed max_requests={max_requests}."
            )


def _find_target(targets: list[DisclosureTarget], dataset: str) -> DisclosureTarget | None:
    for t in targets:
        if t.dataset == dataset:
            return t
    return None


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def parse_symbols(value: str) -> list[str]:
    return [s.strip().upper() for s in value.split(",") if s.strip()]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe official disclosure surfaces (HOSE, HNX, company IR) in a controlled way."
    )
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS, help="Comma-separated symbols.")
    parser.add_argument("--max-requests", type=int, default=MAX_REQUESTS_DEFAULT)
    parser.add_argument("--max-records", type=int, default=DEFAULT_MAX_RECORDS_PER_TARGET,
                        help="Max disclosure records to parse per HTML target.")
    parser.add_argument("--sleep-min-seconds", type=float, default=2.0)
    parser.add_argument("--sleep-max-seconds", type=float, default=5.0)
    parser.add_argument("--output-base-dir", default=str(DEFAULT_OUTPUT_BASE))
    parser.add_argument("--bronze-base-dir", default=str(DEFAULT_BRONZE_BASE))
    parser.add_argument("--targets-config", default="", help="Optional JSON file with URL overrides per dataset.")
    parser.add_argument("--execute", action="store_true", help="Opt in to live network calls.")
    parser.add_argument("--force", action="store_true", help="Re-fetch completed checkpoint targets.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    symbols = parse_symbols(args.symbols)
    if not symbols:
        print("No valid symbols supplied.", file=sys.stderr)
        return 2

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    targets = build_default_targets(symbols)

    if args.targets_config:
        config_path = Path(args.targets_config)
        if config_path.exists():
            try:
                config = load_targets_config(config_path)
                targets = apply_targets_config(targets, config)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                return 2
        else:
            print(f"targets_config_missing={config_path}", file=sys.stderr)

    try:
        result = run_disclosure_probe(
            targets=targets,
            max_requests=args.max_requests,
            sleep_min_seconds=args.sleep_min_seconds,
            sleep_max_seconds=args.sleep_max_seconds,
            execute=args.execute,
            force=args.force,
            run_id=run_id,
            output_base=Path(args.output_base_dir),
            bronze_base=Path(args.bronze_base_dir),
            max_records=args.max_records,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"probe_failed={exc}", file=sys.stderr)
        return 1

    summary = result["summary"]
    print(f"run_id={summary['run_id']}")
    print(f"mode={summary['mode']}")
    print(f"total_targets={summary['total_targets']}")
    print(f"configured_targets={summary['configured_targets']}")
    print(f"planned_request_count={summary['planned_request_count']}")
    print(f"network_requests_made={summary['network_requests_made']}")
    print(f"completed_datasets={','.join(summary['completed_datasets'])}")
    print(f"failed_datasets={','.join(summary['failed_datasets'])}")
    print(f"plan={result['plan_path']}")
    print(f"report={result['report_path']}")
    if "bronze_records" in result:
        bronze_count = len(result["bronze_records"])
        print(f"bronze_records_emitted={bronze_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
