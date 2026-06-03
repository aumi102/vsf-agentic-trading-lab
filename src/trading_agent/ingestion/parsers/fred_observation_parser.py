from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pandas as pd


SOURCE_NAME = "fred"
SCHEMA_VERSION = "fred_observations_dry_run_v1"
PARSER_VERSION = "fred_observation_parser_v1"

REQUIRED_OBSERVATION_COLUMNS = ["series_id", "observation_date", "realtime_start", "realtime_end"]


@dataclass(frozen=True)
class FredParseResult:
    macro_series: pd.DataFrame
    macro_observations: pd.DataFrame
    validation_summary: dict[str, Any]


def parse_fred_observations_payload(raw_path: str | Path, metadata_path: str | Path) -> FredParseResult:
    raw_path = Path(raw_path)
    metadata_path = Path(metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    raw_text = raw_path.read_text(encoding="utf-8")
    raw_content_hash = metadata.get("content_hash") or hashlib.sha256(raw_path.read_bytes()).hexdigest()
    source_payload_id = f"{SOURCE_NAME}:{str(raw_content_hash)[:16]}"

    payload = json.loads(raw_text)
    observations = payload.get("observations")
    if not isinstance(observations, list):
        raise ValueError("FRED observations payload must contain an observations list.")

    series_id = _extract_series_id(payload=payload, metadata=metadata)
    series = _build_macro_series(
        payload=payload,
        metadata=metadata,
        series_id=series_id,
        raw_content_hash=raw_content_hash,
        source_payload_id=source_payload_id,
    )
    rows = _normalize_observations(
        observations=observations,
        series_id=series_id,
        raw_content_hash=raw_content_hash,
        source_payload_id=source_payload_id,
    )
    validated = _validate_observations(rows)
    summary = _build_validation_summary(
        raw_path=raw_path,
        metadata_path=metadata_path,
        metadata=metadata,
        payload=payload,
        observations=validated,
        series=series,
        raw_content_hash=raw_content_hash,
    )
    return FredParseResult(macro_series=series, macro_observations=validated, validation_summary=summary)


def _build_macro_series(
    *,
    payload: dict[str, Any],
    metadata: dict[str, Any],
    series_id: str | None,
    raw_content_hash: str,
    source_payload_id: str,
) -> pd.DataFrame:
    row = {
        "series_id": series_id,
        "source_name": SOURCE_NAME,
        "units": _clean_text(payload.get("units")),
        "observation_start": _parse_iso_date(payload.get("observation_start")),
        "observation_end": _parse_iso_date(payload.get("observation_end")),
        "count": _clean_integer(payload.get("count")),
        "limit": _clean_integer(payload.get("limit")),
        "source_payload_id": source_payload_id,
        "raw_content_hash": raw_content_hash,
        "parser_version": PARSER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "terms_notes": metadata.get("terms_notes", ""),
    }
    return pd.DataFrame([row])


def _normalize_observations(
    *,
    observations: list[Any],
    series_id: str | None,
    raw_content_hash: str,
    source_payload_id: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for index, observation in enumerate(observations):
        if not isinstance(observation, dict):
            observation = {}
        value, value_reason = _parse_observation_value(observation.get("value"))
        row = {
            "macro_observation_id": _make_observation_id(series_id, observation, source_payload_id, index),
            "series_id": series_id,
            "source_name": SOURCE_NAME,
            "observation_date": _parse_iso_date(observation.get("date")),
            "observation_value": value,
            "realtime_start": _parse_iso_date(observation.get("realtime_start")),
            "realtime_end": _parse_iso_date(observation.get("realtime_end")),
            "source_payload_id": source_payload_id,
            "raw_content_hash": raw_content_hash,
            "raw_row_index": index,
            "parser_version": PARSER_VERSION,
            "schema_version": SCHEMA_VERSION,
            "_value_quality_reason": value_reason,
        }
        rows.append(row)
    return pd.DataFrame(rows)


def _validate_observations(df: pd.DataFrame) -> pd.DataFrame:
    rows = df.copy()
    if rows.empty:
        rows["quality_status"] = []
        rows["quality_reasons"] = []
        return _observation_output_columns(rows)

    exact_duplicate_mask = rows.duplicated(
        subset=["series_id", "observation_date", "realtime_start", "realtime_end", "observation_value"],
        keep=False,
    )
    statuses: list[str] = []
    reasons_all: list[str] = []

    for index, row in rows.iterrows():
        fail_reasons: list[str] = []
        warn_reasons: list[str] = []

        for column in REQUIRED_OBSERVATION_COLUMNS:
            if not _has_value(row[column]):
                fail_reasons.append(f"missing_required_{column}")

        value_reason = row.get("_value_quality_reason")
        if value_reason == "warning_missing_observation_value":
            warn_reasons.append(value_reason)
        elif value_reason == "invalid_numeric_observation_value":
            fail_reasons.append(value_reason)

        if bool(exact_duplicate_mask.loc[index]):
            fail_reasons.append("exact_duplicate_macro_observation_identity")

        if fail_reasons:
            statuses.append("fail")
        elif warn_reasons:
            statuses.append("warn")
        else:
            statuses.append("pass")
        reasons_all.append(";".join(sorted(set(fail_reasons + warn_reasons))))

    rows["quality_status"] = statuses
    rows["quality_reasons"] = reasons_all
    return _observation_output_columns(rows)


def _observation_output_columns(rows: pd.DataFrame) -> pd.DataFrame:
    return rows[
        [
            "macro_observation_id",
            "series_id",
            "source_name",
            "observation_date",
            "observation_value",
            "realtime_start",
            "realtime_end",
            "source_payload_id",
            "raw_content_hash",
            "raw_row_index",
            "parser_version",
            "schema_version",
            "quality_status",
            "quality_reasons",
        ]
    ]


def _build_validation_summary(
    *,
    raw_path: Path,
    metadata_path: Path,
    metadata: dict[str, Any],
    payload: dict[str, Any],
    observations: pd.DataFrame,
    series: pd.DataFrame,
    raw_content_hash: str,
) -> dict[str, Any]:
    fail_count = int((observations["quality_status"] == "fail").sum()) if not observations.empty else 0
    warn_count = int((observations["quality_status"] == "warn").sum()) if not observations.empty else 0
    pass_count = int((observations["quality_status"] == "pass").sum()) if not observations.empty else 0
    exact_duplicate_count = int(
        observations.duplicated(
            subset=["series_id", "observation_date", "realtime_start", "realtime_end", "observation_value"],
            keep=False,
        ).sum()
    ) if not observations.empty else 0

    reason_counts: dict[str, int] = {}
    warning_reason_counts: dict[str, int] = {}
    failure_reason_counts: dict[str, int] = {}
    if not observations.empty:
        for value in observations["quality_reasons"].dropna():
            for reason in str(value).split(";"):
                if reason:
                    reason_counts[reason] = reason_counts.get(reason, 0) + 1
                    if reason.startswith("warning_"):
                        warning_reason_counts[reason] = warning_reason_counts.get(reason, 0) + 1
                    else:
                        failure_reason_counts[reason] = failure_reason_counts.get(reason, 0) + 1

    return {
        "source_name": SOURCE_NAME,
        "dataset": metadata.get("dataset", "fred_observations"),
        "series_id": series.loc[0, "series_id"] if not series.empty else None,
        "raw_path": str(raw_path),
        "metadata_path": str(metadata_path),
        "raw_content_hash": raw_content_hash,
        "parser_version": PARSER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "json_observation_count": len(payload.get("observations", [])) if isinstance(payload.get("observations"), list) else None,
        "macro_series_count": int(len(series)),
        "macro_observation_count": int(len(observations)),
        "quality_pass_count": pass_count,
        "quality_warn_count": warn_count,
        "quality_fail_count": fail_count,
        "exact_duplicate_macro_observation_count": exact_duplicate_count,
        "row_count_matches_json_observations": int(len(observations)) == len(payload.get("observations", [])),
        "quality_reason_counts": reason_counts,
        "quality_warning_reason_counts": warning_reason_counts,
        "quality_failure_reason_counts": failure_reason_counts,
        "terms_notes": metadata.get("terms_notes", ""),
    }


def _extract_series_id(*, payload: dict[str, Any], metadata: dict[str, Any]) -> str | None:
    request_params = metadata.get("request_params")
    if isinstance(request_params, dict):
        for key in ("series_id", "series", "fred_series_id"):
            value = request_params.get(key)
            if _has_value(value):
                return str(value).strip()

    endpoint = metadata.get("endpoint_or_surface") or metadata.get("url") or ""
    if endpoint:
        query = parse_qs(urlparse(str(endpoint)).query)
        for key in ("series_id", "series"):
            values = query.get(key)
            if values and _has_value(values[0]):
                return str(values[0]).strip()

    for key in ("series_id", "series"):
        value = payload.get(key)
        if _has_value(value):
            return str(value).strip()
    return None


def _parse_observation_value(value: Any) -> tuple[float | None, str]:
    if value is None:
        return None, "warning_missing_observation_value"
    if isinstance(value, str):
        text = value.strip()
        if text in {"", "."}:
            return None, "warning_missing_observation_value"
        try:
            return float(text), ""
        except ValueError:
            return None, "invalid_numeric_observation_value"
    try:
        if pd.isna(value):
            return None, "warning_missing_observation_value"
    except TypeError:
        pass
    try:
        return float(value), ""
    except (TypeError, ValueError):
        return None, "invalid_numeric_observation_value"


def _parse_iso_date(value: Any) -> str | None:
    if not _has_value(value):
        return None
    text = str(value).strip()
    try:
        return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _clean_text(value: Any) -> str | None:
    if not _has_value(value):
        return None
    return str(value).strip()


def _clean_integer(value: Any) -> int | None:
    if not _has_value(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except TypeError:
        pass
    return str(value).strip() != ""


def _make_observation_id(series_id: str | None, observation: dict[str, Any], source_payload_id: str, raw_row_index: int) -> str:
    parts = [
        SOURCE_NAME,
        str(series_id or ""),
        str(observation.get("date") or ""),
        str(observation.get("realtime_start") or ""),
        source_payload_id,
        str(raw_row_index),
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{SOURCE_NAME}:observation:{digest}"
