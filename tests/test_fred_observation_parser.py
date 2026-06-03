from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.ingestion.parsers.fred_observation_parser import parse_fred_observations_payload


def test_fred_parser_parses_numeric_values(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(tmp_path)

    result = parse_fred_observations_payload(raw_path, metadata_path)

    assert result.macro_series.loc[0, "series_id"] == "DGS10"
    assert result.macro_series.loc[0, "units"] == "lin"
    assert result.macro_observations.loc[0, "observation_value"] == 4.06
    assert result.macro_observations.loc[0, "quality_status"] == "pass"


def test_dot_value_becomes_null_with_warning(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        observations=[
            {
                "realtime_start": "2026-06-02",
                "realtime_end": "2026-06-02",
                "date": "1962-01-02",
                "value": ".",
            }
        ],
    )

    result = parse_fred_observations_payload(raw_path, metadata_path)
    row = result.macro_observations.iloc[0]

    assert pd.isna(row["observation_value"])
    assert row["quality_status"] == "warn"
    assert "warning_missing_observation_value" in row["quality_reasons"]


def test_fred_parser_parses_iso_dates(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(tmp_path)

    result = parse_fred_observations_payload(raw_path, metadata_path)
    row = result.macro_observations.iloc[0]

    assert row["observation_date"] == "1962-01-02"
    assert row["realtime_start"] == "2026-06-02"
    assert row["realtime_end"] == "2026-06-02"


def test_missing_required_field_fails(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        observations=[
            {
                "realtime_end": "2026-06-02",
                "date": "1962-01-02",
                "value": "4.06",
            }
        ],
    )

    result = parse_fred_observations_payload(raw_path, metadata_path)
    row = result.macro_observations.iloc[0]

    assert row["quality_status"] == "fail"
    assert "missing_required_realtime_start" in row["quality_reasons"]


def test_invalid_numeric_value_fails(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        observations=[
            {
                "realtime_start": "2026-06-02",
                "realtime_end": "2026-06-02",
                "date": "1962-01-02",
                "value": "not-a-number",
            }
        ],
    )

    result = parse_fred_observations_payload(raw_path, metadata_path)

    assert result.macro_observations.loc[0, "quality_status"] == "fail"
    assert "invalid_numeric_observation_value" in result.macro_observations.loc[0, "quality_reasons"]


def test_duplicate_observations_fail(tmp_path: Path) -> None:
    observation = {
        "realtime_start": "2026-06-02",
        "realtime_end": "2026-06-02",
        "date": "1962-01-02",
        "value": "4.06",
    }
    raw_path, metadata_path = _write_fixture(tmp_path, observations=[observation, observation])

    result = parse_fred_observations_payload(raw_path, metadata_path)

    assert set(result.macro_observations["quality_status"]) == {"fail"}
    assert all("exact_duplicate_macro_observation_identity" in value for value in result.macro_observations["quality_reasons"])


def test_deterministic_ids_are_stable(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(tmp_path)

    first = parse_fred_observations_payload(raw_path, metadata_path)
    second = parse_fred_observations_payload(raw_path, metadata_path)

    assert first.macro_observations["macro_observation_id"].tolist() == second.macro_observations["macro_observation_id"].tolist()


def test_series_id_recovers_from_request_params(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(tmp_path, request_params={"series_id": "FEDFUNDS"})

    result = parse_fred_observations_payload(raw_path, metadata_path)

    assert result.macro_series.loc[0, "series_id"] == "FEDFUNDS"
    assert set(result.macro_observations["series_id"]) == {"FEDFUNDS"}


def test_series_id_recovers_from_url_query(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        request_params={},
        endpoint_or_surface="https://api.stlouisfed.org/fred/series/observations?series_id=T10Y2Y&file_type=json&api_key=%3Credacted%3E",
    )

    result = parse_fred_observations_payload(raw_path, metadata_path)

    assert result.macro_series.loc[0, "series_id"] == "T10Y2Y"
    assert set(result.macro_observations["series_id"]) == {"T10Y2Y"}


def _write_fixture(
    tmp_path: Path,
    observations: list[dict[str, object]] | None = None,
    request_params: dict[str, object] | None = None,
    endpoint_or_surface: str = "https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&file_type=json&limit=5&api_key=%3Credacted%3E",
) -> tuple[Path, Path]:
    observations = observations or [
        {
            "realtime_start": "2026-06-02",
            "realtime_end": "2026-06-02",
            "date": "1962-01-02",
            "value": "4.06",
        },
        {
            "realtime_start": "2026-06-02",
            "realtime_end": "2026-06-02",
            "date": "1962-01-03",
            "value": "4.03",
        },
    ]
    payload = {
        "realtime_start": "2026-06-02",
        "realtime_end": "2026-06-02",
        "observation_start": "1600-01-01",
        "observation_end": "9999-12-31",
        "units": "lin",
        "count": 16804,
        "limit": len(observations),
        "observations": observations,
    }
    raw_path = tmp_path / "payload.json"
    raw_path.write_text(json.dumps(payload), encoding="utf-8")
    content_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "source_name": "fred",
                "dataset": "fred_observations",
                "endpoint_or_surface": endpoint_or_surface,
                "request_params": request_params if request_params is not None else {"target_name": "fred_test"},
                "raw_path": str(raw_path),
                "content_hash": content_hash,
                "terms_notes": "synthetic test fixture",
            }
        ),
        encoding="utf-8",
    )
    return raw_path, metadata_path
