from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.probe_official_disclosures import (
    HttpResponse,
    _DEFAULT_REQUEST_HEADERS,
    _normalize_fpt_url,
    _normalize_fpt_url_with_warning,
    _normalize_vci_url,
    _normalize_vci_url_with_warning,
    _parse_fpt_date,
    _parse_vci_date,
    _infer_fpt_doc_category,
    _infer_vci_doc_category,
    apply_targets_config,
    build_default_targets,
    build_fetch_plan,
    build_plan_report,
    capture_raw_evidence,
    classify_access_status,
    extract_disclosure_records,
    load_checkpoint,
    parse_fpt_ir_html_records,
    parse_vci_ir_detail_records,
    parse_symbols,
    parse_to_bronze_record,
    run_disclosure_probe,
    validate_targets_config,
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
    targets = [
        DisclosureTarget(
            source_family="hose",
            exchange="HOSE",
            official_domain="www.hsx.vn",
            adapter_name="hose_disclosure_adapter_v1",
            dataset="hose_disclosures_fpt",
            symbol="FPT",
            url="",
        )
    ]
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


def _official_config_entry(**overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "dataset": "company_ir_fpt_disclosures",
        "url": "https://fpt.com/en/ir/information-disclosures",
        "official_domain": "fpt.com",
    }
    entry.update(overrides)
    return entry


@pytest.mark.parametrize("key", ["ssl_verify", "verify", "insecure"])
def test_targets_config_rejects_tls_bypass_keys(key: str) -> None:
    config = {"targets": [_official_config_entry(**{key: False})]}
    with pytest.raises(ValueError, match="Forbidden config key"):
        validate_targets_config(config)


@pytest.mark.parametrize("header", ["Cookie", "Authorization", "Proxy-Authorization"])
def test_targets_config_rejects_auth_headers(header: str) -> None:
    config = {"targets": [_official_config_entry(headers={header: "secret"})]}
    with pytest.raises(ValueError, match="Forbidden config key|Forbidden header"):
        validate_targets_config(config)


@pytest.mark.parametrize("key", ["token", "api_key", "password", "client_secret", "session"])
def test_targets_config_rejects_secret_like_keys_recursively(key: str) -> None:
    config = {"targets": [_official_config_entry(request_params={"nested": {key: "x"}})]}
    with pytest.raises(ValueError, match="Secret-like config key"):
        validate_targets_config(config)


@pytest.mark.parametrize(
    "user_agent",
    [
        "Mozilla/5.0",
        "Chrome/125",
        "Chromium/125",
        "Safari/537.36",
        "Firefox/125",
        "Edge/125",
        "Edg/125",
    ],
)
def test_targets_config_rejects_browser_impersonation_user_agent(user_agent: str) -> None:
    config = {"targets": [_official_config_entry(headers={"User-Agent": user_agent})]}
    with pytest.raises(ValueError, match="Browser impersonation User-Agent"):
        validate_targets_config(config)


def test_targets_config_allows_exact_project_user_agent() -> None:
    config = {
        "targets": [
            _official_config_entry(headers={"User-Agent": _DEFAULT_REQUEST_HEADERS["User-Agent"]})
        ]
    }
    validate_targets_config(config)


def test_targets_config_rejects_unapproved_header() -> None:
    config = {"targets": [_official_config_entry(headers={"Referer": "https://fpt.com"})]}
    with pytest.raises(ValueError, match="Forbidden header"):
        validate_targets_config(config)


def test_targets_config_rejects_non_https_url() -> None:
    config = {"targets": [_official_config_entry(url="http://fpt.com/en/ir")]}
    with pytest.raises(ValueError, match="must use https"):
        validate_targets_config(config)


def test_targets_config_rejects_url_host_mismatch() -> None:
    config = {
        "targets": [
            _official_config_entry(url="https://evil.example/en/ir", official_domain="fpt.com")
        ]
    }
    with pytest.raises(ValueError, match="must match official_domain"):
        validate_targets_config(config)


def test_apply_targets_config_rejects_url_host_mismatch_against_default_domain() -> None:
    targets = build_default_targets(["FPT"])
    config = {
        "targets": [
            {"dataset": "company_ir_fpt_disclosures", "url": "https://evil.example/en/ir"}
        ]
    }
    with pytest.raises(ValueError, match="must match official_domain"):
        apply_targets_config(targets, config)


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


# ---------------------------------------------------------------------------
# FPT IR HTML fixtures and helpers
# ---------------------------------------------------------------------------

def _fpt_ir_html(items: list[tuple[str, str, str]]) -> bytes:
    """Build a minimal FPT IR HTML page fixture.

    Each item is (href, title, date_str) where date_str uses M/D/YYYY format.
    Mirrors the actual Sitecore CMS structure from fpt.com/en/ir/information-disclosures.
    """
    blocks = ""
    for href, title, date_str in items:
        blocks += f"""
        <div class="media-download-section-key-information-content">
            <a class="media-download-section-key-information-content-subtitle" href="{href}" target="_blank">
                {title}
            </a>
            <div class="media-download-section-key-information-description-icon">
                <div class="media-download-section-key-information-description-date">
                    Updated: {date_str}
                </div>
            </div>
        </div>
        """
    return f"<html><body>{blocks}</body></html>".encode("utf-8")


def _fpt_target() -> DisclosureTarget:
    return DisclosureTarget(
        source_family="company_ir",
        exchange="HOSE",
        official_domain="fpt.com",
        adapter_name="company_ir_fpt_v1",
        dataset="company_ir_fpt_disclosures",
        symbol="FPT",
        url="https://fpt.com/en/ir/information-disclosures",
    )


def _fpt_html_response(items: list[tuple[str, str, str]]) -> HttpResponse:
    body = _fpt_ir_html(items)
    return HttpResponse(
        status_code=200,
        content_type="text/html; charset=utf-8",
        body=body,
        response_headers={"content-type": "text/html; charset=utf-8"},
    )


# ---------------------------------------------------------------------------
# parse_fpt_ir_html_records
# ---------------------------------------------------------------------------

def test_parse_fpt_html_extracts_title(tmp_path: Path) -> None:
    body = _fpt_ir_html([
        ("/-/media/fpt/q1-2026-fs.pdf", "FPT Q1 2026 Financial Statements", "4/24/2026"),
    ])
    payload_path = tmp_path / "payload.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_fpt_ir_html_records(
        body=body, target=_fpt_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00", max_records=5,
    )

    assert len(records) == 1
    assert records[0].title == "FPT Q1 2026 Financial Statements"


