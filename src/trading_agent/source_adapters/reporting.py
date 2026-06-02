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
        "",
        "## Source Summary",
        "",
        "| Source | Access status | Auth status | Endpoint or surface | Observed fields | Row count | Likely canonical tables | Raw paths | Terms notes | Next action |",
        "|---|---|---|---|---|---:|---|---|---|---|",
    ]
    for result in results:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{result.source_name}`",
                    f"`{result.access_status.value}`",
                    f"`{result.auth_status}`",
                    _cell(result.endpoint_or_surface),
                    _cell(", ".join(result.original_fields) or "none"),
                    str(result.row_count),
                    _cell(", ".join(result.likely_canonical_tables) or "none"),
                    _cell(", ".join(result.raw_paths) or "none"),
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
                f"- access_status: `{result.access_status.value}`",
                f"- auth_status: `{result.auth_status}`",
                f"- datasets: `{', '.join(result.datasets) if result.datasets else 'none'}`",
                f"- likely_canonical_tables: `{', '.join(result.likely_canonical_tables) if result.likely_canonical_tables else 'none'}`",
                f"- raw_paths: `{', '.join(result.raw_paths) if result.raw_paths else 'none'}`",
                f"- metadata_paths: `{', '.join(result.metadata_paths) if result.metadata_paths else 'none'}`",
                f"- warnings: `{', '.join(result.warnings) if result.warnings else 'none'}`",
                f"- errors: `{', '.join(result.errors) if result.errors else 'none'}`",
                "",
            ]
        )

    blocking = [result for result in results if result.access_status in {AccessStatus.AUTH_REQUIRED, AccessStatus.BLOCKED, AccessStatus.ERROR}]
    lines.extend(["## Blocking Issues", ""])
    if blocking:
        for result in blocking:
            lines.append(f"- `{result.source_name}`: {', '.join(result.errors) if result.errors else result.next_action}")
    else:
        lines.append("- none")

    canonical_ohlcv = [
        result.source_name
        for result in results
        if result.access_status == AccessStatus.VERIFIED
        and "daily_prices" in result.likely_canonical_tables
        and result.source_name != "vnstock_reference"
    ]
    lines.extend(["", "## Sources That Could Support Canonical OHLCV", ""])
    if canonical_ohlcv:
        lines.extend(f"- `{source}`" for source in canonical_ohlcv)
    else:
        lines.append("- none verified yet")

    context_only = [
        result.source_name
        for result in results
        if set(result.likely_canonical_tables).intersection({"reports", "macro_series", "macro_observations", "yield_curve_points", "bond_auctions"})
    ]
    lines.extend(["", "## Context-Only Sources", ""])
    if context_only:
        lines.extend(f"- `{source}`" for source in context_only)
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Explicit Warning",
            "",
            "- `vnstock_reference` is prototype/fallback only and must not be treated as canonical MVP source.",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _cell(value: str) -> str:
    return value.replace("|", "/").replace("\n", " ")
