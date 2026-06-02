from __future__ import annotations

from trading_agent.source_adapters.base import AccessStatus, SourceAdapter, SourceProbeResult


class VnstockReferenceAdapter(SourceAdapter):
    source_name = "vnstock_reference"

    def probe(self, symbols: list[str], start: str, end: str, run_id: str) -> SourceProbeResult:
        try:
            from trading_agent.data_sources.vnstock_client import VnstockClient
        except Exception as exc:
            return SourceProbeResult(
                source_name=self.source_name,
                adapter_name=self.adapter_name,
                access_status=AccessStatus.NOT_CONFIGURED,
                auth_status="dependency_missing",
                endpoint_or_surface="vnstock Python library",
                datasets=["listing_all_symbols", "ohlcv", "company_events"],
                sample_symbols=symbols,
                sample_start=start,
                sample_end=end,
                likely_canonical_tables=["securities", "daily_prices", "corporate_events"],
                terms_notes="Prototype/fallback only; not canonical.",
                warnings=["vnstock_reference_not_canonical"],
                errors=[str(exc)],
                next_action="Keep as fallback/reference only; prioritize source/provider probes.",
            )

        client = VnstockClient()
        result = client.get_listing_all_symbols()
        if not result.ok or result.data is None:
            return SourceProbeResult(
                source_name=self.source_name,
                adapter_name=self.adapter_name,
                access_status=AccessStatus.ERROR,
                auth_status="library_available",
                endpoint_or_surface="vnstock listing_all_symbols",
                datasets=["listing_all_symbols"],
                sample_symbols=symbols,
                sample_start=start,
                sample_end=end,
                likely_canonical_tables=["securities", "daily_prices", "corporate_events"],
                terms_notes="Prototype/fallback only; not canonical.",
                warnings=["vnstock_reference_not_canonical"],
                errors=[result.error or "vnstock reference probe failed"],
                next_action="Do not substitute vnstock for failed canonical source probes.",
            )

        raw_paths: list[str] = []
        metadata_paths: list[str] = []
        if self.raw_store is not None:
            fetch = self.raw_store.write_payload(
                source_name=self.source_name,
                adapter_name=self.adapter_name,
                dataset="listing_all_symbols",
                endpoint_or_surface="vnstock listing_all_symbols",
                payload=result.data.head(20),
                request_params={"library": "vnstock", "method": "listing_all_symbols"},
                symbol=",".join(symbols),
                start=start,
                end=end,
                run_id=run_id,
                access_status=AccessStatus.VERIFIED.value,
                auth_mode="library_no_direct_provider_auth",
                http_status=None,
                content_type="text/csv",
                status="success",
                terms_notes="Prototype/fallback only; not canonical.",
            )
            raw_paths = [fetch.raw_path] if fetch.raw_path else []
            metadata_paths = [fetch.metadata_path] if fetch.metadata_path else []

        return SourceProbeResult(
            source_name=self.source_name,
            adapter_name=self.adapter_name,
            access_status=AccessStatus.VERIFIED,
            auth_status="library_available_not_provider_verified",
            endpoint_or_surface="vnstock listing_all_symbols",
            datasets=["listing_all_symbols"],
            sample_symbols=symbols,
            sample_start=start,
            sample_end=end,
            content_type="text/csv",
            original_fields=[str(col) for col in result.data.columns],
            row_count=len(result.data),
            raw_paths=raw_paths,
            metadata_paths=metadata_paths,
            likely_canonical_tables=["securities", "daily_prices", "corporate_events"],
            terms_notes="Prototype/fallback only; not canonical MVP source.",
            warnings=[
                "vnstock_reference_not_canonical",
                "must_not_substitute_for_failed_canonical_source_probe",
            ],
            next_action="Use only as fallback/reference; continue probing source/vendor/provider data.",
        )