def test_parse_fpt_html_extracts_date_as_iso(tmp_path: Path) -> None:
    body = _fpt_ir_html([("/-/media/fpt/test.pdf", "Test Doc", "4/24/2026")])
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_fpt_ir_html_records(
        body=body, target=_fpt_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )

    assert records[0].published_date == "2026-04-24"


def test_parse_fpt_html_resolves_relative_url(tmp_path: Path) -> None:
    href = "/-/media/project/fpt/q1-2026-consolidated-fs.pdf"
    body = _fpt_ir_html([(href, "Title", "4/24/2026")])
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_fpt_ir_html_records(
        body=body, target=_fpt_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )

    assert records[0].document_url == f"https://fpt.com{href}"


def test_parse_fpt_html_disclosure_id_deterministic(tmp_path: Path) -> None:
    href = "/-/media/fpt/same-doc.pdf"
    body = _fpt_ir_html([(href, "Title", "4/24/2026")])
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    r1 = parse_fpt_ir_html_records(
        body=body, target=_fpt_target(), payload_path=payload_path,
        metadata_path=metadata_path, crawled_at="2026-06-12T10:00:00+00:00",
    )
    r2 = parse_fpt_ir_html_records(
        body=body, target=_fpt_target(), payload_path=payload_path,
        metadata_path=metadata_path, crawled_at="2026-06-12T11:00:00+00:00",
    )

    assert r1[0].disclosure_id == r2[0].disclosure_id


def test_parse_fpt_html_max_records_limit(tmp_path: Path) -> None:
    items = [(f"/-/media/fpt/doc{i}.pdf", f"Doc {i}", "4/24/2026") for i in range(10)]
    body = _fpt_ir_html(items)
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_fpt_ir_html_records(
        body=body, target=_fpt_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00", max_records=3,
    )

    assert len(records) == 3


def test_parse_fpt_html_no_regex_match_returns_empty_list(tmp_path: Path) -> None:
    # HTML with disclosure block structure but missing date — regex won't match
    body = (
        b'<html><body>'
        b'<div class="media-download-section-key-information-content">'
        b'<a class="media-download-section-key-information-content-subtitle" href="/-/media/fpt/nodoc.pdf" target="_blank">'
        b'Title with no date</a>'
        b'</div></body></html>'
    )
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_fpt_ir_html_records(
        body=body, target=_fpt_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )

    assert records == []


def test_parse_fpt_html_no_items_returns_empty_list(tmp_path: Path) -> None:
    body = b"<html><body><p>No disclosure content</p></body></html>"
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_fpt_ir_html_records(
        body=body, target=_fpt_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )

    assert records == []


def test_parse_fpt_html_entity_decoded_in_title(tmp_path: Path) -> None:
    body = _fpt_ir_html([
        ("/-/media/fpt/t.pdf", "BOD&#39;s Resolution &amp; Notes", "4/24/2026"),
    ])
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_fpt_ir_html_records(
        body=body, target=_fpt_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )

    assert records[0].title == "BOD's Resolution & Notes"


def test_parse_fpt_html_pdf_attachment_type(tmp_path: Path) -> None:
    body = _fpt_ir_html([("/-/media/fpt/doc.pdf", "PDF Doc", "4/24/2026")])
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_fpt_ir_html_records(
        body=body, target=_fpt_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )

    assert records[0].attachment_type == "pdf"
    assert records[0].attachment_name == "doc.pdf"


def test_parse_fpt_html_pit_status_date_only_available(tmp_path: Path) -> None:
    body = _fpt_ir_html([("/-/media/fpt/doc.pdf", "Title", "4/24/2026")])
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_fpt_ir_html_records(
        body=body, target=_fpt_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )

    assert records[0].pit_status == DisclosurePitStatus.DATE_ONLY_AVAILABLE.value


def test_parse_fpt_html_quality_pass_for_complete_record(tmp_path: Path) -> None:
    body = _fpt_ir_html([("/-/media/fpt/q1.pdf", "FPT Q1 2026 Financial Statements", "4/24/2026")])
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_fpt_ir_html_records(
        body=body, target=_fpt_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )

    assert records[0].quality_status == DisclosureQualityStatus.PASS.value
    assert records[0].error_codes == []


# ---------------------------------------------------------------------------
# extract_disclosure_records dispatch
# ---------------------------------------------------------------------------

def test_extract_disclosure_records_routes_fpt_html_domain(tmp_path: Path) -> None:
    body = _fpt_ir_html([("/-/media/fpt/q1.pdf", "Q1 FS", "4/24/2026")])
    response = HttpResponse(status_code=200, content_type="text/html; charset=utf-8", body=body, response_headers={})
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = extract_disclosure_records(
        response=response, target=_fpt_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00", max_records=5,
    )

    assert len(records) == 1
    assert records[0].document_url.startswith("https://fpt.com/")


