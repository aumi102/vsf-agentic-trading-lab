from __future__ import annotations

import os

from trading_agent.source_adapters.base import SourceAdapter, SourceProbeResult


class VietcapIqAdapter(SourceAdapter):
    source_name = "vietcap_iq"

    def probe(self, symbols: list[str], start: str, end: str, run_id: str) -> SourceProbeResult:
        url = os.getenv("VIETCAP_IQ_PROBE_URL", "").strip() or os.getenv("VIETCAP_PROBE_URL", "").strip()
        token = os.getenv("VIETCAP_IQ_TOKEN", "").strip() or os.getenv("VIETCAP_TOKEN", "").strip()
        likely_tables = [
            "securities_master",
            "exchange_listings",
            "symbol_universe",
            "instrument_universe",
            "company_profiles",
            "financial_statement_items",
            "financial_ratios",
            "company_reports",
            "report_documents",
        ]
        if not url:
            return self._not_configured_result(
                symbols=symbols,
                start=start,
                end=end,
                endpoint_or_surface="VIETCAP_IQ_PROBE_URL not configured",
                datasets=["company_search_bar", "instrument_universe", "financial_reports", "company_reports", "company_data", "financial_statements", "ratios", "documents"],
                likely_canonical_tables=likely_tables,
                terms_notes="Vietcap IQ is the preferred full-market universe candidate plus company/financial reports and evidence context; do not label as OHLCV without raw fields.",
                next_action="Probe the Vietcap IQ company search-bar universe candidate first, then verify row-level fields, coverage, access, and terms.",
                auth_status="missing_url",
            )
        headers = {"User-Agent": "vsf-source-probe/0.1"}
        auth_status = "public_or_token_absent"
        if token:
            headers["Authorization"] = f"Bearer {token}"
            auth_status = "token_configured"
        return self._probe_url(
            url=url,
            dataset="vietcap_iq_probe",
            symbols=symbols[:2],
            start=start,
            end=end,
            run_id=run_id,
            likely_canonical_tables=likely_tables,
            request_params={"url": url, "symbols": symbols[:2]},
            headers=headers,
            auth_status=auth_status,
            terms_notes="Vietcap IQ probe only; verify row-level universe fields and licensing before parser planning or local storage of reports/documents.",
        )
