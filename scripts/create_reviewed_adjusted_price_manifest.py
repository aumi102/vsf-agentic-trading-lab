from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.ingestion.reviewed_adjusted_price_evidence import (
    ACCEPTED_EVIDENCE_BASIS,
    compute_file_sha256,
)


DEV_ONLY_BASIS = "manual_curated_for_dev_only"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a reviewed adjusted-price evidence manifest.")
    parser.add_argument("--payload", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--reviewed-at", required=True)
    parser.add_argument("--evidence-basis", required=True)
    parser.add_argument("--raw-path", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--not-real-market-data", action="store_true")
    args = parser.parse_args()

    result = create_manifest(
        payload_path=Path(args.payload),
        source_id=args.source_id,
        reviewer=args.reviewer,
        reviewed_at=args.reviewed_at,
        evidence_basis=args.evidence_basis,
        raw_path=args.raw_path,
        output_path=Path(args.output),
        not_real_market_data=args.not_real_market_data,
    )
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "ok" else 1


def create_manifest(
    *,
    payload_path: Path,
    source_id: str,
    reviewer: str,
    reviewed_at: str,
    evidence_basis: str,
    raw_path: str,
    output_path: Path,
    not_real_market_data: bool = False,
) -> dict[str, Any]:
    reasons = _validate_inputs(
        payload_path=payload_path,
        source_id=source_id,
        reviewer=reviewer,
        reviewed_at=reviewed_at,
        evidence_basis=evidence_basis,
        raw_path=raw_path,
        not_real_market_data=not_real_market_data,
    )
    if reasons:
        return _summary(status="invalid_request", output_path=output_path, reasons=reasons)

    payload_sha256 = compute_file_sha256(payload_path)
    manifest: dict[str, Any] = {
        "source_id": source_id.strip(),
        "raw_path": raw_path.strip(),
        "reviewer": reviewer.strip(),
        "reviewed_at": reviewed_at.strip(),
        "evidence_basis": evidence_basis.strip(),
        "payload_sha256": payload_sha256,
    }
    if not_real_market_data:
        manifest["not_real_market_data"] = True

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return _summary(
        status="ok",
        output_path=output_path,
        payload_sha256=payload_sha256,
        reasons=[],
    )


def _validate_inputs(
    *,
    payload_path: Path,
    source_id: str,
    reviewer: str,
    reviewed_at: str,
    evidence_basis: str,
    raw_path: str,
    not_real_market_data: bool,
) -> list[str]:
    reasons: list[str] = []
    if not payload_path.exists():
        reasons.append(f"payload_not_found:{payload_path}")
    if not source_id.strip():
        reasons.append("source_id_required")
    if not reviewer.strip():
        reasons.append("reviewer_required")
    if not raw_path.strip():
        reasons.append("raw_path_required")
    if evidence_basis not in ACCEPTED_EVIDENCE_BASIS:
        reasons.append(f"unsupported_evidence_basis:{evidence_basis}")
    if evidence_basis == DEV_ONLY_BASIS and not not_real_market_data:
        reasons.append("not_real_market_data_required_for_dev_only")
    if not _is_iso_date(reviewed_at):
        reasons.append("reviewed_at_must_be_iso_date")
    return reasons


def _summary(
    *,
    status: str,
    output_path: Path,
    reasons: list[str],
    payload_sha256: str | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "manifest_path": str(output_path),
        "payload_sha256": payload_sha256,
        "reasons": reasons,
        "caveats": [
            "Local reviewed evidence manifest creation only; no network request made.",
            "Do not commit real reviewed evidence payloads or generated reports.",
        ],
    }


def _is_iso_date(value: str) -> bool:
    if len(value) != 10 or value[4] != "-" or value[7] != "-":
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
