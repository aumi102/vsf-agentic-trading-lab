from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from trading_agent.source_adapters.base import SourceFetchResult


PARSER_VERSION = "source_probe_parser_v1"
SCHEMA_VERSION = "source_probe_schema_v1"
SECRET_HINTS = ("token", "secret", "password", "key", "authorization")
SAFE_METADATA_KEYS = {
    "auth_env",
    "auth_in",
    "auth_param",
    "body_json_keys",
    "body_json_sensitive_keys_redacted",
    "body_present",
    "body_size_bytes",
    "config_file",
    "header_names",
    "method",
    "response_validation",
    "target_name",
    "verify_ssl",
}


class RawProbeStore:
    def __init__(self, base_dir: str | Path = "data/raw/source_probe") -> None:
        self.base_dir = Path(base_dir)

    def write_payload(
        self,
        *,
        source_name: str,
        adapter_name: str,
        dataset: str,
        endpoint_or_surface: str,
        payload: Any,
        request_params: dict[str, Any],
        symbol: str,
        start: str,
        end: str,
        run_id: str,
        access_status: str,
        auth_mode: str,
        http_status: int | None,
        content_type: str,
        status: str,
        terms_notes: str,
        error: str | None = None,
    ) -> SourceFetchResult:
        dataset_dir = self.base_dir / f"source={_safe_name(source_name)}" / f"run_id={_safe_name(run_id)}" / _safe_name(dataset)
        dataset_dir.mkdir(parents=True, exist_ok=True)

        ext, bytes_payload, original_columns, row_count = _serialize_payload(payload, content_type)
        raw_path = dataset_dir / f"payload.{ext}"
        raw_path.write_bytes(bytes_payload)
        content_hash = hashlib.sha256(bytes_payload).hexdigest()

        metadata = {
            "source_name": source_name,
            "adapter_name": adapter_name,
            "dataset": dataset,
            "endpoint_or_surface": endpoint_or_surface,
            "request_params": _scrub_secrets(request_params),
            "symbol": symbol,
            "start": start,
            "end": end,
            "crawled_at": datetime.now(timezone.utc).isoformat(),
            "access_status": access_status,
            "auth_mode": auth_mode,
            "http_status": http_status,
            "content_type": content_type,
            "original_columns": original_columns,
            "row_count": row_count,
            "content_hash": content_hash,
            "raw_path": str(raw_path),
            "parser_version": PARSER_VERSION,
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "error": error,
            "terms_notes": terms_notes,
        }
        metadata_path = dataset_dir / "metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        return SourceFetchResult(
            dataset=dataset,
            status=status,
            payload=payload,
            raw_path=str(raw_path),
            metadata_path=str(metadata_path),
            original_fields=original_columns,
            row_count=row_count,
            error=error,
        )


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.=-]+", "_", value.strip()) or "unknown"


def _scrub_secrets(params: dict[str, Any]) -> dict[str, Any]:
    scrubbed: dict[str, Any] = {}
    for key, value in params.items():
        if key in SAFE_METADATA_KEYS:
            scrubbed[key] = value
        elif any(hint in key.lower() for hint in SECRET_HINTS):
            scrubbed[key] = "<redacted>"
        else:
            scrubbed[key] = value
    return scrubbed


def _serialize_payload(payload: Any, content_type: str) -> tuple[str, bytes, list[str], int]:
    if isinstance(payload, pd.DataFrame):
        text = payload.to_csv(index=False)
        return "csv", text.encode("utf-8"), [str(col) for col in payload.columns], len(payload)
    if isinstance(payload, (dict, list)):
        original_columns = _fields_from_json(payload)
        row_count = len(payload) if isinstance(payload, list) else 1
        text = json.dumps(payload, indent=2, ensure_ascii=False)
        return "json", text.encode("utf-8"), original_columns, row_count
    if isinstance(payload, bytes):
        lower_content_type = content_type.lower()
        ext = "html" if "html" in lower_content_type else "json" if "json" in lower_content_type else "txt"
        original_columns, row_count = _inspect_bytes(payload, ext)
        return ext, payload, original_columns, row_count
    text = str(payload)
    lower = text.lstrip().lower()
    ext = "html" if lower.startswith("<!doctype") or lower.startswith("<html") else "txt"
    return ext, text.encode("utf-8"), [], 1 if text else 0


def _fields_from_json(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        return [str(key) for key in payload.keys()]
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        fields: set[str] = set()
        for row in payload[:25]:
            fields.update(str(key) for key in row.keys())
        return sorted(fields)
    return []


def _inspect_bytes(payload: bytes, ext: str) -> tuple[list[str], int]:
    text = payload.decode("utf-8", errors="replace")
    if ext == "json":
        try:
            parsed = json.loads(text)
            return _fields_from_json(parsed), len(parsed) if isinstance(parsed, list) else 1
        except json.JSONDecodeError:
            return [], 0
    first_line = text.splitlines()[0] if text.splitlines() else ""
    if ext == "txt" and "," in first_line:
        reader = csv.reader(text.splitlines())
        rows = list(reader)
        return rows[0] if rows else [], max(len(rows) - 1, 0)
    return [], 1 if text else 0
