from __future__ import annotations

import os

from trading_agent.source_adapters.base import SourceAdapter, SourceProbeResult


class FiinGroupAdapter(SourceAdapter):
    source_name = "fiingroup"

    def probe(self, symbols: list[str], start: str, end: str, run_id: str) -> SourceProbeResult:
        base_url = os.getenv("FIINGROUP_BASE_URL", "").strip()
        token = os.getenv("FIINGROUP_TOKEN", "").strip()
        datasets = ["EOD price", "adjusted price", "foreign trading", "corporate actions", "market depth"]
        if not base_url or not token:
            return self._not_configured_result(
                symbols=symbols,
                start=start,
                end=end,
                endpoint_or_surface="FIINGROUP_BASE_URL/FIINGROUP_TOKEN not configured",
                datasets=datasets,
                likely_canonical_tables=["securities", "daily_prices", "corporate_events"],
                terms_notes="Candidate paid/vendor feed; access and terms must be verified.",
                next_action="Configure FiinGroup credentials or obtain docs before probing.",
            )
        url = f"{base_url.rstrip('/')}/"
        return self._probe_url(
            url=url,
            dataset="fiingroup_market_data_probe",
            symbols=symbols[:2],
            start=start,
            end=end,
            run_id=run_id,
            likely_canonical_tables=["securities", "daily_prices", "corporate_events"],
            request_params={"base_url": base_url, "symbols": symbols[:2], "start": start, "end": end},
            headers={"User-Agent": "vsf-source-probe/0.1", "Authorization": f"Bearer {token}"},
            auth_status="token_configured",
            terms_notes="Probe only; do not claim adjusted-price support until raw fields are observed.",
        )
