from __future__ import annotations

import os

from trading_agent.source_adapters.base import SourceAdapter, SourceProbeResult


class VbmaAdapter(SourceAdapter):
    source_name = "vbma"

    def probe(self, symbols: list[str], start: str, end: str, run_id: str) -> SourceProbeResult:
        url = os.getenv("VBMA_PROBE_URL", "").strip()
        if not url:
            return self._manual_only_result(
                symbols=symbols,
                start=start,
                end=end,
                endpoint_or_surface="VBMA_PROBE_URL not configured",
                datasets=["bond_rates_context", "yield_curve_context"],
                likely_canonical_tables=["bond_auctions", "yield_curve_points"],
                terms_notes="VBMA is macro/rates context and does not block the equity MVP.",
                next_action="Manually inspect VBMA download/API surfaces before configuring a tiny probe.",
            )
        return self._probe_url(
            url=url,
            dataset="vbma_rates_probe",
            symbols=symbols[:2],
            start=start,
            end=end,
            run_id=run_id,
            likely_canonical_tables=["bond_auctions", "yield_curve_points"],
            request_params={"url": url, "start": start, "end": end},
            terms_notes="Macro/rates context only; not primary equity OHLCV.",
        )
