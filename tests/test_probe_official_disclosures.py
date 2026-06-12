from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.probe_official_disclosures import (
    HttpResponse,
    apply_targets_config,
    build_default_targets,
    build_fetch_plan,
    build_plan_report,
    capture_raw_evidence,
    classify_access_status,
    load_checkpoint,
    parse_symbols,
    parse_to_bronze_record,
    run_disclosure_probe,
)
from trading_agent.source_adapters.disclosure_adapter import (
    DisclosureTarget,
    DisclosurePitStatus,
    DisclosureQualityStatus,
    assign_pit_status,
    check_disclosure_quality,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok_response(body: bytes = b'{"title": "FPT Q1 2026 FS", "date": "2026-04-24"}') -> HttpResponse:
    return HttpResponse(
        status_code=200,
        content_type="application/json",
        body=body,
        response_headers={"content-type": "application/json"},
    )


def _blocked_response() -> HttpResponse:
    return HttpResponse(
        status_code=403,
        content_type="text/html",
        body=b"<html>Forbidden</html>",
        response_headers={"content-type": "text/html"},
    )


def _configured_target(symbol: str = "FPT", dataset: str = "test_fpt") -> DisclosureTarget:
    return DisclosureTarget(
        source_family="company_ir",
        exchange="HOSE",
        official_domain="fpt.com",
        adapter_name="company_ir_fpt_v1",
        dataset=dataset,
        symbol=symbol,
        url="https://example.com/ir",
    )


# ---------------------------------------------------------------------------
# disclosure_adapter: assign_pit_status
# ---------------------------------------------------------------------------

def test_assign_pit_status_canonical_timestamp_available() -> None:
    status = assign_pit_status(
        published_at="2026-04-24T09:00:00+07:00",
        published_date="2026-04-24",
        access_status="verified",
    )
    assert status == DisclosurePitStatus.CANONICAL_TIMESTAMP_AVAILABLE.value


def test_assign_pit_status_date_only_available() -> None:
    status = assign_pit_status(
        published_at="",
        published_date="2026-04-24",
        access_status="verified",
    )
    assert status == DisclosurePitStatus.DATE_ONLY_AVAILABLE.value


def test_assign_pit_status_official_timestamp_missing() -> None:
    status = assign_pit_status(
        published_at="",
        published_date="",
        access_status="verified",
    )
    assert status == DisclosurePitStatus.OFFICIAL_TIMESTAMP_MISSING.value


def test_assign_pit_status_blocked_for_blocked_access() -> None:
    assert assign_pit_status(published_at="", published_date="", access_status="blocked") == DisclosurePitStatus.BLOCKED.value


def test_assign_pit_status_blocked_for_auth_required() -> None:
    assert assign_pit_status(published_at="2026-01-01", published_date="2026-01-01", access_status="auth_required") == DisclosurePitStatus.BLOCKED.value


def test_assign_pit_status_blocked_for_not_configured() -> None:
    assert assign_pit_status(published_at="", published_date="", access_status="not_configured") == DisclosurePitStatus.BLOCKED.value


def test_assign_pit_status_blocked_for_error() -> None:
    assert assign_pit_status(published_at="", published_date="", access_status="error") == DisclosurePitStatus.BLOCKED.value


# ---------------------------------------------------------------------------
# disclosure_adapter: check_disclosure_quality
# ---------------------------------------------------------------------------

def _complete_record() -> dict:
    return {
        "source_family": "hose",
        "exchange": "HOSE",
        "disclosure_id": "hose_FPT_test_abc123",
        "crawled_at": "2026-06-12T10:00:00+00:00",
        "schema_version": "official_disclosure_bronze_v1",
        "parser_version": "official_disclosure_parser_v1",
        "published_date": "2026-04-24",
        "published_at": "2026-04-24T09:00:00+07:00",
        "title": "FPT Q1 2026 FS",
        "symbol": "FPT",
    }


def test_check_quality_pass_for_complete_record() -> None:
    status, warnings, errors = check_disclosure_quality(_complete_record())
    assert status == DisclosureQualityStatus.PASS.value
    assert warnings == []
    assert errors == []


def test_check_quality_warn_for_missing_dates() -> None:
    rec = _complete_record()
    rec["published_date"] = ""
    rec["published_at"] = ""
    status, warnings, errors = check_disclosure_quality(rec)
    assert status == DisclosureQualityStatus.WARN.value
    assert "publication_date_unknown" in warnings
    assert errors == []


def test_check_quality_warn_for_missing_title() -> None:
    rec = _complete_record()
    rec["title"] = ""
    status, warnings, errors = check_disclosure_quality(rec)
    assert status == DisclosureQualityStatus.WARN.value
    assert "title_missing" in warnings


def test_check_quality_fail_for_missing_required_field() -> None:
    rec = _complete_record()
    del rec["disclosure_id"]
    status, warnings, errors = check_disclosure_quality(rec)
    assert status == DisclosureQualityStatus.FAIL.value
    assert any("disclosure_id" in e for e in errors)


def test_check_quality_fail_takes_priority_over_warn() -> None:
    rec = _complete_record()
    del rec["crawled_at"]
    rec["published_date"] = ""
    rec["published_at"] = ""
    status, warnings, errors = check_disclosure_quality(rec)
    assert status == DisclosureQualityStatus.FAIL.value
    assert errors


# ---------------------------------------------------------------------------
# disclosure_adapter: DisclosureTarget
# ---------------------------------------------------------------------------

def test_disclosure_target_is_configured_true() -> None:
    t = _configured_target()
    assert t.is_configured is True


def test_disclosure_target_is_configured_false() -> None:
    t = DisclosureTarget(
        source_family="hose", exchange="HOSE", official_domain="www.hsx.vn",
        adapter_name="a", dataset="d", url="",
    )
    assert t.is_configured is False


def test_disclosure_target_is_configured_whitespace_only() -> None:
    t = DisclosureTarget(
        source_family="hose", exchange="HOSE", official_domain="www.hsx.vn",
        adapter_name="a", dataset="d", url="   ",
    )
    assert t.is_configured is False


# ---------------------------------------------------------------------------
# build_default_targets / parse_symbols
# ---------------------------------------------------------------------------

def test_build_default_targets_contains_hose_and_hnx_per_symbol() -> None:
    targets = build_default_targets(["FPT", "VCI"])
    families = {t.source_family for t in targets}
    assert "hose" in families
    assert "hnx" in families


def test_build_default_targets_includes_company_ir_for_fpt() -> None:
    targets = build_default_targets(["FPT"])
    company_ir_targets = [t for t in targets if t.source_family == "company_ir" and t.symbol == "FPT"]
    assert len(company_ir_targets) >= 1


def test_build_default_targets_all_not_configured_by_default() -> None:
    targets = build_default_targets(["FPT"])
    assert all(not t.is_configured for t in targets)


def test_parse_symbols_normalizes_and_strips() -> None:
    assert parse_symbols("fpt , vci, VNM") == ["FPT", "VCI", "VNM"]


def test_parse_symbols_empty_string_returns_empty() -> None:
    assert parse_symbols("") == []


# ---------------------------------------------------------------------------
# Plan mode
# ---------------------------------------------------------------------------

def test_plan_mode_no_network_calls(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_get(url: str, headers: dict) -> HttpResponse:
        calls.append(url)
        raise AssertionError("plan mode must not call the network")

    targets = [_configured_target()]
    result = run_disclosure_probe(
        targets=targets,
        max_requests=5,
        sleep_min_seconds=2.0,
        sleep_max_seconds=5.0,
        execute=False,
        force=False,
        run_id="test_run",
        output_base=tmp_path / "raw",
        bronze_base=tmp_path / "bronze",
        http_get=fake_get,
    )

    assert calls == []
    assert result["summary"]["mode"] == "plan_only"
    assert result["summary"]["network_requests_made"] is False


def test_plan_writes_plan_json(tmp_path: Path) -> None:
    targets = [_configured_target()]
    result = run_disclosure_probe(
        targets=targets,
        max_requests=5,
        sleep_min_seconds=2.0,
        sleep_max_seconds=5.0,
        execute=False,
        force=False,
        run_id="test_plan_json",
        output_base=tmp_path / "raw",
        bronze_base=tmp_path / "bronze",
    )
    assert result["plan_path"].exists()
    plan = json.loads(result["plan_path"].read_text(encoding="utf-8"))
    assert plan["summary"]["run_id"] == "test_plan_json"


def test_plan_writes_plan_report(tmp_path: Path) -> None:
    targets = [_configured_target()]
    result = run_disclosure_probe(
        targets=targets,
        max_requests=5,
        sleep_min_seconds=2.0,
        sleep_max_seconds=5.0,
        execute=False,
        force=False,
        run_id="test_plan_report",
        output_base=tmp_path / "raw",
        bronze_base=tmp_path / "bronze",
    )
    assert result["report_path"].exists()
    report_text = result["report_path"].read_text(encoding="utf-8")
    assert "Official Disclosure Probe Plan" in report_text


def test_plan_report_contains_guardrails(tmp_path: Path) -> None:
    targets = [_configured_target()]
    result = run_disclosure_probe(
        targets=targets,
        max_requests=5,
        sleep_min_seconds=2.0,
        sleep_max_seconds=5.0,
        execute=False,
        force=False,
        run_id="test_guardrails",
        output_base=tmp_path / "raw",
        bronze_base=tmp_path / "bronze",
    )
    report_text = result["report_path"].read_text(encoding="utf-8")
    assert "Guardrails" in report_text
    assert "No network requests" in report_text


def test_plan_skips_not_configured_targets_in_requests(tmp_path: Path) -> None:
    not_configured = DisclosureTarget(
        source_family="hose", exchange="HOSE", official_domain="www.hsx.vn",
        adapter_name="a", dataset="skipped_target", url="",
    )
    targets = [_configured_target(dataset="real_target"), not_configured]
    result = run_disclosure_probe(
        targets=targets,
        max_requests=5,
        sleep_min_seconds=2.0,
        sleep_max_seconds=5.0,
        execute=False,
        force=False,
        run_id="test_skip",
        output_base=tmp_path / "raw",
        bronze_base=tmp_path / "bronze",
    )
    plan = result["plan"]
    request_datasets = {r["dataset"] for r in plan["requests"]}
    assert "real_target" in request_datasets
    assert "skipped_target" not in request_datasets
    skipped_datasets = {s["dataset"] for s in plan["skipped"]}
    assert "skipped_target" in skipped_datasets


def test_plan_enforces_max_requests(tmp_path: Path) -> None:
    targets = [_configured_target(dataset=f"ds_{i}") for i in range(5)]
    result = run_disclosure_probe(
        targets=targets,
        max_requests=2,
        sleep_min_seconds=2.0,
        sleep_max_seconds=5.0,
        execute=False,
        force=False,
        run_id="test_max",
        output_base=tmp_path / "raw",
        bronze_base=tmp_path / "bronze",
    )
    assert len(result["plan"]["requests"]) == 2


# ---------------------------------------------------------------------------
# Execute mode
# ---------------------------------------------------------------------------

def test_execute_mode_calls_http(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_get(url: str, headers: dict) -> HttpResponse:
        calls.append(url)
        return _ok_response()

    targets = [_configured_target()]
    run_disclosure_probe(
        targets=targets,
        max_requests=5,
        sleep_min_seconds=2.0,
        sleep_max_seconds=5.0,
        execute=True,
        force=False,
        run_id="test_execute",
        output_base=tmp_path / "raw",
        bronze_base=tmp_path / "bronze",
        http_get=fake_get,
        sleeper=lambda _: None,
    )

    assert len(calls) == 1
    assert calls[0] == "https://example.com/ir"


def test_execute_mode_writes_raw_evidence(tmp_path: Path) -> None:
    def fake_get(url: str, headers: dict) -> HttpResponse:
        return _ok_response()

    targets = [_configured_target(dataset="test_raw")]
    result = run_disclosure_probe(
        targets=targets,
        max_requests=5,
        sleep_min_seconds=2.0,
        sleep_max_seconds=5.0,
        execute=True,
        force=False,
        run_id="test_raw_ev",
        output_base=tmp_path / "raw",
        bronze_base=tmp_path / "bronze",
        http_get=fake_get,
        sleeper=lambda _: None,
    )

    plan = result["plan"]
    evidence_dir = Path(plan["requests"][0]["output_dir"])
    assert (evidence_dir / "metadata.json").exists()
    assert any(evidence_dir.glob("payload.*"))


def test_execute_mode_captures_sha256_in_metadata(tmp_path: Path) -> None:
    body = b'{"title": "FPT test"}'

    def fake_get(url: str, headers: dict) -> HttpResponse:
        return HttpResponse(status_code=200, content_type="application/json", body=body, response_headers={})

    targets = [_configured_target(dataset="sha_test")]
    result = run_disclosure_probe(
        targets=targets,
        max_requests=5,
        sleep_min_seconds=2.0,
        sleep_max_seconds=5.0,
        execute=True,
        force=False,
        run_id="test_sha",
        output_base=tmp_path / "raw",
        bronze_base=tmp_path / "bronze",
        http_get=fake_get,
        sleeper=lambda _: None,
    )

    evidence_dir = Path(result["plan"]["requests"][0]["output_dir"])
    metadata = json.loads((evidence_dir / "metadata.json").read_text(encoding="utf-8"))
    import hashlib
    assert metadata["body_sha256"] == hashlib.sha256(body).hexdigest()


def test_execute_mode_writes_bronze_record(tmp_path: Path) -> None:
    def fake_get(url: str, headers: dict) -> HttpResponse:
        return _ok_response()

    targets = [_configured_target(dataset="bronze_test")]
    result = run_disclosure_probe(
        targets=targets,
        max_requests=5,
        sleep_min_seconds=2.0,
        sleep_max_seconds=5.0,
        execute=True,
        force=False,
        run_id="test_bronze",
        output_base=tmp_path / "raw",
        bronze_base=tmp_path / "bronze",
        http_get=fake_get,
        sleeper=lambda _: None,
    )

    bronze_dir = Path(result["plan"]["requests"][0]["bronze_dir"])
    assert (bronze_dir / "disclosure_record.json").exists()
    record = json.loads((bronze_dir / "disclosure_record.json").read_text(encoding="utf-8"))
    assert record["source_family"] == "company_ir"
    assert record["schema_version"] == "official_disclosure_bronze_v1"


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------

def test_checkpoint_written_on_execute(tmp_path: Path) -> None:
    def fake_get(url: str, headers: dict) -> HttpResponse:
        return _ok_response()

    targets = [_configured_target(dataset="ckpt_test")]
    result = run_disclosure_probe(
        targets=targets,
        max_requests=5,
        sleep_min_seconds=2.0,
        sleep_max_seconds=5.0,
        execute=True,
        force=False,
        run_id="test_ckpt",
        output_base=tmp_path / "raw",
        bronze_base=tmp_path / "bronze",
        http_get=fake_get,
        sleeper=lambda _: None,
    )

    checkpoint = load_checkpoint(result["checkpoint_path"])
    assert checkpoint is not None
    assert checkpoint["run_id"] == "test_ckpt"
    assert "ckpt_test" in checkpoint["completed_datasets"]


def test_checkpoint_resume_skips_completed(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_get(url: str, headers: dict) -> HttpResponse:
        calls.append(url)
        return _ok_response()

    target = _configured_target(dataset="resume_test")
    checkpoint_path = tmp_path / "raw" / "test_resume" / "checkpoint.json"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(
        json.dumps({
            "run_id": "old",
            "started_at": "2026-01-01",
            "completed_datasets": ["resume_test"],
            "failed_datasets": [],
            "pending_datasets": [],
            "plan_path": "",
        }),
        encoding="utf-8",
    )

    result = run_disclosure_probe(
        targets=[target],
        max_requests=5,
        sleep_min_seconds=2.0,
        sleep_max_seconds=5.0,
        execute=True,
        force=False,
        run_id="test_resume",
        output_base=tmp_path / "raw",
        bronze_base=tmp_path / "bronze",
        http_get=fake_get,
        sleeper=lambda _: None,
    )

    assert len(calls) == 0
    assert "resume_test" in result["summary"]["completed_datasets"]


def test_checkpoint_force_reruns_completed(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_get(url: str, headers: dict) -> HttpResponse:
        calls.append(url)
        return _ok_response()

    target = _configured_target(dataset="force_test")
    checkpoint_path = tmp_path / "raw" / "test_force" / "checkpoint.json"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(
        json.dumps({
            "run_id": "old",
            "started_at": "2026-01-01",
            "completed_datasets": ["force_test"],
            "failed_datasets": [],
            "pending_datasets": [],
            "plan_path": "",
        }),
        encoding="utf-8",
    )

    run_disclosure_probe(
        targets=[target],
        max_requests=5,
        sleep_min_seconds=2.0,
        sleep_max_seconds=5.0,
        execute=True,
        force=True,
        run_id="test_force",
        output_base=tmp_path / "raw",
        bronze_base=tmp_path / "bronze",
        http_get=fake_get,
        sleeper=lambda _: None,
    )

    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Bronze parsing
# ---------------------------------------------------------------------------

def test_blocked_response_sets_pit_blocked_in_bronze(tmp_path: Path) -> None:
    target = _configured_target(dataset="blocked_test")
    payload_path = tmp_path / "payload.html"
    payload_path.write_bytes(b"<html>Forbidden</html>")
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text("{}", encoding="utf-8")

    record = parse_to_bronze_record(
        response=_blocked_response(),
        target=target,
        payload_path=payload_path,
        metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )

    assert record.pit_status == DisclosurePitStatus.BLOCKED.value
    assert record.quality_status == DisclosureQualityStatus.FAIL.value


def test_verified_json_response_parses_title_into_bronze(tmp_path: Path) -> None:
    body = b'{"title": "FPT Q1 2026 Financials", "date": "2026-04-24"}'
    response = HttpResponse(
        status_code=200, content_type="application/json",
        body=body, response_headers={},
    )
    target = _configured_target(dataset="json_parse_test")
    payload_path = tmp_path / "payload.json"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text("{}", encoding="utf-8")

    record = parse_to_bronze_record(
        response=response,
        target=target,
        payload_path=payload_path,
        metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )

    assert record.title == "FPT Q1 2026 Financials"
    assert record.published_date == "2026-04-24"
    assert record.pit_status == DisclosurePitStatus.DATE_ONLY_AVAILABLE.value


def test_verified_json_with_published_at_gets_canonical_pit(tmp_path: Path) -> None:
    body = b'{"publishedAt": "2026-04-24T09:00:00+07:00", "date": "2026-04-24"}'
    response = HttpResponse(
        status_code=200, content_type="application/json",
        body=body, response_headers={},
    )
    target = _configured_target(dataset="pit_ts_test")
    payload_path = tmp_path / "payload.json"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text("{}", encoding="utf-8")

    record = parse_to_bronze_record(
        response=response,
        target=target,
        payload_path=payload_path,
        metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )

    assert record.pit_status == DisclosurePitStatus.CANONICAL_TIMESTAMP_AVAILABLE.value


# ---------------------------------------------------------------------------
# classify_access_status
# ---------------------------------------------------------------------------

def test_classify_access_status_verified_on_200() -> None:
    assert classify_access_status(HttpResponse(200, "application/json", b"{}", {})) == "verified"


def test_classify_access_status_auth_required_on_403() -> None:
    assert classify_access_status(HttpResponse(403, "text/html", b"", {})) == "auth_required"


def test_classify_access_status_auth_required_on_401() -> None:
    assert classify_access_status(HttpResponse(401, "text/html", b"", {})) == "auth_required"


def test_classify_access_status_error_on_500() -> None:
    assert classify_access_status(HttpResponse(500, "text/html", b"", {})) == "error"


# ---------------------------------------------------------------------------
# apply_targets_config
# ---------------------------------------------------------------------------

def test_apply_targets_config_sets_url_on_matching_dataset() -> None:
    targets = [_configured_target(dataset="hose_disclosures_fpt")]
    config = {
        "targets": [
            {"dataset": "hose_disclosures_fpt", "url": "https://www.hsx.vn/api/disclosures?ticker=FPT"}
        ]
    }
    updated = apply_targets_config(targets, config)
    assert updated[0].url == "https://www.hsx.vn/api/disclosures?ticker=FPT"


def test_apply_targets_config_leaves_unmatched_unchanged() -> None:
    targets = [_configured_target(dataset="other_dataset")]
    config = {"targets": [{"dataset": "different_dataset", "url": "https://example.com"}]}
    updated = apply_targets_config(targets, config)
    assert updated[0].url == "https://example.com/ir"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_validate_inputs_raises_on_zero_max_requests(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_requests must be positive"):
        run_disclosure_probe(
            targets=[_configured_target()],
            max_requests=0,
            sleep_min_seconds=2.0,
            sleep_max_seconds=5.0,
            execute=False,
            force=False,
            run_id="test",
            output_base=tmp_path / "raw",
            bronze_base=tmp_path / "bronze",
        )


def test_validate_inputs_raises_on_sleep_below_minimum(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Sleep values"):
        run_disclosure_probe(
            targets=[_configured_target()],
            max_requests=5,
            sleep_min_seconds=0.5,
            sleep_max_seconds=5.0,
            execute=False,
            force=False,
            run_id="test",
            output_base=tmp_path / "raw",
            bronze_base=tmp_path / "bronze",
        )


def test_validate_inputs_raises_on_empty_targets(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="At least one"):
        run_disclosure_probe(
            targets=[],
            max_requests=5,
            sleep_min_seconds=2.0,
            sleep_max_seconds=5.0,
            execute=False,
            force=False,
            run_id="test",
            output_base=tmp_path / "raw",
            bronze_base=tmp_path / "bronze",
        )
