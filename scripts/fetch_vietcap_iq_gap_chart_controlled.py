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
SOURCE_NAME = "vietcap_iq"
ENDPOINT = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart"
DEFAULT_OUTPUT_BASE = ROOT / "data/raw/controlled_fetch/source=vietcap_iq"
DEFAULT_SYMBOLS = "FPT,VNM,VCB"
DEFAULT_COUNT_BACK = 5000
DEFAULT_TIME_FRAME = "ONE_DAY"
MIN_EXECUTE_SLEEP_SECONDS = 1.0
TERMS_NOTES = (
    "Controlled Vietcap Trading gap-chart raw fetch skeleton. Use tiny batches first; "
    "no full-universe fetch, DB write, migration, or backtest."
)


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    content_type: str
    body: bytes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan or execute a tiny controlled Vietcap Trading gap-chart raw fetch."
    )
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS, help="Comma-separated symbols. Defaults to FPT,VNM,VCB.")
    parser.add_argument("--count-back", type=int, default=DEFAULT_COUNT_BACK)
    parser.add_argument("--time-frame", default=DEFAULT_TIME_FRAME)
    parser.add_argument(
        "--to",
        type=int,
        default=None,
        help="Optional to epoch seconds. Defaults to current UTC epoch seconds and is recorded in the plan.",
    )
    parser.add_argument("--output-base-dir", default=str(DEFAULT_OUTPUT_BASE))
    parser.add_argument("--checkpoint-path", default="", help="Optional checkpoint JSON path. Defaults inside the run output dir.")
    parser.add_argument("--sleep-min-seconds", type=float, default=2.0)
    parser.add_argument("--sleep-max-seconds", type=float, default=5.0)
    parser.add_argument("--max-symbols", type=int, default=3)
    parser.add_argument("--execute", action="store_true", help="Opt in to live network calls. Omit for plan-only mode.")
    parser.add_argument("--force", action="store_true", help="Re-fetch completed checkpoint symbols when --execute is set.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    to_epoch_seconds = int(args.to) if args.to is not None else int(datetime.now(timezone.utc).timestamp())
    to_epoch_source = "explicit_cli" if args.to is not None else "current_utc_epoch_seconds_default"
    output_dir = Path(args.output_base_dir) / run_id
    checkpoint_path = Path(args.checkpoint_path) if args.checkpoint_path else output_dir / "fetch_checkpoint.json"

    try:
        result = run_controlled_fetch(
            symbols=parse_symbols(args.symbols),
            count_back=args.count_back,
            time_frame=args.time_frame,
            to_epoch_seconds=to_epoch_seconds,
            to_epoch_source=to_epoch_source,
            output_dir=output_dir,
            checkpoint_path=checkpoint_path,
            sleep_min_seconds=args.sleep_min_seconds,
            sleep_max_seconds=args.sleep_max_seconds,
            max_symbols=args.max_symbols,
            execute=args.execute,
            force=args.force,
            run_id=run_id,
        )
    except Exception as exc:
        print(f"vietcap_iq_gap_chart_controlled_fetch_failed={exc}", file=sys.stderr)
        return 1

    summary = result["summary"]
    print(f"run_id={summary['run_id']}")
    print(f"mode={summary['mode']}")
    print(f"network_requests_made={summary['network_requests_made']}")
    print(f"output_dir={summary['output_dir']}")
    print(f"fetch_plan={result['plan_path']}")
    print(f"fetch_plan_report={result['report_path']}")
    print(f"checkpoint_path={summary['checkpoint_path']}")
    print(f"sleep_range_seconds={summary['sleep_min_seconds']}..{summary['sleep_max_seconds']}")
    print(f"symbols={','.join(summary['symbols'])}")
    print(f"planned_request_count={summary['planned_request_count']}")
    print(f"completed_symbols={','.join(summary['completed_symbols'])}")
    print(f"failed_symbols={','.join(summary['failed_symbols'])}")
    print(f"pending_symbols={','.join(summary['pending_symbols'])}")
    return 0


def run_controlled_fetch(
    *,
    symbols: list[str],
    count_back: int,
    time_frame: str,
    to_epoch_seconds: int,
    to_epoch_source: str,
    output_dir: Path,
    checkpoint_path: Path,
    sleep_min_seconds: float,
    sleep_max_seconds: float,
    max_symbols: int,
    execute: bool,
    force: bool,
    run_id: str,
    http_post: Callable[[str, dict[str, Any], dict[str, str]], HttpResponse] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    validate_inputs(
        symbols=symbols,
        count_back=count_back,
        to_epoch_seconds=to_epoch_seconds,
        sleep_min_seconds=sleep_min_seconds,
        sleep_max_seconds=sleep_max_seconds,
        max_symbols=max_symbols,
        execute=execute,
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    plan = build_fetch_plan(
        symbols=symbols,
        count_back=count_back,
        time_frame=time_frame,
        to_epoch_seconds=to_epoch_seconds,
        to_epoch_source=to_epoch_source,
        output_dir=output_dir,
        checkpoint_path=checkpoint_path,
        sleep_min_seconds=sleep_min_seconds,
        sleep_max_seconds=sleep_max_seconds,
        execute=execute,
        force=force,
        run_id=run_id,
    )
    plan_path = output_dir / "fetch_plan.json"
    report_path = output_dir / "fetch_plan_report.md"
    write_json(plan_path, plan)
    report_path.write_text(build_plan_report(plan), encoding="utf-8")

    if not execute:
        return {
            "summary": plan["summary"],
            "plan": plan,
            "plan_path": plan_path,
            "report_path": report_path,
            "checkpoint_path": checkpoint_path,
        }

    checkpoint = load_checkpoint(checkpoint_path)
    if checkpoint and not force:
        completed = set(str(symbol).upper() for symbol in checkpoint.get("completed_symbols", []))
        failed = set(str(symbol).upper() for symbol in checkpoint.get("failed_symbols", []))
    else:
        completed = set()
        failed = set()

    pending = [item["symbol"] for item in plan["requests"] if item["symbol"] not in completed]
    checkpoint_doc = build_checkpoint(
        run_id=run_id,
        started_at=plan["summary"]["started_at"],
        completed_symbols=sorted(completed),
        failed_symbols=sorted(failed),
        pending_symbols=pending,
        request_params=plan["request_params"],
        output_paths=plan["output_paths"],
    )
    write_json(checkpoint_path, checkpoint_doc)

    post = http_post or post_json
    random_source = rng or random.Random()
    completed_symbols = set(completed)
    failed_symbols = set(failed)

    for request_index, request_plan in enumerate(plan["requests"]):
        symbol = request_plan["symbol"]
        if symbol in completed_symbols and not force:
            continue

        try:
            response = post(ENDPOINT, request_plan["body_json"], request_plan["headers"])
            write_symbol_output(
                output_dir=output_dir,
                symbol=symbol,
                dataset=request_plan["dataset"],
                body_json=request_plan["body_json"],
                response=response,
                run_id=run_id,
            )
            if classify_access_status(response) == "verified":
                completed_symbols.add(symbol)
                failed_symbols.discard(symbol)
            else:
                failed_symbols.add(symbol)
        except Exception as exc:  # pragma: no cover - defensive live-fetch isolation
            failed_symbols.add(symbol)
            write_error_metadata(
                output_dir=output_dir,
                symbol=symbol,
                dataset=request_plan["dataset"],
                body_json=request_plan["body_json"],
                run_id=run_id,
                error=str(exc),
            )

        pending_symbols = [
            item["symbol"]
            for item in plan["requests"]
            if item["symbol"] not in completed_symbols and item["symbol"] not in failed_symbols
        ]
        checkpoint_doc = build_checkpoint(
            run_id=run_id,
            started_at=plan["summary"]["started_at"],
            completed_symbols=sorted(completed_symbols),
            failed_symbols=sorted(failed_symbols),
            pending_symbols=pending_symbols,
            request_params=plan["request_params"],
            output_paths=plan["output_paths"],
        )
        write_json(checkpoint_path, checkpoint_doc)

        remaining = [
            item["symbol"]
            for item in plan["requests"][request_index + 1 :]
            if item["symbol"] not in completed_symbols
        ]
        if remaining:
            sleeper(random_source.uniform(sleep_min_seconds, sleep_max_seconds))

    summary = dict(plan["summary"])
    summary["network_requests_made"] = True
    summary["completed_symbols"] = sorted(completed_symbols)
    summary["failed_symbols"] = sorted(failed_symbols)
    summary["pending_symbols"] = [
        item["symbol"]
        for item in plan["requests"]
        if item["symbol"] not in completed_symbols and item["symbol"] not in failed_symbols
    ]
    plan["summary"] = summary
    write_json(plan_path, plan)
    report_path.write_text(build_plan_report(plan), encoding="utf-8")

    return {
        "summary": summary,
        "plan": plan,
        "plan_path": plan_path,
        "report_path": report_path,
        "checkpoint_path": checkpoint_path,
    }


def parse_symbols(value: str) -> list[str]:
    symbols = [_normalize_symbol(item) for item in str(value).split(",") if item.strip()]
    return [symbol for symbol in symbols if symbol]


def build_fetch_plan(
    *,
    symbols: list[str],
    count_back: int,
    time_frame: str,
    to_epoch_seconds: int,
    to_epoch_source: str,
    output_dir: Path,
    checkpoint_path: Path,
    sleep_min_seconds: float,
    sleep_max_seconds: float,
    execute: bool,
    force: bool,
    run_id: str,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    requests = []
    for index, symbol in enumerate(symbols, start=1):
        dataset = make_dataset_name(symbol=symbol, count_back=count_back)
        body_json = make_request_body(
            symbol=symbol,
            time_frame=time_frame,
            count_back=count_back,
            to_epoch_seconds=to_epoch_seconds,
        )
        requests.append(
            {
                "planned_order": index,
                "symbol": symbol,
                "dataset": dataset,
                "method": "POST",
                "endpoint": ENDPOINT,
                "body_json": body_json,
                "headers": make_headers(symbol),
                "output_dir": str(output_dir / dataset),
            }
        )

    request_params = {
        "endpoint": ENDPOINT,
        "method": "POST",
        "countBack": count_back,
        "timeFrame": time_frame,
        "to": to_epoch_seconds,
        "to_epoch_source": to_epoch_source,
        "symbols": symbols,
        "sequential_only": True,
        "concurrency": 1,
    }
    output_paths = {
        "output_dir": str(output_dir),
        "checkpoint_path": str(checkpoint_path),
        "fetch_plan": str(output_dir / "fetch_plan.json"),
        "fetch_plan_report": str(output_dir / "fetch_plan_report.md"),
    }
    summary = {
        "run_id": run_id,
        "started_at": started_at,
        "mode": "execute" if execute else "plan_only",
        "network_requests_made": False,
        "output_dir": str(output_dir),
        "checkpoint_path": str(checkpoint_path),
        "symbols": symbols,
        "planned_request_count": len(requests),
        "sleep_min_seconds": sleep_min_seconds,
        "sleep_max_seconds": sleep_max_seconds,
        "force": force,
        "completed_symbols": [],
        "failed_symbols": [],
        "pending_symbols": symbols,
        "guardrails": [
            "No network requests are made unless --execute is supplied.",
            "Symbols are processed sequentially with concurrency=1.",
            "Random sleep is applied only between execute-mode symbol requests.",
            "No local source-probe target config file is read.",
            "Raw payloads and metadata are saved before any parsing.",
            "No database, migration, backtest, or full-universe fetch is performed.",
        ],
    }
    return {
        "summary": summary,
        "request_params": request_params,
        "output_paths": output_paths,
        "requests": requests,
    }


def validate_inputs(
    *,
    symbols: list[str],
    count_back: int,
    to_epoch_seconds: int,
    sleep_min_seconds: float,
    sleep_max_seconds: float,
    max_symbols: int,
    execute: bool,
) -> None:
    if not symbols:
        raise ValueError("At least one symbol is required.")
    if count_back <= 0:
        raise ValueError("count_back must be positive.")
    if to_epoch_seconds <= 0:
        raise ValueError("to epoch seconds must be positive.")
    if max_symbols <= 0:
        raise ValueError("max_symbols must be positive.")
    if sleep_min_seconds < MIN_EXECUTE_SLEEP_SECONDS or sleep_max_seconds < MIN_EXECUTE_SLEEP_SECONDS:
        raise ValueError(f"sleep values must be at least {MIN_EXECUTE_SLEEP_SECONDS} seconds.")
    if sleep_min_seconds > sleep_max_seconds:
        raise ValueError("sleep_min_seconds must be less than or equal to sleep_max_seconds.")
    if execute and len(symbols) > max_symbols:
        raise ValueError(f"execute mode supports at most {max_symbols} symbols in this controlled skeleton.")


def make_dataset_name(*, symbol: str, count_back: int) -> str:
    return f"vietcap_iq_gap_chart_{_normalize_symbol(symbol).lower()}_countback_{int(count_back)}"


def make_request_body(*, symbol: str, time_frame: str, count_back: int, to_epoch_seconds: int) -> dict[str, Any]:
    return {
        "symbols": [_normalize_symbol(symbol)],
        "timeFrame": str(time_frame),
        "countBack": int(count_back),
        "to": int(to_epoch_seconds),
    }


def make_headers(symbol: str) -> dict[str, str]:
    normalized = _normalize_symbol(symbol)
    return {
        "Accept": "application/json",
        "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
        "Content-Type": "application/json",
        "Origin": "https://trading.vietcap.com.vn",
        "Referer": f"https://trading.vietcap.com.vn/iq/company?ticker={normalized}&tab=overview&isIndex=false",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36 vsf-controlled-fetch/0.1",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }


def post_json(url: str, body_json: dict[str, Any], headers: dict[str, str]) -> HttpResponse:
    body_bytes = json.dumps(body_json, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body_bytes, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=20) as response:
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


def write_symbol_output(
    *,
    output_dir: Path,
    symbol: str,
    dataset: str,
    body_json: dict[str, Any],
    response: HttpResponse,
    run_id: str,
) -> None:
    dataset_dir = output_dir / dataset
    dataset_dir.mkdir(parents=True, exist_ok=True)
    payload_path = dataset_dir / "payload.json"
    payload_text, parsed_json = _payload_text(response.body)
    payload_path.write_text(payload_text, encoding="utf-8")
    content_hash = hashlib.sha256(payload_path.read_bytes()).hexdigest()
    metadata = {
        "source_name": SOURCE_NAME,
        "adapter_name": "controlled_gap_chart_fetcher",
        "dataset": dataset,
        "symbol": _normalize_symbol(symbol),
        "endpoint_or_surface": ENDPOINT,
        "request_params": {
            "method": "POST",
            "body_json": body_json,
            "header_names": sorted(make_headers(symbol).keys()),
        },
        "request_body": body_json,
        "run_id": run_id,
        "access_status": classify_access_status(response),
        "auth_mode": "browser_like_headers_no_secrets",
        "http_status": response.status_code,
        "content_type": response.content_type,
        "content_hash": content_hash,
        "byte_size": len(response.body),
        "raw_path": str(payload_path),
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "status": "success" if classify_access_status(response) == "verified" else classify_access_status(response),
        "row_count": len(parsed_json) if isinstance(parsed_json, list) else 1 if parsed_json is not None else 0,
        "terms_notes": TERMS_NOTES,
    }
    write_json(dataset_dir / "metadata.json", metadata)


def write_error_metadata(
    *,
    output_dir: Path,
    symbol: str,
    dataset: str,
    body_json: dict[str, Any],
    run_id: str,
    error: str,
) -> None:
    dataset_dir = output_dir / dataset
    dataset_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "source_name": SOURCE_NAME,
        "adapter_name": "controlled_gap_chart_fetcher",
        "dataset": dataset,
        "symbol": _normalize_symbol(symbol),
        "endpoint_or_surface": ENDPOINT,
        "request_params": {"method": "POST", "body_json": body_json},
        "request_body": body_json,
        "run_id": run_id,
        "access_status": "error",
        "auth_mode": "browser_like_headers_no_secrets",
        "http_status": None,
        "content_type": "",
        "content_hash": "",
        "byte_size": 0,
        "raw_path": "",
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "status": "error",
        "error": error,
        "terms_notes": TERMS_NOTES,
    }
    write_json(dataset_dir / "metadata.json", metadata)


def classify_access_status(response: HttpResponse) -> str:
    if response.status_code in {401, 403}:
        return "auth_required"
    if response.status_code < 200 or response.status_code >= 300:
        return "error"
    try:
        json.loads(response.body.decode("utf-8-sig"))
    except json.JSONDecodeError:
        return "rejected_response"
    return "verified"


def build_checkpoint(
    *,
    run_id: str,
    started_at: str,
    completed_symbols: list[str],
    failed_symbols: list[str],
    pending_symbols: list[str],
    request_params: dict[str, Any],
    output_paths: dict[str, str],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "started_at": started_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "completed_symbols": completed_symbols,
        "failed_symbols": failed_symbols,
        "pending_symbols": pending_symbols,
        "request_params": request_params,
        "output_paths": output_paths,
    }


def build_plan_report(plan: dict[str, Any]) -> str:
    summary = plan["summary"]
    lines = [
        "# Vietcap IQ Gap-Chart Controlled Fetch Plan",
        "",
        f"- run_id: `{summary['run_id']}`",
        f"- mode: `{summary['mode']}`",
        f"- network_requests_made: `{summary['network_requests_made']}`",
        f"- output_dir: `{summary['output_dir']}`",
        f"- checkpoint_path: `{summary['checkpoint_path']}`",
        f"- sleep range seconds: `{summary['sleep_min_seconds']} - {summary['sleep_max_seconds']}`",
        f"- force: `{summary['force']}`",
        "",
        "## Planned Requests",
        "",
        "| Order | Symbol | Dataset | countBack | to |",
        "|---:|---|---|---:|---:|",
    ]
    for item in plan["requests"]:
        body = item["body_json"]
        lines.append(
            f"| {item['planned_order']} | `{item['symbol']}` | `{item['dataset']}` | "
            f"{body['countBack']} | {body['to']} |"
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
        ]
    )
    for guardrail in summary["guardrails"]:
        lines.append(f"- {guardrail}")
    if summary["mode"] == "plan_only":
        lines.extend(["", "No network requests were made."])
    return "\n".join(lines) + "\n"


def load_checkpoint(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _payload_text(body: bytes) -> tuple[str, Any | None]:
    text = body.decode("utf-8-sig", errors="replace")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text, None
    return json.dumps(parsed, indent=2, ensure_ascii=False), parsed


def _normalize_symbol(value: object) -> str:
    return str(value or "").strip().upper()


if __name__ == "__main__":
    raise SystemExit(main())
