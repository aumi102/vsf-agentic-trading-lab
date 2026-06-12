"""Controlled probe for official disclosure surfaces (HOSE, HNX, company IR).

Plan mode (default) builds a fetch plan without making network calls.
Execute mode (--execute) fetches configured targets sequentially with rate limiting.
Force mode (--execute --force) re-fetches already completed targets.

Targets without a configured URL are listed in the plan as NOT_CONFIGURED and are
skipped during execute. Supply real URLs via --targets-config JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
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
DEFAULT_SYMBOLS = "FPT,VCI"
DEFAULT_OUTPUT_BASE = ROOT / "data/raw/official_disclosures"
DEFAULT_BRONZE_BASE = ROOT / "data/bronze/official_disclosures"

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


# ---------------------------------------------------------------------------
# HTTP primitives
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    content_type: str
    body: bytes
    response_headers: dict[str, str]


def get_url(url: str, headers: dict[str, str], *, timeout: int = 20) -> HttpResponse:
    request = Request(url, headers=headers, method="GET")
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
            terms_notes="HOSE official disclosure page. Requires targets-config URL.",
        ))
        targets.append(DisclosureTarget(
            source_family="hnx",
            exchange="HNX",
            official_domain="www.hnx.vn",
            adapter_name="hnx_disclosure_adapter_v1",
            dataset=f"hnx_disclosures_{sym.lower()}",
            symbol=sym,
            url="",
            terms_notes="HNX official disclosure page. Requires targets-config URL.",
        ))
    targets.append(DisclosureTarget(
        source_family="company_ir",
        exchange="HOSE",
        official_domain="fpt.com",
        adapter_name="company_ir_fpt_v1",
        dataset="company_ir_fpt_disclosures",
        symbol="FPT",
        url="",
        terms_notes=(
            "FPT company IR page (positive control). "
            "Supply URL via targets-config to enable. "
            "Manual confirm: fpt.com/en/ir/information-disclosures."
        ),
    ))
    targets.append(DisclosureTarget(
        source_family="company_ir",
        exchange="HOSE",
        official_domain="vietcapital.com.vn",
        adapter_name="company_ir_vci_v1",
        dataset="company_ir_vci_disclosures",
        symbol="VCI",
        url="",
        terms_notes=(
            "VCI company IR (unresolved target). Vietcap IR page returned login portal "
            "in prior probe. Supply URL via targets-config if accessible."
        ),
    ))
    return targets


def apply_targets_config(
    targets: list[DisclosureTarget],
    config: dict[str, Any],
) -> list[DisclosureTarget]:
    """Overlay URL / headers from external config onto matching targets by dataset."""
    overrides: dict[str, dict[str, Any]] = {}
    for entry in config.get("targets", []):
        dataset = entry.get("dataset", "")
        if dataset:
            overrides[dataset] = entry
    result: list[DisclosureTarget] = []
    for t in targets:
        ov = overrides.get(t.dataset, {})
        if ov:
            import dataclasses
            updates = {
                k: ov[k]
                for k in ("url", "method", "headers", "request_params", "terms_notes")
                if k in ov
            }
            t = dataclasses.replace(t, **updates)
        result.append(t)
    return result


def load_targets_config(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid targets config JSON at {path}: {exc}") from exc


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
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "started_at": started_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "completed_datasets": completed_datasets,
        "failed_datasets": failed_datasets,
        "pending_datasets": pending_datasets,
        "plan_path": plan_path,
    }


def load_checkpoint(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


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
# Bronze parsing
# ---------------------------------------------------------------------------

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


def write_bronze_record(record: DisclosureRecord, bronze_dir: Path) -> Path:
    bronze_dir.mkdir(parents=True, exist_ok=True)
    out_path = bronze_dir / "disclosure_record.json"
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

    get = http_get or get_url
    random_source = rng or random.Random()

    checkpoint_doc = build_checkpoint(
        run_id=run_id,
        started_at=plan["summary"]["started_at"],
        completed_datasets=sorted(completed),
        failed_datasets=sorted(failed),
        pending_datasets=[r["dataset"] for r in plan["requests"] if r["dataset"] not in completed],
        plan_path=str(plan_path),
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
            response = get(target.url, target.headers)
            evidence_dir = Path(request_item["output_dir"])
            payload_path, metadata_path = capture_raw_evidence(
                output_dir=evidence_dir,
                target=target,
                response=response,
                run_id=run_id,
            )
            bronze_dir = Path(request_item["bronze_dir"])
            record = parse_to_bronze_record(
                response=response,
                target=target,
                payload_path=payload_path,
                metadata_path=metadata_path,
                crawled_at=crawled_at,
            )
            bronze_path = write_bronze_record(record, bronze_dir)
            bronze_records.append({"dataset": dataset, "bronze_path": str(bronze_path), "record": record.as_dict()})

            if classify_access_status(response) == "verified":
                completed.add(dataset)
                failed.discard(dataset)
            else:
                failed.add(dataset)
        except Exception as exc:
            failed.add(dataset)
            err_path = Path(request_item["output_dir"]) / "error.json"
            err_path.parent.mkdir(parents=True, exist_ok=True)
            _write_json(err_path, {"dataset": dataset, "error": str(exc), "run_id": run_id})

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
        )
        _write_json(checkpoint_path, checkpoint_doc)

        remaining = plan["requests"][idx + 1 :]
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
    _write_json(plan_path, plan)
    report_path.write_text(build_plan_report(plan), encoding="utf-8")

    return {
        "summary": summary,
        "plan": plan,
        "plan_path": plan_path,
        "report_path": report_path,
        "checkpoint_path": checkpoint_path,
        "bronze_records": bronze_records,
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
