from __future__ import annotations

import os

from trading_agent.source_adapters.base import SourceAdapter, SourceProbeResult


class HoseAdapter(SourceAdapter):
    source_name = "hose"

    def probe(self, symbols: list[str], start: str, end: str, run_id: str) -> SourceProbeResult:
        url = os.getenv("HOSE_PROBE_URL", "").strip()
        if not url:
            return self._manual_only_result(
                symbols=symbols,
                start=start,
                end=end,
                endpoint_or_surface="HOSE_PROBE_URL not configured",
                datasets=["official_public_surface"],
                likely_canonical_tables=["securities", "daily_prices", "corporate_events"],
                terms_notes="Official HSX/HOSE access surface must be manually identified and terms checked before crawling.",
                next_action="Manually identify a stable HSX/HOSE page, file, or API surface and set HOSE_PROBE_URL for a tiny probe.",
            )
        return self._probe_url(
            url=url,
            dataset="official_public_surface",
            symbols=symbols,
            start=start,
            end=end,
            run_id=run_id,
            likely_canonical_tables=["securities", "daily_prices", "corporate_events"],
            request_params={"url": url, "symbols": symbols, "start": start, "end": end},
            terms_notes="Probe only; do not promote to ingestion until terms and fields are reviewed.",
        )
