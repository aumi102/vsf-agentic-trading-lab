from __future__ import annotations

import os

from trading_agent.source_adapters.base import SourceAdapter, SourceProbeResult


class SsiFastConnectAdapter(SourceAdapter):
    source_name = "ssi_fastconnect"

    def probe(self, symbols: list[str], start: str, end: str, run_id: str) -> SourceProbeResult:
        base_url = os.getenv("SSI_FASTCONNECT_BASE_URL", "").strip()
        token = os.getenv("SSI_FASTCONNECT_TOKEN", "").strip()
        datasets = ["Securities", "SecuritiesDetails", "DailyOhlc", "IntradayOhlc", "DailyIndex", "DailyStockPrice"]
        if not base_url or not token:
            return self._not_configured_result(
                symbols=symbols,
                start=start,
                end=end,
                endpoint_or_surface="SSI_FASTCONNECT_BASE_URL/SSI_FASTCONNECT_TOKEN not configured",
                datasets=datasets,
                likely_canonical_tables=["securities", "daily_prices"],
                terms_notes="Candidate paid/vendor API; use only with verified credentials and terms.",
                next_action="Configure SSI_FASTCONNECT_BASE_URL and SSI_FASTCONNECT_TOKEN, then run a tiny probe.",
            )
        url = f"{base_url.rstrip('/')}/Securities"
        return self._probe_url(
            url=url,
            dataset="Securities",
            symbols=symbols[:2],
            start=start,
            end=end,
            run_id=run_id,
            likely_canonical_tables=["securities", "daily_prices"],
            request_params={"base_url": base_url, "dataset": "Securities"},
            headers={"User-Agent": "vsf-source-probe/0.1", "Authorization": f"Bearer {token}"},
            auth_status="token_configured",
            terms_notes="Vendor API probe; confirm license before storing or redistributing data.",
        )