def test_extract_disclosure_records_falls_back_for_json_on_fpt_domain(tmp_path: Path) -> None:
    body = b'{"title": "FPT JSON", "date": "2026-04-24"}'
    response = HttpResponse(status_code=200, content_type="application/json", body=body, response_headers={})
    payload_path = tmp_path / "p.json"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = extract_disclosure_records(
        response=response, target=_fpt_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )

    assert len(records) == 1
    assert records[0].title == "FPT JSON"


# ---------------------------------------------------------------------------
# classify_access_status: js_app_shell detection
# ---------------------------------------------------------------------------

def test_classify_access_status_js_shell_hose_body() -> None:
    hose_shell = (
        b'<!doctype html><html><head></head><body>'
        b'<noscript>You need to enable JavaScript to run this app.</noscript>'
        b'<div id="HOSE"><div class="hose-loading"><h4>HOSE</h4></div></div>'
        b'</body></html>'
    )
    assert len(hose_shell) < 8000
    result = classify_access_status(
        HttpResponse(200, "text/html", hose_shell, {})
    )
    assert result == "js_app_shell"


def test_classify_access_status_verified_for_large_html() -> None:
    large_html = b"<html><body>" + b"x" * 9000 + b"</body></html>"
    result = classify_access_status(
        HttpResponse(200, "text/html", large_html, {})
    )
    assert result == "verified"


def test_classify_access_status_js_shell_pit_blocked() -> None:
    from trading_agent.source_adapters.disclosure_adapter import assign_pit_status
    result = assign_pit_status(published_at="", published_date="", access_status="js_app_shell")
    assert result == DisclosurePitStatus.BLOCKED.value


# ---------------------------------------------------------------------------
# Config / activation tests
# ---------------------------------------------------------------------------

def test_fpt_target_configured_after_apply_config() -> None:
    targets = build_default_targets(["FPT"])
    config = {
        "targets": [
            {"dataset": "company_ir_fpt_disclosures", "url": "https://fpt.com/en/ir/information-disclosures"}
        ]
    }
    updated = apply_targets_config(targets, config)
    fpt_ir = next((t for t in updated if t.dataset == "company_ir_fpt_disclosures"), None)
    assert fpt_ir is not None
    assert fpt_ir.is_configured is True
    assert fpt_ir.url == "https://fpt.com/en/ir/information-disclosures"


def test_vci_targets_not_configured_by_default() -> None:
    targets = build_default_targets(["VCI"])
    vci_ir_targets = [t for t in targets if t.symbol == "VCI" and t.source_family == "company_ir"]
    assert len(vci_ir_targets) >= 1
    assert all(not t.is_configured for t in vci_ir_targets)


def test_vci_official_domain_is_vietcap_by_default() -> None:
    targets = build_default_targets(["VCI"])
    vci_ir_targets = [t for t in targets if t.symbol == "VCI" and t.source_family == "company_ir"]
    assert any(t.official_domain == "www.vietcap.com.vn" for t in vci_ir_targets)


def test_plan_request_count_positive_with_fpt_configured(tmp_path: Path) -> None:
    targets = build_default_targets(["FPT"])
    config = {
        "targets": [
            {"dataset": "company_ir_fpt_disclosures", "url": "https://fpt.com/en/ir/information-disclosures"}
        ]
    }
    targets = apply_targets_config(targets, config)
    result = run_disclosure_probe(
        targets=targets,
        max_requests=5,
        sleep_min_seconds=2.0,
        sleep_max_seconds=5.0,
        execute=False,
        force=False,
        run_id="test_pos_plan",
        output_base=tmp_path / "raw",
        bronze_base=tmp_path / "bronze",
    )
    assert result["summary"]["planned_request_count"] > 0
    assert result["summary"]["configured_targets"] > 0


# ---------------------------------------------------------------------------
# FPT HTML execute integration
# ---------------------------------------------------------------------------

def test_execute_fpt_html_produces_numbered_bronze_files(tmp_path: Path) -> None:
    items = [(f"/-/media/fpt/doc{i}.pdf", f"FPT Doc {i}", "4/24/2026") for i in range(3)]
    body = _fpt_ir_html(items)

    def fake_get(url: str, headers: dict) -> HttpResponse:
        return HttpResponse(200, "text/html; charset=utf-8", body, {})

    targets = [_fpt_target()]
    result = run_disclosure_probe(
        targets=targets,
        max_requests=5,
        sleep_min_seconds=2.0,
        sleep_max_seconds=5.0,
        execute=True,
        force=False,
        run_id="test_fpt_exec",
        output_base=tmp_path / "raw",
        bronze_base=tmp_path / "bronze",
        http_get=fake_get,
        sleeper=lambda _: None,
    )

    bronze_dir = Path(result["plan"]["requests"][0]["bronze_dir"])
    assert (bronze_dir / "disclosure_record_000.json").exists()
    assert (bronze_dir / "disclosure_record_001.json").exists()
    assert (bronze_dir / "disclosure_record_002.json").exists()
    assert not (bronze_dir / "disclosure_record.json").exists()


