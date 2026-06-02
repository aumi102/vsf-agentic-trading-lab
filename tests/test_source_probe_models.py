from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.source_adapters.base import AccessStatus, SourceProbeResult
from trading_agent.source_adapters.raw_store import RawProbeStore


def test_source_probe_result_serializes_to_dict() -> None:
    result = SourceProbeResult(
        source_name="hose",
        adapter_name="HoseAdapter",
        access_status=AccessStatus.NOT_CONFIGURED,
        auth_status="missing_config",
        endpoint_or_surface="HOSE_PROBE_URL not configured",
        datasets=["official_public_surface"],
        likely_canonical_tables=["daily_prices"],
    )

    data = result.as_dict()

    assert data["access_status"] == "not_configured"
    assert data["source_name"] == "hose"
    assert data["likely_canonical_tables"] == ["daily_prices"]


def test_raw_store_writes_metadata_without_secrets(tmp_path: Path) -> None:
    store = RawProbeStore(tmp_path)

    fetch = store.write_payload(
        source_name="test_source",
        adapter_name="TestAdapter",
        dataset="sample",
        endpoint_or_surface="https://example.test/api",
        payload=pd.DataFrame({"symbol": ["FPT"], "close": [100.0]}),
        request_params={"symbol": "FPT", "token": "secret-token", "api_key": "secret-key"},
        symbol="FPT",
        start="2024-01-01",
        end="2024-01-02",
        run_id="run1",
        access_status="verified",
        auth_mode="token_configured",
        http_status=200,
        content_type="text/csv",
        status="success",
        terms_notes="test terms",
    )

    metadata = json.loads(Path(fetch.metadata_path).read_text(encoding="utf-8"))
    assert Path(fetch.raw_path).exists()
    assert metadata["request_params"]["token"] == "<redacted>"
    assert metadata["request_params"]["api_key"] == "<redacted>"
    assert metadata["original_columns"] == ["symbol", "close"]
    assert metadata["row_count"] == 1
