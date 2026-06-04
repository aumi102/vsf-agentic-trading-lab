from __future__ import annotations

from pathlib import Path

from trading_agent.source_adapters.base import AccessStatus, SourceProbeResult


def write_source_probe_report(
    *,
    report_path: str | Path,
    run_id: str,
    symbols: list[str],
    start: str,
    end: str,
    results: list[SourceProbeResult],
    config_file: str = "",
    config_status: str = "",
) -> None:
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    probed_at = results[0].probed_at if results else ""
    lines = [
        "# Source Probe Report",
        "",
        f"- run_id: `{run_id}`",
        f"- probed_at: `{probed_at}`",
        f"- symbols: `{', '.join(symbols)}`",
        f"- date_range: `{start}` to `{end}`",
        "- active_source_scope: `hose, vietcap_iq, vbma, fred`",
        f"- targets_config: `{config_file or 'none'}`",
        f"- targets_config_status: `{config_status or 'not_used'}`",
        "",
        "## Source Summary",
        "",
        "| Source | Target | Access status | Auth status | Auth mode | Auth param | Endpoint or surface | Observed fields | Row count | Likely canonical tables | Raw paths | Skipped reason | Missing auth env | Terms notes | Next action |",
        "|---|---|---|---|---|---|---|---|---:|---|---|---|---|---|---|",
    ]
    for result in results:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{result.source_name}`",
                    f"`{result.target_name or 'default'}`",
                    f"`{result.access_status.value}`",
                    f"`{result.auth_status}`",
                    f"`{result.auth_in or 'none'}`",
                    f"`{result.auth_param or 'none'}`",
                    _cell(result.endpoint_or_surface),
                    _cell(", ".join(result.original_fields) or "none"),
                    str(result.row_count),
                    _cell(", ".join(result.likely_canonical_tables) or "none"),
                    _cell(", ".join(result.raw_paths) or "none"),
                    _cell(result.target_skipped_reason or "none"),
                    _cell(result.auth_env_missing or "none"),
                    _cell(result.terms_notes or "none"),
                    _cell(result.next_action or "none"),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Source Details", ""])
    for result in results:
        lines.extend(
            [
                f"### {result.source_name}",
                "",
                f"- adapter: `{result.adapter_name}`",
                f"- target_name: `{result.target_name or 'default'}`",
                f"- config_file: `{result.config_file or 'none'}`",
                f"- access_status: `{result.access_status.value}`",
                f"- auth_status: `{result.auth_status}`",
                f"- auth_in: `{result.auth_in or 'none'}`",
                f"- auth_param: `{result.auth_param or 'none'}`",
                f"- datasets: `{', '.join(result.datasets) if result.datasets else 'none'}`",
                f"- likely_canonical_tables: `{', '.join(result.likely_canonical_tables) if result.likely_canonical_tables else 'none'}`",
                f"- raw_paths: `{', '.join(result.raw_paths) if result.raw_paths else 'none'}`",
                f"- metadata_paths: `{', '.join(result.metadata_paths) if result.metadata_paths else 'none'}`",
                f"- target_skipped_reason: `{result.target_skipped_reason or 'none'}`",
                f"- auth_env_missing: `{result.auth_env_missing or 'none'}`",
                f"- warnings: `{', '.join(result.warnings) if result.warnings else 'none'}`",
                f"- errors: `{', '.join(result.errors) if result.errors else 'none'}`",
                "",
            ]
        )

    blocking = [result for result in results if result.access_status in {AccessStatus.AUTH_REQUIRED, AccessStatus.BLOCKED, AccessStatus.ERROR, AccessStatus.REJECTED_RESPONSE}]
    lines.extend(["## Blocking Issues", ""])
    if blocking:
        for result in blocking:
            lines.append(f"- `{result.source_name}`: {', '.join(result.errors) if result.errors else result.next_action}")
    else:
        lines.append("- none")

    readiness = []
    for result in [item for item in results if item.source_name == "hose"]:
        is_candidate = (
            result.access_status == AccessStatus.VERIFIED
            and "daily_prices" in result.likely_canonical_tables
            and bool(result.raw_paths)
            and result.source_name == "hose"
        )
        readiness.append((result, is_candidate))

    canonical_ohlcv = [
        f"{result.source_name}/{result.target_name or 'default'}"
        for result in results
        if (
            result.access_status == AccessStatus.VERIFIED
            and "daily_prices" in result.likely_canonical_tables
            and bool(result.raw_paths)
            and result.source_name == "hose"
        )
    ]
    lines.extend(["", "## Canonical Stock Data Readiness For HSX/HOSE", ""])
    lines.extend(["| Source | Target | Candidate? | Reason |", "|---|---|---|---|"])
    for result, is_candidate in readiness:
        reason = "verified daily_prices target with raw sample" if is_candidate else _readiness_reason(result)
        lines.append(f"| `{result.source_name}` | `{result.target_name or 'default'}` | `{str(is_candidate).lower()}` | {_cell(reason)} |")

    lines.extend(["", "## Full-Market Universe And Company/Financial Readiness For Vietcap IQ", ""])
    _append_source_readiness(
        lines,
        results,
        "vietcap_iq",
        {
            "securities_master",
            "exchange_listings",
            "symbol_universe",
            "instrument_universe",
            "company_profiles",
            "financial_statement_items",
            "financial_ratios",
            "company_reports",
            "report_documents",
        },
    )

    lines.extend(["", "## Bonds/Macro Local Readiness For VBMA", ""])
    _append_source_readiness(lines, results, "vbma", {"bond_auctions", "bond_instruments", "yield_curve_points", "bond_reports", "macro_context_events"})

    lines.extend(["", "## Global Macro Readiness For FRED", ""])
    _append_source_readiness(lines, results, "fred", {"macro_series", "macro_observations", "macro_features"})

    lines.extend(["", "## Sources That Could Support Canonical OHLCV", ""])
    if canonical_ohlcv:
        lines.extend(f"- `{source}`" for source in canonical_ohlcv)
    else:
        lines.append("- none verified yet")

    lines.extend(
        [
            "",
            "## Manual Investigation Only",
            "",
        ]
    )
    manual_only = [result for result in results if result.access_status == AccessStatus.MANUAL_ONLY]
    if manual_only:
        lines.extend(f"- `{result.source_name}`: {result.next_action}" for result in manual_only)
    else:
        lines.append("- none")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _cell(value: str) -> str:
    return value.replace("|", "/").replace("\n", " ")


def _readiness_reason(result: SourceProbeResult) -> str:
    if result.access_status != AccessStatus.VERIFIED:
        return f"access_status is {result.access_status.value}"
    if "daily_prices" not in result.likely_canonical_tables:
        return "target does not map to daily_prices"
    if not result.raw_paths:
        return "no raw sample captured"
    return "not candidate"


def _append_source_readiness(lines: list[str], results: list[SourceProbeResult], source_name: str, expected_tables: set[str]) -> None:
    matching = [result for result in results if result.source_name == source_name]
    if not matching:
        lines.append(f"- `{source_name}` not probed")
        return
    lines.extend(["| Source | Target | Candidate? | Reason |", "|---|---|---|---|"])
    for result in matching:
        has_mapping = bool(set(result.likely_canonical_tables).intersection(expected_tables))
        is_candidate = result.access_status == AccessStatus.VERIFIED and has_mapping and bool(result.raw_paths)
        if is_candidate:
            reason = "verified target with raw sample and expected table mapping"
        elif result.access_status != AccessStatus.VERIFIED:
            reason = f"access_status is {result.access_status.value}"
        elif not has_mapping:
            reason = "target does not map to expected tables"
        else:
            reason = "no raw sample captured"
        lines.append(f"| `{result.source_name}` | `{result.target_name or 'default'}` | `{str(is_candidate).lower()}` | {_cell(reason)} |")