def test_js_app_shell_target_marked_completed_not_failed(tmp_path: Path) -> None:
    hose_shell = (
        b'<!doctype html><html><body>'
        b'<noscript>You need to enable JavaScript to run this app.</noscript>'
        b'<div id="HOSE"></div></body></html>'
    )

    def fake_get(url: str, headers: dict) -> HttpResponse:
        return HttpResponse(200, "text/html", hose_shell, {})

    target = DisclosureTarget(
        source_family="hose",
        exchange="HOSE",
        official_domain="www.hsx.vn",
        adapter_name="hose_disclosure_adapter_v1",
        dataset="hose_disclosures_fpt",
        symbol="FPT",
        url="https://www.hsx.vn/Modules/CMS/Web/CategoryDetail?alias=CBTT",
    )
    result = run_disclosure_probe(
        targets=[target],
        max_requests=5,
        sleep_min_seconds=2.0,
        sleep_max_seconds=5.0,
        execute=True,
        force=False,
        run_id="test_hose_shell",
        output_base=tmp_path / "raw",
        bronze_base=tmp_path / "bronze",
        http_get=fake_get,
        sleeper=lambda _: None,
    )

    assert "hose_disclosures_fpt" in result["summary"]["completed_datasets"]
    assert "hose_disclosures_fpt" not in result["summary"]["failed_datasets"]


# ---------------------------------------------------------------------------
# Security: honest User-Agent (Part C)
# ---------------------------------------------------------------------------

def test_honest_ua_does_not_contain_chrome() -> None:
    ua = _DEFAULT_REQUEST_HEADERS.get("User-Agent", "")
    assert "Chrome" not in ua
    assert "Mozilla" not in ua


def test_honest_ua_identifies_project() -> None:
    ua = _DEFAULT_REQUEST_HEADERS.get("User-Agent", "")
    assert "vsf-agentic-trading-lab" in ua


# ---------------------------------------------------------------------------
# Security: no ssl_verify field on DisclosureTarget (Part B)
# ---------------------------------------------------------------------------

def test_disclosure_target_has_no_ssl_verify_field() -> None:
    import dataclasses
    field_names = {f.name for f in dataclasses.fields(DisclosureTarget)}
    assert "ssl_verify" not in field_names


def test_disclosure_target_creation_does_not_accept_ssl_verify() -> None:
    import dataclasses
    with pytest.raises(TypeError):
        DisclosureTarget(
            source_family="test", exchange="HOSE", official_domain="example.com",
            adapter_name="a", dataset="d", url="https://example.com",
            ssl_verify=False,  # type: ignore[call-arg]
        )


# ---------------------------------------------------------------------------
# Part D: probe-only statuses produce no disclosure records
# ---------------------------------------------------------------------------

def test_extract_disclosure_records_returns_empty_for_js_app_shell(tmp_path: Path) -> None:
    hose_shell = (
        b'<!doctype html><html><body>'
        b'<noscript>You need to enable JavaScript to run this app.</noscript>'
        b'<div id="HOSE"></div></body></html>'
    )
    response = HttpResponse(200, "text/html", hose_shell, {})
    target = DisclosureTarget(
        source_family="hose", exchange="HOSE", official_domain="www.hsx.vn",
        adapter_name="hose_disclosure_adapter_v1", dataset="hose_test", symbol="FPT",
        url="https://www.hsx.vn/Modules/CMS/Web/CategoryDetail?alias=CBTT",
    )
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(hose_shell)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = extract_disclosure_records(
        response=response, target=target,
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )
    assert records == []


def test_extract_disclosure_records_returns_empty_for_auth_required(tmp_path: Path) -> None:
    response = HttpResponse(403, "text/html", b"<html>Forbidden</html>", {})
    target = _configured_target(dataset="auth_test")
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(b"<html>Forbidden</html>")
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = extract_disclosure_records(
        response=response, target=target,
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )
    assert records == []


def test_extract_disclosure_records_returns_empty_for_error_status(tmp_path: Path) -> None:
    response = HttpResponse(500, "text/html", b"Server Error", {})
    target = _configured_target(dataset="error_test")
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(b"Server Error")
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = extract_disclosure_records(
        response=response, target=target,
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )
    assert records == []


def test_js_app_shell_execute_writes_no_bronze_records(tmp_path: Path) -> None:
    hose_shell = (
        b'<!doctype html><html><body>'
        b'<noscript>You need to enable JavaScript to run this app.</noscript>'
        b'<div id="HOSE"></div></body></html>'
    )

    def fake_get(url: str, headers: dict) -> HttpResponse:
        return HttpResponse(200, "text/html", hose_shell, {})

    target = DisclosureTarget(
        source_family="hose", exchange="HOSE", official_domain="www.hsx.vn",
        adapter_name="hose_disclosure_adapter_v1", dataset="hose_disclosures_fpt",
        symbol="FPT", url="https://www.hsx.vn/Modules/CMS/Web/CategoryDetail?alias=CBTT",
    )
    result = run_disclosure_probe(
        targets=[target], max_requests=5, sleep_min_seconds=2.0, sleep_max_seconds=5.0,
        execute=True, force=False, run_id="test_shell_no_bronze",
        output_base=tmp_path / "raw", bronze_base=tmp_path / "bronze",
        http_get=fake_get, sleeper=lambda _: None,
    )
    assert result["bronze_records"] == []


def test_execute_persists_parse_summary_for_fpt_positive_count(tmp_path: Path) -> None:
    body = _fpt_ir_html([("/-/media/fpt/q1-2026-fs.pdf", "FPT Q1 2026 Financial Statements", "4/24/2026")])

    def fake_get(url: str, headers: dict) -> HttpResponse:
        return HttpResponse(200, "text/html; charset=utf-8", body, {})

    result = run_disclosure_probe(
        targets=[_fpt_target()], max_requests=5, sleep_min_seconds=2.0, sleep_max_seconds=5.0,
        execute=True, force=False, run_id="test_fpt_summary",
        output_base=tmp_path / "raw", bronze_base=tmp_path / "bronze",
        http_get=fake_get, sleeper=lambda _: None,
    )
    parse_summary = result["parse_summaries"][0]
    assert parse_summary["dataset"] == "company_ir_fpt_disclosures"
    assert parse_summary["access_status"] == "verified"
    assert parse_summary["http_status"] == 200
    assert parse_summary["parser_name"] == "parse_fpt_ir_html_records"
    assert parse_summary["parse_status"] == "parsed"
    assert parse_summary["bronze_record_count"] == 1
    assert parse_summary["body_sha256"]

    evidence_dir = Path(result["plan"]["requests"][0]["output_dir"])
    assert (evidence_dir / "parse_summary.json").exists()
    checkpoint = load_checkpoint(result["checkpoint_path"])
    assert checkpoint is not None
    assert checkpoint["parse_summaries"][0]["bronze_record_count"] == 1
    plan = json.loads(result["plan_path"].read_text(encoding="utf-8"))
    assert plan["parse_summaries"][0]["bronze_record_count"] == 1
    assert "Parse Summaries" in result["report_path"].read_text(encoding="utf-8")


