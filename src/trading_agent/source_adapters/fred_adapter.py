from __future__ import annotations

import os

from trading_agent.source_adapters.base import SourceAdapter, SourceProbeResult


class FredAdapter(SourceAdapter):
    source_name = "fred"

    def probe(self, symbols: list[str], start: str, end: str, run_id: str) -> SourceProbeResult:
        api_key = os.getenv("FRED_API_KEY", "").strip()
        if not api_key:
            return self._not_configured_result(
                symbols=symbols,
                start=start,
                end=end,
                endpoint_or_surface="FRED_API_KEY not configured",
                datasets=["macro_series", "macro_observations"],
                likely_canonical_tables=["macro_series", "macro_observations", "macro_features"],
                terms_notes="FRED is global macro context and does not block equity OHLCV.",
                next_action="Configure FRED_API_KEY to probe tiny observations for DGS10, DGS2, T10Y2Y, FEDFUNDS, CPIAUCSL, or UNRATE.",
                auth_status="missing_api_key",
            )
        url = (
            "https://api.stlouisfed.org/fred/series/observations"
            f"?series_id=DGS10&api_key={api_key}&file_type=json&observation_start={start}&observation_end={end}&limit=5"
        )
        return self._probe_url(
            url=url,
            dataset="fred_observations",
            symbols=["DGS10"],
            start=start,
            end=end,
            run_id=run_id,
            likely_canonical_tables=["macro_series", "macro_observations", "macro_features"],
            request_params={"series_id": "DGS10", "observation_start": start, "observation_end": end, "auth_env": "FRED_API_KEY", "auth_in": "query", "auth_param": "api_key"},
            auth_status="api_key_configured",
            auth_in="query",
            auth_param="api_key",
            terms_notes="FRED macro context only; preserve release/observation timing for point-in-time joins.",
        )
