from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts.validate_vietcap_iq_fa_publicdate_samples import (
    DEFAULT_INPUT,
    classify_delta,
    load_and_validate,
    normalize_row,
)


FIELDNAMES = [
    "sample_id",
    "symbol",
    "issuer_name",
    "sector",
    "section",
    "run_id",
    "evidence_run_id",
    "payload_path",
    "raw_evidence_path",
    "fiscal_year",
    "length_report",
    "period_type",
    "period_label",
    "vietcap_public_date",
    "vietcap_update_date",
    "server_datetime",
    "crawled_at",
    "official_source_type",
    "official_source_url",
    "official_disclosure_date",
    "official_document_title",
    "official_date_basis",
    "date_delta_days",
    "match_status",
    "confidence",
    "reviewer_note",
]


def row(**overrides: str) -> dict[str, str]:
    base = {name: "" for name in FIELDNAMES}
    base.update({
        "sample_id": "sample",
        "symbol": "FPT",
        "section": "BALANCE_SHEET",
        "period_label": "2025Y",
        "vietcap_public_date": "2026-03-20",
        "official_source_url": "https://fpt.com/en/ir/information-disclosures",
        "official_disclosure_date": "2026-03-20",
        "official_document_title": "Financial Statements 2025",
        "confidence": "medium",
    })
    base.update(overrides)
    return base


def evidence_row(
    sample_id: str,
    *,
    symbol: str,
    period_label: str,
    official_date: str,
    title: str,
    confidence: str = "high",
    status: str = "",
    vietcap_date: str | None = None,
    source_url: str | None = None,
    section: str = "BALANCE_SHEET",
    sector: str = "Technology",
    issuer_name: str | None = None,
) -> dict[str, str]:
    return row(
        sample_id=sample_id,
        symbol=symbol,
        issuer_name=issuer_name or f"{symbol} Issuer",
        sector=sector,
        section=section,
        period_label=period_label,
        vietcap_public_date=vietcap_date or official_date,
        official_source_url=source_url or f"https://example.com/{symbol.lower()}/{period_label}",
        official_disclosure_date=official_date,
        official_document_title=title,
        match_status=status,
        date_delta_days="",
        confidence=confidence,
    )


def breadth_event(
    idx: int,
    *,
    symbol: str,
    sector: str,
    period_label: str,
    period_type: str,
    official_date: str,
    vietcap_date: str | None = None,
    status: str = "",
    confidence: str = "high",
) -> dict[str, str]:
    return evidence_row(
        f"breadth_{idx}",
        symbol=symbol,
        sector=sector,
        period_label=period_label,
        official_date=official_date,
        vietcap_date=vietcap_date or official_date,
        title=f"{symbol} {period_label} financial statements",
        status=status,
        confidence=confidence,
    ) | {"period_type": period_type}


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def test_exact_match_classification() -> None:
    normalized = normalize_row(row(match_status="", date_delta_days=""))
    assert normalized["date_delta_days"] == "0"
    assert normalized["match_status"] == "exact_match"


def test_near_match_within_one_to_three_days() -> None:
    assert classify_delta(1) == "near_match_1_3_days"
    assert classify_delta(3) == "near_match_1_3_days"


def test_vietcap_after_official_by_more_than_three_days() -> None:
    normalized = normalize_row(row(
        vietcap_public_date="2026-04-28",
        official_disclosure_date="2026-04-24",
        match_status="",
        date_delta_days="",
    ))
    assert normalized["date_delta_days"] == "4"
    assert normalized["match_status"] == "vietcap_after_official"


def test_vietcap_before_official_red_flag_status() -> None:
    normalized = normalize_row(row(
        vietcap_public_date="2026-04-20",
        official_disclosure_date="2026-04-24",
        match_status="",
        date_delta_days="",
    ))
    assert normalized["date_delta_days"] == "-4"
    assert normalized["match_status"] == "vietcap_before_official"


def test_official_not_found_preserved() -> None:
    normalized = normalize_row(row(
        official_disclosure_date="",
        match_status="official_not_found",
        confidence="none",
    ))
    assert normalized["match_status"] == "official_not_found"


def test_network_error_preserved_and_not_blocked() -> None:
    normalized = normalize_row(row(
        official_disclosure_date="",
        match_status="network_error",
        confidence="none",
    ))
    assert normalized["match_status"] == "network_error"
    assert normalized["match_status"] != "blocked"