def test_execute_persists_parse_summary_for_vci_one_row(tmp_path: Path) -> None:
    body = _vci_real_shaped_detail_html(
        title="Financial Statements Q1.2026",
        date_str="20 Apr 2026",
        pdf_href="https://www.vietcap.com.vn/api/cms-api/uploads/froala/files/20260420-vci-q1.pdf",
    )

    def fake_get(url: str, headers: dict) -> HttpResponse:
        return HttpResponse(200, "text/html; charset=utf-8", body, {})

    result = run_disclosure_probe(
        targets=[_vci_q1_target()], max_requests=5, sleep_min_seconds=2.0, sleep_max_seconds=5.0,
        execute=True, force=False, run_id="test_vci_summary",
        output_base=tmp_path / "raw", bronze_base=tmp_path / "bronze",
        http_get=fake_get, sleeper=lambda _: None,
    )
    parse_summary = result["parse_summaries"][0]
    assert parse_summary["parser_name"] == "parse_vci_ir_detail_records"
    assert parse_summary["parse_status"] == "parsed"
    assert parse_summary["bronze_record_count"] == 1


def test_execute_persists_parse_summary_for_hose_spa_shell(tmp_path: Path) -> None:
    hose_shell = (
        b'<!doctype html><html><body>'
        b'<noscript>You need to enable JavaScript to run this app.</noscript>'
        b'<div id="HOSE"></div></body></html>'
    )

    def fake_get(url: str, headers: dict) -> HttpResponse:
        return HttpResponse(200, "text/html", hose_shell, {})

    target = DisclosureTarget(
        source_family="hose", exchange="HOSE", official_domain="www.hsx.vn",
        adapter_name="hose_disclosure_adapter_v1", dataset="hose_disclosures_fpt",
        symbol="FPT", url="https://www.hsx.vn/Modules/CMS/Web/CategoryDetail?alias=CBTT",
    )
    result = run_disclosure_probe(
        targets=[target], max_requests=5, sleep_min_seconds=2.0, sleep_max_seconds=5.0,
        execute=True, force=False, run_id="test_shell_summary",
        output_base=tmp_path / "raw", bronze_base=tmp_path / "bronze",
        http_get=fake_get, sleeper=lambda _: None,
    )
    parse_summary = result["parse_summaries"][0]
    assert parse_summary["bronze_record_count"] == 0
    assert parse_summary["parse_status"] == "no_structured_data"
    assert "js_app_shell_no_structured_data" in parse_summary["warning_codes"]


def test_execute_persists_parse_summary_for_network_error(tmp_path: Path) -> None:
    def fake_get(url: str, headers: dict) -> HttpResponse:
        raise RuntimeError("request_error:timeout")

    target = DisclosureTarget(
        source_family="hnx", exchange="HNX", official_domain="www.hnx.vn",
        adapter_name="hnx_disclosure_adapter_v1", dataset="hnx_disclosures_fpt",
        symbol="FPT", url="https://www.hnx.vn/en-gb/cong-bo-thong-tin.html",
    )
    result = run_disclosure_probe(
        targets=[target], max_requests=5, sleep_min_seconds=2.0, sleep_max_seconds=5.0,
        execute=True, force=False, run_id="test_error_summary",
        output_base=tmp_path / "raw", bronze_base=tmp_path / "bronze",
        http_get=fake_get, sleeper=lambda _: None,
    )
    parse_summary = result["parse_summaries"][0]
    assert parse_summary["access_status"] == "error"
    assert parse_summary["http_status"] == 0
    assert parse_summary["parse_status"] == "fetch_error"
    assert parse_summary["bronze_record_count"] == 0
    assert parse_summary["error_codes"] == ["request_error:timeout"]


def test_execute_persists_parse_summary_for_valid_no_match_html(tmp_path: Path) -> None:
    def fake_get(url: str, headers: dict) -> HttpResponse:
        return HttpResponse(200, "text/html; charset=utf-8", b"<html><body>No disclosures here</body></html>", {})

    result = run_disclosure_probe(
        targets=[_fpt_target()], max_requests=5, sleep_min_seconds=2.0, sleep_max_seconds=5.0,
        execute=True, force=False, run_id="test_nomatch_summary",
        output_base=tmp_path / "raw", bronze_base=tmp_path / "bronze",
        http_get=fake_get, sleeper=lambda _: None,
    )
    parse_summary = result["parse_summaries"][0]
    assert parse_summary["access_status"] == "verified"
    assert parse_summary["parse_status"] == "no_matching_disclosures"
    assert parse_summary["bronze_record_count"] == 0
    assert "no_matching_disclosures" in parse_summary["warning_codes"]


# ---------------------------------------------------------------------------
# Part E: URL domain validation
# ---------------------------------------------------------------------------

