from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.ingestion.reviewed_adjusted_price_evidence import (
    run_reviewed_adjusted_price_evidence_intake,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a reviewed adjusted-price evidence package.")
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--symbols", required=True)
    parser.add_argument("--validation-output", default=None)
    parser.add_argument("--factor-output", default=None)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--db-path", default=None)
    args = parser.parse_args()

    result = validate_package(
        package_dir=Path(args.package_dir),
        symbols=_parse_symbols(args.symbols),
        validation_output_path=Path(args.validation_output) if args.validation_output else None,
        factor_output_path=Path(args.factor_output) if args.factor_output else None,
        db_path=Path(args.db_path) if args.db_path else None,
        execute=args.execute,
    )
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "ok" else 1


def validate_package(
    *,
    package_dir: Path,
    symbols: list[str],
    validation_output_path: Path | None = None,
    factor_output_path: Path | None = None,
    db_path: Path | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    manifest_path = package_dir / "manifest.json"
    reasons: list[str] = []
    manifest_result = load_manifest_for_package(package_dir)
    if manifest_result["status"] != "ok":
        return manifest_result
    manifest = manifest_result["manifest"]
    payload_result = resolve_payload_from_manifest(package_dir, manifest)
    if payload_result["status"] != "ok":
        return _summary(
            status="invalid_request",
            package_dir=package_dir,
            manifest_path=manifest_path,
            payload_path=payload_result.get("payload_path"),
            reasons=list(payload_result["reasons"]),
        )
    payload_path = Path(payload_result["payload_path"])
    if execute and db_path is None:
        reasons.append("db_path_required_for_execute")
    if execute and factor_output_path is None:
        reasons.append("factor_output_path_required_for_execute")
    if reasons:
        return _summary(
            status="invalid_request",
            package_dir=package_dir,
            manifest_path=manifest_path,
            payload_path=payload_path,
            reasons=reasons,
        )

    intake = run_reviewed_adjusted_price_evidence_intake(
        manifest_path=manifest_path,
        payload_path=payload_path,
        symbols=symbols,
        validation_output_path=validation_output_path,
        factor_output_path=factor_output_path,
        db_path=db_path,
        dry_run=not execute,
        execute=execute,
    )
    intake["package_dir"] = str(package_dir)
    intake["manifest_path"] = str(manifest_path)
    intake["payload_path"] = str(payload_path)
    return intake


def load_manifest_for_package(package_dir: Path) -> dict[str, Any]:
    manifest_path = package_dir / "manifest.json"
    if not manifest_path.exists():
        return _summary(
            status="missing_manifest",
            package_dir=package_dir,
            manifest_path=manifest_path,
            payload_path=None,
            reasons=["missing_manifest"],
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        return _summary(
            status="invalid_manifest_json",
            package_dir=package_dir,
            manifest_path=manifest_path,
            payload_path=None,
            reasons=[f"invalid_manifest_json:{exc.msg}"],
        )
    if not isinstance(manifest, dict):
        return _summary(
            status="invalid_manifest_json",
            package_dir=package_dir,
            manifest_path=manifest_path,
            payload_path=None,
            reasons=["manifest_must_be_json_object"],
        )
    return {
        "status": "ok",
        "package_dir": str(package_dir),
        "manifest_path": str(manifest_path),
        "manifest": manifest,
        "reasons": [],
    }


def resolve_payload_from_manifest(package_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    raw_path = manifest.get("raw_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return {"status": "invalid_request", "payload_path": None, "reasons": ["manifest_raw_path_missing"]}

    raw_path_obj = Path(raw_path.strip())
    if raw_path_obj.is_absolute():
        return {
            "status": "invalid_request",
            "payload_path": str(raw_path_obj),
            "reasons": ["manifest_raw_path_must_be_package_relative"],
        }

    package_root = package_dir.resolve(strict=False)
    payload_path = (package_root / raw_path_obj).resolve(strict=False)
    try:
        payload_path.relative_to(package_root)
    except ValueError:
        return {
            "status": "invalid_request",
            "payload_path": str(payload_path),
            "reasons": ["manifest_raw_path_outside_package"],
        }

    if payload_path.name not in {"payload.json", "payload.csv"}:
        return {
            "status": "invalid_request",
            "payload_path": str(payload_path),
            "reasons": ["manifest_raw_path_must_reference_payload_json_or_csv"],
        }
    if not payload_path.exists():
        return {"status": "invalid_request", "payload_path": str(payload_path), "reasons": ["missing_payload"]}
    return {"status": "ok", "payload_path": str(payload_path), "reasons": []}


def _summary(
    *,
    status: str,
    package_dir: Path,
    manifest_path: Path,
    payload_path: Path | None,
    reasons: list[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "package_dir": str(package_dir),
        "manifest_path": str(manifest_path),
        "payload_path": str(payload_path) if payload_path else None,
        "reasons": reasons,
        "caveats": [
            "Reviewed local evidence package only; no network request made.",
            "No production DB mutation unless execute is explicitly requested with a local DB path.",
            "Backtrader/VN100 remains blocked until reviewed evidence and adjusted readiness pass.",
        ],
    }


def _parse_symbols(value: str) -> list[str]:
    return [item.strip().upper() for item in str(value or "").split(",") if item.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
