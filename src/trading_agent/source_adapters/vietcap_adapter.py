from __future__ import annotations

import os

from trading_agent.source_adapters.base import SourceAdapter, SourceProbeResult


class VietcapAdapter(SourceAdapter):
    source_name = "vietcap"

    def probe(self, symbols: list[str], start: str, end: str, run_id: str) -> SourceProbeResult:
        url = os.getenv("VIETCAP_PROBE_URL", "").strip()
        token = os.getenv("VIETCAP_TOKEN", "").strip()
        if not url:
            return self._not_configured_result(
                symbols=symbols,
                start=start,
                end=end,
                endpoint_or_surface="VIETCAP_PROBE_URL not configured",
                datasets=["research_reports", "company_research"],
                likely_canonical_tables=["reports"],
                terms_notes="Vietcap is report/evidence context, not primary OHLCV.",
                next_action="Identify permitted Vietcap IQ/Research access mode and set VIETCAP_PROBE_URL if probing is allowed.",
                auth_status="missing_url",
            )
        headers = {"User-Agent": "vsf-source-probe/0.1"}
        auth_status = "public_or_token_absent"
        if token:
            headers["Authorization"] = f"Bearer {token}"
            auth_status = "token_configured"
        return self._probe_url(
            url=url,
            dataset="vietcap_reports_probe",
            symbols=symbols[:2],
            start=start,
            end=end,
            run_id=run_id,
            likely_canonical_tables=["reports"],
            request_params={"url": url, "symbols": symbols[:2]},
            headers=headers,
            auth_status=auth_status,
            terms_notes="Reports/evidence probe only; verify licensing before local storage.",
        )