def test_normalize_fpt_url_accepts_relative_path() -> None:
    assert _normalize_fpt_url("/-/media/fpt/doc.pdf") == "https://fpt.com/-/media/fpt/doc.pdf"


def test_normalize_fpt_url_accepts_on_domain_absolute() -> None:
    url = "https://fpt.com/-/media/fpt/q1.pdf"
    assert _normalize_fpt_url(url) == url


def test_normalize_fpt_url_rejects_off_domain() -> None:
    assert _normalize_fpt_url("https://evil.com/steal.pdf") == ""


def test_normalize_fpt_url_rejects_partial_domain_match() -> None:
    assert _normalize_fpt_url("https://notfpt.com/doc.pdf") == ""


@pytest.mark.parametrize("bad_url", ["javascript:alert(1)", "data:text/plain,x", "file:///tmp/x.pdf"])
def test_normalize_fpt_url_rejects_unsafe_scheme_with_warning(bad_url: str) -> None:
    result = _normalize_fpt_url_with_warning(bad_url)
    assert result.url == ""
    assert result.warning_code == "unsafe_document_url_scheme"


def test_normalize_fpt_url_rejects_protocol_relative_url() -> None:
    result = _normalize_fpt_url_with_warning("//fpt.com/file.pdf")
    assert result.url == ""
    assert result.warning_code == "invalid_document_url"


def test_normalize_fpt_url_rejects_non_https_absolute_url() -> None:
    result = _normalize_fpt_url_with_warning("http://fpt.com/file.pdf")
    assert result.url == ""
    assert result.warning_code == "unsafe_document_url_scheme"


def test_normalize_fpt_url_rejects_deceptive_suffix_domain() -> None:
    result = _normalize_fpt_url_with_warning("https://fpt.com.evil.example/file.pdf")
    assert result.url == ""
    assert result.warning_code == "off_domain_document_url"


def test_normalize_fpt_url_rejects_userinfo_host_trick() -> None:
    result = _normalize_fpt_url_with_warning("https://fpt.com@evil.example/file.pdf")
    assert result.url == ""
    assert result.warning_code == "off_domain_document_url"


def test_normalize_fpt_url_rejects_malformed_url() -> None:
    result = _normalize_fpt_url_with_warning("https:///file.pdf")
    assert result.url == ""
    assert result.warning_code == "invalid_document_url"


def test_normalize_fpt_url_rejects_empty_url() -> None:
    result = _normalize_fpt_url_with_warning("")
    assert result.url == ""
    assert result.warning_code == "document_url_missing"


def test_normalize_vci_url_accepts_relative_path() -> None:
    assert _normalize_vci_url("/media/vci/annual.pdf") == "https://www.vietcap.com.vn/media/vci/annual.pdf"


def test_normalize_vci_url_accepts_on_domain_absolute() -> None:
    url = "https://www.vietcap.com.vn/media/vci/q1.pdf"
    assert _normalize_vci_url(url) == url


def test_normalize_vci_url_rejects_off_domain() -> None:
    assert _normalize_vci_url("https://evil.com/fake.pdf") == ""


def test_normalize_vci_url_rejects_third_party_with_warning() -> None:
    result = _normalize_vci_url_with_warning("https://evil.com/fake.pdf")
    assert result.url == ""
    assert result.warning_code == "off_domain_document_url"


# ---------------------------------------------------------------------------
# Part F: calendar date validation
# ---------------------------------------------------------------------------

def test_parse_fpt_date_valid() -> None:
    assert _parse_fpt_date("4/24/2026") == "2026-04-24"


def test_parse_fpt_date_invalid_day_returns_empty() -> None:
    assert _parse_fpt_date("13/40/2026") == ""


def test_parse_fpt_date_invalid_month_returns_empty() -> None:
    assert _parse_fpt_date("13/4/2026") == ""


def test_parse_fpt_date_empty_string_returns_empty() -> None:
    assert _parse_fpt_date("") == ""


def test_parse_vci_date_feb_2026() -> None:
    assert _parse_vci_date("13 Feb 2026") == "2026-02-13"


def test_parse_vci_date_apr_2026() -> None:
    assert _parse_vci_date("20 Apr 2026") == "2026-04-20"


def test_parse_vci_date_invalid_returns_empty() -> None:
    assert _parse_vci_date("40 Feb 2026") == ""


def test_parse_vci_date_wrong_format_returns_empty() -> None:
    assert _parse_vci_date("2026-02-13") == ""


# ---------------------------------------------------------------------------
# Part H: Vietcap IR detail-page parser
# ---------------------------------------------------------------------------

def _vci_target(dataset: str = "company_ir_vci_fy2025_fs") -> DisclosureTarget:
    return DisclosureTarget(
        source_family="company_ir",
        exchange="HOSE",
        official_domain="www.vietcap.com.vn",
        adapter_name="company_ir_vietcap_v1",
        dataset=dataset,
        symbol="VCI",
        url="https://www.vietcap.com.vn/en/investor-relations/financial-statements-for-financial-year-of-2025",
    )


def _vci_detail_html(title: str = "Financial Statements FY2025", date_str: str = "13 Feb 2026", pdf_href: str = "/media/vci/fy2025.pdf") -> bytes:
    return f"""<html><head><title>{title} | VCI</title></head><body>
    <h1>{title}</h1>
    <p>Published: {date_str}</p>
    <a href="{pdf_href}">Download PDF</a>
    </body></html>""".encode("utf-8")


