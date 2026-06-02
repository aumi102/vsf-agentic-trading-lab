from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class AccessStatus(str, Enum):
    VERIFIED = "verified"
    AUTH_REQUIRED = "auth_required"
    MANUAL_ONLY = "manual_only"
    BLOCKED = "blocked"
    NOT_CONFIGURED = "not_configured"
    UNKNOWN = "unknown"
    ERROR = "error"


@dataclass
class SourceFetchResult:
    dataset: str
    status: str
    payload: Any = None
    parsed_rows: Any = None
    raw_path: str | None = None
    metadata_path: str | None = None
    original_fields: list[str] = field(default_factory=list)
    row_count: int = 0
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceProbeResult:
    source_name: str
    adapter_name: str
    access_status: AccessStatus
    auth_status: str
    endpoint_or_surface: str
    datasets: list[str] = field(default_factory=list)
    sample_symbols: list[str] = field(default_factory=list)
    sample_start: str = ""
    sample_end: str = ""
    http_status: int | None = None
    content_type: str = ""
    original_fields: list[str] = field(default_factory=list)
    row_count: int = 0
    raw_paths: list[str] = field(default_factory=list)
    metadata_paths: list[str] = field(default_factory=list)
    likely_canonical_tables: list[str] = field(default_factory=list)
    terms_notes: str = ""
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    next_action: str = ""
    probed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["access_status"] = self.access_status.value
        return data


