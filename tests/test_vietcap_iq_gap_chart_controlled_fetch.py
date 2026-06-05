from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.fetch_vietcap_iq_gap_chart_controlled import (
    HttpResponse,
    make_dataset_name,
    make_request_body,
    run_controlled_fetch,
    validate_inputs,
)


def test_plan_only_writes_plan_and_makes_no_network_call(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def fake_post(url: str, body_json: dict[str, object], headers: dict[str, str]) -> HttpResponse:
        calls.append({"url": url, "body_json": body_json, "headers": headers})
        raise AssertionError("plan-only mode must not call the network")

    result = run_controlled_fetch(
        symbols=["FPT", "VNM"],
        count_back=5000,
        time_frame="ONE_DAY",
        to_epoch_seconds=1780633564,
        to_epoch_source="test",
        output_dir=tmp_path / "out",
        checkpoint_path=tmp_path / "out" / "fetch_checkpoint.json",
        sleep_min_seconds=2.0,
        sleep_max_seconds=5.0,
        max_symbols=3,
        execute=False,
        force=False,
        run_id="test_run",
        http_post=fake_post,
    )

    assert calls == []
    assert result["summary"]["mode"] == "plan_only"
    assert result["summary"]["network_requests_made"] is False
    assert result["plan_path"].exists()
    assert result["report_path"].exists()
    assert "No network requests were made." in result["report_path"].read_text(encoding="utf-8")
    plan = json.loads(result["plan_path"].read_text(encoding="utf-8"))
    assert [item["symbol"] for item in plan["requests"]] == ["FPT", "VNM"]


def test_execute_respects_max_symbols_guardrail(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at most 3 symbols"):
        run_controlled_fetch(
            symbols=["FPT", "VNM", "VCB", "MSN"],
            count_back=5000,
            time_frame="ONE_DAY",
            to_epoch_seconds=1780633564,
            to_epoch_source="test",
            output_dir=tmp_path / "out",
            checkpoint_path=tmp_path / "out" / "fetch_checkpoint.json",
            sleep_min_seconds=2.0,
            sleep_max_seconds=5.0,
            max_symbols=3,
            execute=True,
            force=False,
            run_id="test_run",
        )


def test_checkpoint_skips_completed_symbols(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "out" / "fetch_checkpoint.json"
    checkpoint_path.parent.mkdir(parents=True)
    checkpoint_path.write_text(
        json.dumps(
            {
                "run_id": "old_run",
                "completed_symbols": ["FPT"],
                "failed_symbols": [],
                "pending_symbols": ["VNM"],
            }
        ),
        encoding="utf-8",
    )
    calls: list[dict[str, object]] = []

    def fake_post(url: str, body_json: dict[str, object], headers: dict[str, str]) -> HttpResponse:
        calls.append({"url": url, "body_json": body_json, "headers": headers})
        return HttpResponse(
            status_code=200,
            content_type="application/json",
            body=b'[{"symbol":"VNM","t":[],"o":[],"h":[],"l":[],"c":[]}]',
        )

    result = run_controlled_fetch(
        symbols=["FPT", "VNM"],
        count_back=5000,
        time_frame="ONE_DAY",
        to_epoch_seconds=1780633564,
        to_epoch_source="test",
        output_dir=tmp_path / "out",
        checkpoint_path=checkpoint_path,
        sleep_min_seconds=2.0,
        sleep_max_seconds=5.0,
        max_symbols=3,
        execute=True,
        force=False,
        run_id="test_run",
        http_post=fake_post,
        sleeper=lambda seconds: None,
    )

    assert len(calls) == 1
    assert calls[0]["body_json"]["symbols"] == ["VNM"]
    assert result["summary"]["completed_symbols"] == ["FPT", "VNM"]
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint["completed_symbols"] == ["FPT", "VNM"]
    assert checkpoint["pending_symbols"] == []


def test_dataset_names_are_deterministic() -> None:
    assert make_dataset_name(symbol="fpt", count_back=5000) == "vietcap_iq_gap_chart_fpt_countback_5000"
    assert make_dataset_name(symbol=" VNM ", count_back=2000) == "vietcap_iq_gap_chart_vnm_countback_2000"


def test_request_body_is_correct() -> None:
    assert make_request_body(
        symbol="fpt",
        time_frame="ONE_DAY",
        count_back=5000,
        to_epoch_seconds=1780633564,
    ) == {
        "symbols": ["FPT"],
        "timeFrame": "ONE_DAY",
        "countBack": 5000,
        "to": 1780633564,
    }


def test_sleep_guardrail_rejects_too_small_values() -> None:
    with pytest.raises(ValueError, match="at least 1.0 seconds"):
        validate_inputs(
            symbols=["FPT"],
            count_back=5000,
            to_epoch_seconds=1780633564,
            sleep_min_seconds=0.25,
            sleep_max_seconds=2.0,
            max_symbols=3,
            execute=False,
        )


def test_no_local_config_read_is_needed() -> None:
    script_text = Path("scripts/fetch_vietcap_iq_gap_chart_controlled.py").read_text(encoding="utf-8")
    assert "source_probe_targets.local.json" not in script_text