def _vci_real_shaped_detail_html(
    *,
    title: str,
    date_str: str,
    pdf_href: str,
    before_detail: str = "",
) -> bytes:
    return f"""<html><head><title>{title} - Vietcap</title></head><body>
    {before_detail}
    <div class="detail-page-container">
      <div class="banner-info-container mx-auto">
        <h1 class="title">{title}</h1>
        <div class="additional-info">
          <span class="type">Financial Reports</span>
          <span class="date">{date_str}</span>
        </div>
      </div>
      <div class="main-content">
        <article class="binding fr-view">
          <p><a class="fr-file" href="{pdf_href}" target="_blank">{title}.pdf</a></p>
        </article>
      </div>
    </div>
    <div class="modal fade" id="login-form-modal"><h2>Log in</h2></div>
    </body></html>""".encode("utf-8")


def _vci_q1_target() -> DisclosureTarget:
    return DisclosureTarget(
        source_family="company_ir", exchange="HOSE", official_domain="www.vietcap.com.vn",
        adapter_name="company_ir_vietcap_v1", dataset="company_ir_vci_q1_2026_fs", symbol="VCI",
        url="https://www.vietcap.com.vn/en/investor-relations/financial-statements-q1-2026",
    )


def test_parse_vci_ir_detail_extracts_title(tmp_path: Path) -> None:
    body = _vci_detail_html(title="VCI Annual Financial Statements 2025")
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_vci_ir_detail_records(
        body=body, target=_vci_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )
    assert len(records) == 1
    assert "Annual Financial Statements 2025" in records[0].title


def test_parse_vci_ir_detail_extracts_date_feb_2026(tmp_path: Path) -> None:
    body = _vci_detail_html(date_str="13 Feb 2026")
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_vci_ir_detail_records(
        body=body, target=_vci_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )
    assert records[0].published_date == "2026-02-13"


def test_parse_vci_ir_detail_extracts_date_apr_2026(tmp_path: Path) -> None:
    target = DisclosureTarget(
        source_family="company_ir", exchange="HOSE", official_domain="www.vietcap.com.vn",
        adapter_name="company_ir_vietcap_v1", dataset="company_ir_vci_q1_2026_fs", symbol="VCI",
        url="https://www.vietcap.com.vn/en/investor-relations/financial-statements-q1-2026",
    )
    body = _vci_detail_html(title="Q1 2026 Financial Statements", date_str="20 Apr 2026")
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_vci_ir_detail_records(
        body=body, target=target,
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )
    assert records[0].published_date == "2026-04-20"


def test_parse_vci_ir_detail_pit_status_date_only_available(tmp_path: Path) -> None:
    body = _vci_detail_html()
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_vci_ir_detail_records(
        body=body, target=_vci_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )
    assert records[0].pit_status == DisclosurePitStatus.DATE_ONLY_AVAILABLE.value


def test_parse_vci_ir_detail_extracts_on_domain_pdf_url(tmp_path: Path) -> None:
    body = _vci_detail_html(pdf_href="/media/vci/fy2025.pdf")
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_vci_ir_detail_records(
        body=body, target=_vci_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )
    assert records[0].document_url == "https://www.vietcap.com.vn/media/vci/fy2025.pdf"
    assert records[0].attachment_type == "pdf"


def test_parse_vci_ir_detail_rejects_off_domain_pdf(tmp_path: Path) -> None:
    body = _vci_detail_html(pdf_href="https://evil.com/fake.pdf")
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_vci_ir_detail_records(
        body=body, target=_vci_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )
    assert records[0].document_url == ""
    assert "off_domain_document_url" in records[0].warning_codes


def test_parse_vci_ir_detail_returns_empty_for_no_content(tmp_path: Path) -> None:
    body = b"<html><body><p>Page not found</p></body></html>"
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_vci_ir_detail_records(
        body=body, target=_vci_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )
    assert records == []


def test_parse_vci_ir_detail_quality_pass(tmp_path: Path) -> None:
    body = _vci_detail_html()
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_vci_ir_detail_records(
        body=body, target=_vci_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )
    assert records[0].error_codes == []


def test_extract_disclosure_records_routes_vci_html_domain(tmp_path: Path) -> None:
    body = _vci_detail_html()
    response = HttpResponse(200, "text/html; charset=utf-8", body, {})
    target = _vci_target()
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = extract_disclosure_records(
        response=response, target=target,
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )
    assert len(records) == 1
    assert records[0].symbol == "VCI"


def test_parse_vci_ir_detail_ignores_login_modal_before_disclosure(tmp_path: Path) -> None:
    body = _vci_real_shaped_detail_html(
        title="Financial Statements Q1.2026",
        date_str="20 Apr 2026",
        pdf_href="https://www.vietcap.com.vn/api/cms-api/uploads/froala/files/20260420-vci-q1.pdf",
        before_detail='<div id="login-form-modal"><h1>Log in</h1><span class="date">01 Jan 2020</span></div>',
    )
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_vci_ir_detail_records(
        body=body, target=_vci_q1_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )
    assert len(records) == 1
    assert records[0].title == "Financial Statements Q1.2026"
    assert records[0].published_date == "2026-04-20"


def test_parse_vci_ir_detail_ignores_unrelated_nav_date(tmp_path: Path) -> None:
    body = _vci_real_shaped_detail_html(
        title="Financial Statements Q1.2026",
        date_str="20 Apr 2026",
        pdf_href="https://www.vietcap.com.vn/api/cms-api/uploads/froala/files/20260420-vci-q1.pdf",
        before_detail='<nav><span class="date">01 Jan 2020</span></nav>',
    )
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_vci_ir_detail_records(
        body=body, target=_vci_q1_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )
    assert records[0].published_date == "2026-04-20"