class SourceAdapter:
    source_name: str = "unknown"

    def __init__(self, raw_store: Any | None = None) -> None:
        self.raw_store = raw_store

    @property
    def adapter_name(self) -> str:
        return self.__class__.__name__

    def probe(self, symbols: list[str], start: str, end: str, run_id: str) -> SourceProbeResult:
        return self._not_configured_result(
            symbols=symbols,
            start=start,
            end=end,
            endpoint_or_surface="not configured",
            datasets=[],
            next_action="Configure this adapter before probing.",
        )

    def fetch_symbols(self, *args: Any, **kwargs: Any) -> SourceFetchResult:
        return SourceFetchResult(dataset="symbols", status=AccessStatus.NOT_CONFIGURED.value, error="Not implemented for source probe task.")

    def fetch_daily_ohlcv(self, symbol: str, start: str, end: str) -> SourceFetchResult:
        return SourceFetchResult(dataset="daily_ohlcv", status=AccessStatus.NOT_CONFIGURED.value, error="Not implemented for source probe task.")

    def fetch_corporate_actions(self, symbol: str) -> SourceFetchResult:
        return SourceFetchResult(dataset="corporate_actions", status=AccessStatus.NOT_CONFIGURED.value, error="Not implemented for source probe task.")

    def fetch_reports(self, symbol: str) -> SourceFetchResult:
        return SourceFetchResult(dataset="reports", status=AccessStatus.NOT_CONFIGURED.value, error="Not implemented for source probe task.")

    def _not_configured_result(
        self,
        symbols: list[str],
        start: str,
        end: str,
        endpoint_or_surface: str,
        datasets: list[str],
        next_action: str,
        likely_canonical_tables: list[str] | None = None,
        terms_notes: str = "",
        auth_status: str = "missing_config",
    ) -> SourceProbeResult:
        return SourceProbeResult(
            source_name=self.source_name,
            adapter_name=self.adapter_name,
            access_status=AccessStatus.NOT_CONFIGURED,
            auth_status=auth_status,
            endpoint_or_surface=endpoint_or_surface,
            datasets=datasets,
            sample_symbols=symbols,
            sample_start=start,
            sample_end=end,
            likely_canonical_tables=likely_canonical_tables or [],
            terms_notes=terms_notes,
            warnings=["probe_not_run_without_config"],
            next_action=next_action,
        )

    def _manual_only_result(
        self,
        symbols: list[str],
        start: str,
        end: str,
        endpoint_or_surface: str,
        datasets: list[str],
        next_action: str,
        likely_canonical_tables: list[str] | None = None,
        terms_notes: str = "",
    ) -> SourceProbeResult:
        return SourceProbeResult(
            source_name=self.source_name,
            adapter_name=self.adapter_name,
            access_status=AccessStatus.MANUAL_ONLY,
            auth_status="manual_or_unknown",
            endpoint_or_surface=endpoint_or_surface,
            datasets=datasets,
            sample_symbols=symbols,
            sample_start=start,
            sample_end=end,
            likely_canonical_tables=likely_canonical_tables or [],
            terms_notes=terms_notes,
            warnings=["manual_probe_required"],
            next_action=next_action,
        )

    def _probe_url(
        self,
        *,
        url: str,
        dataset: str,
        symbols: list[str],
        start: str,
        end: str,
        run_id: str,
        likely_canonical_tables: list[str],
        request_params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        auth_status: str = "configured",
        terms_notes: str = "",
    ) -> SourceProbeResult:
        request = Request(url, headers=headers or {"User-Agent": "vsf-source-probe/0.1"})
        try:
            with urlopen(request, timeout=10) as response:
                payload = response.read()
                http_status = getattr(response, "status", None)
                content_type = response.headers.get("content-type", "")
        except HTTPError as exc:
            status = AccessStatus.AUTH_REQUIRED if exc.code in {401, 403} else AccessStatus.BLOCKED
            return SourceProbeResult(
                source_name=self.source_name,
                adapter_name=self.adapter_name,
                access_status=status,
                auth_status="auth_or_access_failed",
                endpoint_or_surface=url,
                datasets=[dataset],
                sample_symbols=symbols,
                sample_start=start,
                sample_end=end,
                http_status=exc.code,
                terms_notes=terms_notes,
                errors=[str(exc)],
                next_action="Verify credentials, access rights, and provider terms.",
            )
        except (TimeoutError, URLError, OSError) as exc:
            return SourceProbeResult(
                source_name=self.source_name,
                adapter_name=self.adapter_name,
                access_status=AccessStatus.ERROR,
                auth_status=auth_status,
                endpoint_or_surface=url,
                datasets=[dataset],
                sample_symbols=symbols,
                sample_start=start,
                sample_end=end,
                terms_notes=terms_notes,
                errors=[str(exc)],
                next_action="Retry manually and verify the endpoint/configuration.",
            )

        raw_paths: list[str] = []
        metadata_paths: list[str] = []
        original_fields: list[str] = []
        row_count = 0
        if self.raw_store is not None:
            fetch = self.raw_store.write_payload(
                source_name=self.source_name,
                adapter_name=self.adapter_name,
                dataset=dataset,
                endpoint_or_surface=url,
                payload=payload,
                request_params=request_params or {"url": url},
                symbol=",".join(symbols),
                start=start,
                end=end,
                run_id=run_id,
                access_status=AccessStatus.VERIFIED.value,
                auth_mode=auth_status,
                http_status=http_status,
                content_type=content_type,
                status="success",
                terms_notes=terms_notes,
            )
            raw_paths = [fetch.raw_path] if fetch.raw_path else []
            metadata_paths = [fetch.metadata_path] if fetch.metadata_path else []
            original_fields = fetch.original_fields
            row_count = fetch.row_count

        return SourceProbeResult(
            source_name=self.source_name,
            adapter_name=self.adapter_name,
            access_status=AccessStatus.VERIFIED,
            auth_status=auth_status,
            endpoint_or_surface=url,
            datasets=[dataset],
            sample_symbols=symbols,
            sample_start=start,
            sample_end=end,
            http_status=http_status,
            content_type=content_type,
            original_fields=original_fields,
            row_count=row_count,
            raw_paths=raw_paths,
            metadata_paths=metadata_paths,
            likely_canonical_tables=likely_canonical_tables,
            terms_notes=terms_notes,
            warnings=["raw_sample_captured_but_schema_not_promoted"],
            next_action="Inspect raw sample fields before promoting this source to ingestion.",
        )