def test_network_error_does_not_count_as_credible_evidence(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    write_csv(path, [
        evidence_row("a", symbol="AAA", period_label="2025Y", official_date="2026-03-20", title="AAA FY"),
        row(
            sample_id="b",
            symbol="VCB",
            period_label="2025Y",
            official_disclosure_date="",
            match_status="network_error",
            confidence="none",
        ),
    ])
    _, summary = load_and_validate(path)
    assert summary["credible_unique_evidence_events"] == 1
    assert summary["blocked_manual_unresolved_targets"] == 1


def test_ambiguous_basis_preserved() -> None:
    normalized = normalize_row(row(match_status="ambiguous_basis", confidence="low"))
    assert normalized["match_status"] == "ambiguous_basis"


def test_malformed_date_handling() -> None:
    with pytest.raises(ValueError, match="Malformed vietcap_public_date"):
        normalize_row(row(vietcap_public_date="20-03-2026", match_status=""))


def test_invalid_match_status_raises() -> None:
    with pytest.raises(ValueError, match="Invalid match_status"):
        normalize_row(row(match_status="after_official"))


def test_invalid_confidence_raises() -> None:
    with pytest.raises(ValueError, match="Invalid confidence"):
        normalize_row(row(confidence="certain"))


def test_mismatched_date_delta_raises() -> None:
    with pytest.raises(ValueError, match="date_delta_days mismatch"):
        normalize_row(row(
            vietcap_public_date="2026-04-28",
            official_disclosure_date="2026-04-24",
            date_delta_days="3",
        ))


def test_explicit_wrong_status_vs_computed_status_raises() -> None:
    with pytest.raises(ValueError, match="match_status mismatch"):
        normalize_row(row(
            vietcap_public_date="2026-04-28",
            official_disclosure_date="2026-04-24",
            match_status="near_match_1_3_days",
        ))


def test_comparable_status_requires_official_date() -> None:
    with pytest.raises(ValueError, match="official_disclosure_date missing"):
        normalize_row(row(
            official_disclosure_date="",
            match_status="vietcap_after_official",
        ))


def test_committed_csv_returns_pit_supported_small_sample() -> None:
    _, summary = load_and_validate(DEFAULT_INPUT)
    assert summary["total_samples"] == 8
    assert summary["total_statement_rows"] == 8
    assert summary["credible_statement_rows"] == 8
    assert summary["credible_statement_ratio"] == 1.0
    assert summary["credible_comparable_count"] == 8
    assert summary["credible_comparable_ratio"] == 1.0
    assert summary["unique_evidence_events"] == 4
    assert summary["credible_unique_evidence_events"] == 4
    assert summary["credible_evidence_ratio"] == 1.0
    assert summary["unique_issuers"] == 2
    assert summary["unique_issuer_period_events"] == 4
    assert summary["red_flag_count"] == 0
    assert summary["pit_sample_status"] == "pit_supported_small_sample"
    assert summary["match_status_counts"]["exact_match"] == 2
    assert summary["match_status_counts"]["near_match_1_3_days"] == 4
    assert summary["match_status_counts"]["vietcap_after_official"] == 2
    assert summary["match_status_counts"]["official_not_found"] == 0
    assert summary["match_status_counts"]["vietcap_before_official"] == 0
    assert summary["confidence_counts"]["high"] == 4
    assert summary["confidence_counts"]["medium"] == 4
    assert summary["confidence_counts"]["none"] == 0


def test_final_status_supported_small_sample(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    write_csv(path, [
        evidence_row("a", symbol="AAA", period_label="2025Y", official_date="2026-03-20", title="AAA FY"),
        evidence_row("b", symbol="AAA", period_label="2026Q1", official_date="2026-04-20", title="AAA Q1"),
        evidence_row("c", symbol="BBB", period_label="2025Y", official_date="2026-03-22", title="BBB FY"),
        evidence_row("d", symbol="BBB", period_label="2026Q1", official_date="2026-04-22", title="BBB Q1"),
    ])
    _, summary = load_and_validate(path)
    assert summary["pit_sample_status"] == "pit_supported_small_sample"
    assert summary["pit_sample_status"] != "pit_confirmed_full"


def test_duplicate_sections_sharing_disclosure_count_as_one_event(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    write_csv(path, [
        evidence_row("a", symbol="AAA", period_label="2025Y", official_date="2026-03-20", title="AAA FY", section="BALANCE_SHEET"),
        evidence_row("b", symbol="AAA", period_label="2025Y", official_date="2026-03-20", title="AAA FY", section="INCOME_STATEMENT"),
        evidence_row("c", symbol="AAA", period_label="2025Y", official_date="2026-03-20", title="AAA FY", section="CASH_FLOW"),
    ])
    _, summary = load_and_validate(path)
    assert summary["credible_statement_rows"] == 3
    assert summary["credible_statement_ratio"] == 1.0
    assert summary["unique_evidence_events"] == 1
    assert summary["credible_unique_evidence_events"] == 1
    assert summary["unique_issuer_period_events"] == 1
    assert summary["pit_sample_status"] == "pit_inconclusive"


def test_one_issuer_many_duplicate_rows_cannot_reach_supported(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    write_csv(path, [
        evidence_row("a", symbol="AAA", period_label="2025Y", official_date="2026-03-20", title="AAA FY", section="BALANCE_SHEET"),
        evidence_row("b", symbol="AAA", period_label="2025Y", official_date="2026-03-20", title="AAA FY", section="INCOME_STATEMENT"),
        evidence_row("c", symbol="AAA", period_label="2026Q1", official_date="2026-04-20", title="AAA Q1", section="BALANCE_SHEET"),
        evidence_row("d", symbol="AAA", period_label="2026Q1", official_date="2026-04-20", title="AAA Q1", section="CASH_FLOW"),
        evidence_row("e", symbol="AAA", period_label="2026Q2", official_date="2026-07-20", title="AAA Q2", section="BALANCE_SHEET"),
        evidence_row("f", symbol="AAA", period_label="2026Q3", official_date="2026-10-20", title="AAA Q3", section="BALANCE_SHEET"),
    ])
    _, summary = load_and_validate(path)
    assert summary["credible_statement_ratio"] == 1.0
    assert summary["credible_unique_evidence_events"] == 4
    assert summary["unique_issuers"] == 1
    assert summary["pit_sample_status"] == "pit_inconclusive"


def test_two_issuers_fewer_than_four_credible_events_inconclusive(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    write_csv(path, [
        evidence_row("a", symbol="AAA", period_label="2025Y", official_date="2026-03-20", title="AAA FY"),
        evidence_row("b", symbol="AAA", period_label="2026Q1", official_date="2026-04-20", title="AAA Q1"),
        evidence_row("c", symbol="BBB", period_label="2025Y", official_date="2026-03-22", title="BBB FY"),
    ])
    _, summary = load_and_validate(path)
    assert summary["unique_issuers"] == 2
    assert summary["credible_unique_evidence_events"] == 3
    assert summary["pit_sample_status"] == "pit_inconclusive"


def test_low_none_and_secondary_evidence_do_not_count_as_credible(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    write_csv(path, [
        evidence_row("a", symbol="AAA", period_label="2025Y", official_date="2026-03-20", title="AAA FY", confidence="high"),
        evidence_row("b", symbol="AAA", period_label="2026Q1", official_date="2026-04-20", title="AAA Q1", confidence="medium"),
        evidence_row("c", symbol="BBB", period_label="2025Y", official_date="2026-03-22", title="BBB FY", confidence="low"),
        evidence_row("d", symbol="BBB", period_label="2026Q1", official_date="2026-04-22", title="BBB Q1", confidence="none"),
        row(
            sample_id="e",
            symbol="CCC",
            period_label="2025Y",
            official_source_type="secondary_aggregator",
            official_disclosure_date="",
            official_document_title="",
            match_status="not_comparable",
            confidence="low",
        ),
    ])
    _, summary = load_and_validate(path)
    assert summary["credible_statement_rows"] == 2
    assert summary["credible_unique_evidence_events"] == 2
    assert summary["credible_statement_ratio"] == 0.4
    assert summary["pit_sample_status"] == "pit_inconclusive"


def test_official_not_found_rows_do_not_count_as_events(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    write_csv(path, [
        evidence_row("a", symbol="AAA", period_label="2025Y", official_date="2026-03-20", title="AAA FY"),
        row(
            sample_id="b",
            symbol="BBB",
            period_label="2025Y",
            official_source_url="",
            official_disclosure_date="",
            official_document_title="",
            match_status="official_not_found",
            confidence="none",
        ),
    ])
    _, summary = load_and_validate(path)
    assert summary["unique_evidence_events"] == 1
    assert summary["credible_unique_evidence_events"] == 1
    assert summary["pit_sample_status"] == "pit_inconclusive"


def test_red_flag_overrides_otherwise_sufficient_support(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    write_csv(path, [
        evidence_row("a", symbol="AAA", period_label="2025Y", official_date="2026-03-20", title="AAA FY"),
        evidence_row("b", symbol="AAA", period_label="2026Q1", official_date="2026-04-20", title="AAA Q1"),
        evidence_row("c", symbol="BBB", period_label="2025Y", official_date="2026-03-22", title="BBB FY"),
        evidence_row("d", symbol="BBB", period_label="2026Q1", official_date="2026-04-22", title="BBB Q1"),
        evidence_row(
            "e",
            symbol="CCC",
            period_label="2025Y",
            official_date="2026-03-20",
            title="CCC FY",
            vietcap_date="2026-03-19",
        ),
    ])
    _, summary = load_and_validate(path)
    assert summary["red_flag_count"] == 1
    assert summary["pit_sample_status"] == "pit_red_flags_found"


def test_final_status_inconclusive(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    write_csv(path, [
        row(sample_id="a"),
        row(sample_id="b", match_status="official_not_found", confidence="none", official_disclosure_date=""),
        row(sample_id="c", match_status="official_not_found", confidence="none", official_disclosure_date=""),
    ])
    _, summary = load_and_validate(path)
    assert summary["pit_sample_status"] == "pit_inconclusive"


def test_final_status_red_flags_found(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    write_csv(path, [
        row(sample_id="a", vietcap_public_date="2026-03-19", official_disclosure_date="2026-03-20"),
        row(sample_id="b"),
    ])
    _, summary = load_and_validate(path)
    assert summary["pit_sample_status"] == "pit_red_flags_found"


def test_check_payload_paths_missing_raises(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    write_csv(path, [row(sample_id="a", payload_path="data/nonexistent/payload.json")])
    with pytest.raises(FileNotFoundError, match="Payload path not found"):
        load_and_validate(path, check_payload_paths=True)


def test_check_payload_paths_skipped_by_default(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    write_csv(path, [row(sample_id="a", payload_path="data/nonexistent/payload.json")])
    _, summary = load_and_validate(path)  # no error when check_payload_paths=False
    assert summary["total_samples"] == 1


def test_never_emits_pit_confirmed_full(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    write_csv(path, [
        evidence_row("a", symbol="AAA", period_label="2025Y", official_date="2026-03-20", title="AAA FY"),
        evidence_row("b", symbol="AAA", period_label="2026Q1", official_date="2026-04-20", title="AAA Q1"),
        evidence_row("c", symbol="BBB", period_label="2025Y", official_date="2026-03-22", title="BBB FY"),
        evidence_row("d", symbol="BBB", period_label="2026Q1", official_date="2026-04-22", title="BBB Q1"),
    ])
    _, summary = load_and_validate(path)
    assert summary["pit_sample_status"] in {
        "pit_supported_small_sample",
        "pit_inconclusive",
        "pit_red_flags_found",
    }
    assert summary["pit_sample_status"] != "pit_confirmed_full"


def test_breadth_duplicate_sections_do_not_inflate_events(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    write_csv(path, [
        breadth_event(1, symbol="AAA", sector="Tech", period_label="2025Y", period_type="annual", official_date="2026-03-20",) | {"section": "BALANCE_SHEET"},
        breadth_event(2, symbol="AAA", sector="Tech", period_label="2025Y", period_type="annual", official_date="2026-03-20",) | {"section": "INCOME_STATEMENT"},
    ])
    _, summary = load_and_validate(path)
    assert summary["credible_statement_rows"] == 2
    assert summary["credible_unique_evidence_events"] == 1
    assert summary["verified_issuers"] == 1
    assert summary["verified_sectors"] == 1


def test_breadth_one_sector_many_issuers_cannot_satisfy(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    rows = [
        breadth_event(i, symbol=f"A{i}", sector="Tech", period_label="2025Y", period_type="annual", official_date="2026-03-20")
        for i in range(1, 13)
    ]
    write_csv(path, rows)
    _, summary = load_and_validate(path)
    assert summary["verified_issuers"] == 12
    assert summary["verified_sectors"] == 1
    assert summary["pit_sample_status"] == "pit_supported_small_sample"


def test_breadth_six_issuers_fewer_than_five_sectors_cannot_satisfy(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    rows = []
    sectors = ["Bank", "Bank", "Retail", "Retail", "Tech", "Tech"]
    for idx, sector in enumerate(sectors, start=1):
        rows.append(breadth_event(idx, symbol=f"S{idx}", sector=sector, period_label="2025Y", period_type="annual", official_date="2026-03-20"))
        rows.append(breadth_event(idx + 20, symbol=f"S{idx}", sector=sector, period_label="2026Q1", period_type="quarterly", official_date="2026-04-20"))
    write_csv(path, rows)
    _, summary = load_and_validate(path)
    assert summary["verified_issuers"] == 6
    assert summary["verified_sectors"] == 3
    assert summary["credible_unique_evidence_events"] == 12
    assert summary["pit_sample_status"] == "pit_supported_small_sample"


def test_breadth_fewer_than_twelve_events_cannot_satisfy(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    rows = [
        breadth_event(i, symbol=f"S{i}", sector=f"Sector{i}", period_label="2025Y", period_type="annual", official_date="2026-03-20")
        for i in range(1, 7)
    ]
    rows.extend([
        breadth_event(i + 10, symbol=f"S{i}", sector=f"Sector{i}", period_label="2026Q1", period_type="quarterly", official_date="2026-04-20")
        for i in range(1, 5)
    ])
    write_csv(path, rows)
    _, summary = load_and_validate(path)
    assert summary["credible_unique_evidence_events"] == 10
    assert summary["verified_sectors"] == 6
    assert summary["pit_sample_status"] == "pit_supported_small_sample"


def test_breadth_annual_only_cannot_satisfy(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    rows = [
        breadth_event(i, symbol=f"S{i}", sector=f"Sector{i}", period_label=f"2025Y_{i}", period_type="annual", official_date="2026-03-20")
        for i in range(1, 13)
    ]
    write_csv(path, rows)
    _, summary = load_and_validate(path)
    assert summary["annual_evidence_events"] == 12
    assert summary["quarterly_evidence_events"] == 0
    assert summary["pit_sample_status"] == "pit_supported_small_sample"


def test_breadth_quarterly_only_cannot_satisfy(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    rows = [
        breadth_event(i, symbol=f"S{i}", sector=f"Sector{i}", period_label=f"2026Q{i}", period_type="quarterly", official_date="2026-04-20")
        for i in range(1, 13)
    ]
    write_csv(path, rows)
    _, summary = load_and_validate(path)
    assert summary["annual_evidence_events"] == 0
    assert summary["quarterly_evidence_events"] == 12
    assert summary["pit_sample_status"] == "pit_supported_small_sample"


def test_breadth_red_flag_overrides_support(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    rows = qualifying_breadth_rows()
    rows.append(breadth_event(
        99,
        symbol="RED",
        sector="Energy",
        period_label="2025Y",
        period_type="annual",
        official_date="2026-03-20",
        vietcap_date="2026-03-19",
    ))
    write_csv(path, rows)
    _, summary = load_and_validate(path)
    assert summary["pit_sample_status"] == "pit_red_flags_found"


def test_breadth_unresolved_evidence_does_not_count(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    rows = qualifying_breadth_rows()[:10]
    rows.extend([
        row(sample_id="u1", symbol="U1", sector="Bank", match_status="official_not_found", confidence="none", official_disclosure_date=""),
        row(sample_id="u2", symbol="U2", sector="Retail", match_status="blocked", confidence="none", official_disclosure_date=""),
    ])
    write_csv(path, rows)
    _, summary = load_and_validate(path)
    assert summary["credible_unique_evidence_events"] == 10
    assert summary["blocked_manual_unresolved_targets"] == 2
    assert summary["pit_sample_status"] == "pit_supported_small_sample"


def test_existing_small_sample_still_supported_small_not_breadth() -> None:
    _, summary = load_and_validate(DEFAULT_INPUT)
    assert summary["pit_sample_status"] == "pit_supported_small_sample"
    assert summary["pit_sample_status"] != "pit_supported_breadth_sample"


def qualifying_breadth_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    sectors = ["Bank", "Securities", "Industrial", "Retail", "Consumer", "Real estate"]
    for idx, sector in enumerate(sectors, start=1):
        rows.append(breadth_event(
            idx,
            symbol=f"S{idx}",
            sector=sector,
            period_label="2025Y",
            period_type="annual",
            official_date="2026-03-20",
        ))
        rows.append(breadth_event(
            idx + 20,
            symbol=f"S{idx}",
            sector=sector,
            period_label="2026Q1",
            period_type="quarterly",
            official_date="2026-04-20",
        ))
    return rows


def test_qualifying_synthetic_breadth_sample_supported(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    write_csv(path, qualifying_breadth_rows())
    _, summary = load_and_validate(path)
    assert summary["verified_issuers"] == 6
    assert summary["verified_sectors"] == 6
    assert summary["credible_unique_evidence_events"] == 12
    assert summary["annual_evidence_events"] == 6
    assert summary["quarterly_evidence_events"] == 6
    assert summary["pit_sample_status"] == "pit_supported_breadth_sample"


def test_breadth_status_never_full_confirmation(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    write_csv(path, qualifying_breadth_rows())
    _, summary = load_and_validate(path)
    assert summary["pit_sample_status"] != "pit_confirmed_full"
