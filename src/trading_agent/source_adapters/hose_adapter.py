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
                datasets=["universe_stocks", "daily_ohlcv", "order_book_or_price_board", "corporate_actions", "index_data", "trading_calendar"],
                likely_canonical_tables=[
                    "securities",
                    "daily_prices",
                    "order_book_snapshots",
                    "realtime_quote_snapshots",
                    "corporate_events",
                    "index_prices",
                    "trading_calendar",
                ],
                terms_notes="Official HSX/HOSE access surface must be manually identified and terms checked before crawling.",
                next_action="Manually identify stable HSX/HOSE surfaces for universe, OHLCV, price board/order book, actions, indexes, and calendar.",
            )
        return self._probe_url(
            url=url,
            dataset="hose_official_market_data_probe",
            symbols=symbols,
            start=start,
            end=end,
            run_id=run_id,
            likely_canonical_tables=[
                "securities",
                "daily_prices",
                "order_book_snapshots",
                "realtime_quote_snapshots",
                "corporate_events",
                "index_prices",
                "trading_calendar",
            ],
            request_params={"url": url, "symbols": symbols, "start": start, "end": end},
            terms_notes="Probe only; do not promote to ingestion until terms and fields are reviewed.",
        )