def test_parse_vci_ir_detail_ignores_unrelated_pdf_before_article(tmp_path: Path) -> None:
    body = _vci_real_shaped_detail_html(
        title="Financial Statements Q1.2026",
        date_str="20 Apr 2026",
        pdf_href="https://www.vietcap.com.vn/api/cms-api/uploads/froala/files/20260420-vci-q1.pdf",
        before_detail='<a href="https://www.vietcap.com.vn/media/unrelated.pdf">unrelated</a>',
    )
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_vci_ir_detail_records(
        body=body, target=_vci_q1_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )
    assert records[0].document_url.endswith("20260420-vci-q1.pdf")


def test_parse_vci_ir_detail_fy_target_rejects_q1_page(tmp_path: Path) -> None:
    body = _vci_real_shaped_detail_html(
        title="Financial Statements Q1.2026",
        date_str="20 Apr 2026",
        pdf_href="https://www.vietcap.com.vn/api/cms-api/uploads/froala/files/20260420-vci-q1.pdf",
    )
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_vci_ir_detail_records(
        body=body, target=_vci_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )
    assert records == []


def test_parse_vci_ir_detail_q1_target_rejects_annual_page(tmp_path: Path) -> None:
    body = _vci_real_shaped_detail_html(
        title="Financial Statements For Financial Year Of 2025",
        date_str="13 Feb 2026",
        pdf_href="https://www.vietcap.com.vn/api/cms-api/uploads/froala/files/20260213-vci-fs-2025.pdf",
    )
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_vci_ir_detail_records(
        body=body, target=_vci_q1_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )
    assert records == []


def test_parse_vci_ir_detail_correct_fy_page(tmp_path: Path) -> None:
    body = _vci_real_shaped_detail_html(
        title="Financial Statements For Financial Year Of 2025",
        date_str="13 Feb 2026",
        pdf_href="https://www.vietcap.com.vn/api/cms-api/uploads/froala/files/20260213-vci-fs-2025.pdf",
    )
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_vci_ir_detail_records(
        body=body, target=_vci_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )
    assert len(records) == 1
    assert records[0].published_date == "2026-02-13"


def test_parse_vci_ir_detail_correct_q1_page(tmp_path: Path) -> None:
    body = _vci_real_shaped_detail_html(
        title="Financial Statements Q1.2026",
        date_str="20 Apr 2026",
        pdf_href="https://www.vietcap.com.vn/api/cms-api/uploads/froala/files/20260420-vci-q1.pdf",
    )
    payload_path = tmp_path / "p.html"
    payload_path.write_bytes(body)
    metadata_path = tmp_path / "m.json"
    metadata_path.write_text("{}", encoding="utf-8")

    records = parse_vci_ir_detail_records(
        body=body, target=_vci_q1_target(),
        payload_path=payload_path, metadata_path=metadata_path,
        crawled_at="2026-06-12T10:00:00+00:00",
    )
    assert len(records) == 1
    assert records[0].published_date == "2026-04-20"


# ---------------------------------------------------------------------------
# Part G: VCI targets configured via config
# ---------------------------------------------------------------------------

def test_vci_fy2025_target_configured_after_apply_config() -> None:
    targets = build_default_targets(["VCI"])
    config = {
        "targets": [
            {
                "dataset": "company_ir_vci_fy2025_fs",
                "url": "https://www.vietcap.com.vn/en/investor-relations/financial-statements-for-financial-year-of-2025",
            }
        ]
    }
    updated = apply_targets_config(targets, config)
    vci_fy = next((t for t in updated if t.dataset == "company_ir_vci_fy2025_fs"), None)
    assert vci_fy is not None
    assert vci_fy.is_configured is True


def test_vci_q1_2026_target_configured_after_apply_config() -> None:
    targets = build_default_targets(["VCI"])
    config = {
        "targets": [
            {
                "dataset": "company_ir_vci_q1_2026_fs",
                "url": "https://www.vietcap.com.vn/en/investor-relations/financial-statements-q1-2026",
            }
        ]
    }
    updated = apply_targets_config(targets, config)
    vci_q1 = next((t for t in updated if t.dataset == "company_ir_vci_q1_2026_fs"), None)
    assert vci_q1 is not None
    assert vci_q1.is_configured is True


# ---------------------------------------------------------------------------
# Part K: FPT document category semantics
# ---------------------------------------------------------------------------

def test_infer_fpt_doc_category_annual_report() -> None:
    assert _infer_fpt_doc_category("Annual Report 2025", "/-/media/fpt/annual-report-2025.pdf") == "annual_report"


def test_infer_fpt_doc_category_quarterly_fs() -> None:
    assert _infer_fpt_doc_category("Financial Statements Q1 2026", "/-/media/fpt/q1-fs.pdf") == "quarterly_financial_statement"


def test_infer_fpt_doc_category_financial_statement_no_quarter() -> None:
    assert _infer_fpt_doc_category("Audited Financial Statements 2025", "/-/media/fpt/fs-2025.pdf") == "financial_statement"


def test_infer_fpt_doc_category_annual_report_is_not_financial_statement() -> None:
    # Annual reports and financial statements are distinct categories
    cat = _infer_fpt_doc_category("Annual Report 2025", "/-/media/fpt/annual-report-2025.pdf")
    assert cat == "annual_report"
    assert cat != "financial_statement"


def test_infer_vci_doc_category_financial_year() -> None:
    assert _infer_vci_doc_category(
        "Financial Statements FY2025",
        "https://www.vietcap.com.vn/en/investor-relations/financial-statements-for-financial-year-of-2025",
    ) == "annual_financial_statement"


def test_infer_vci_doc_category_q1() -> None:
    assert _infer_vci_doc_category(
        "Q1 2026 Financial Statements",
        "https://www.vietcap.com.vn/en/investor-relations/financial-statements-q1-2026",
    ) == "quarterly_financial_statement"
