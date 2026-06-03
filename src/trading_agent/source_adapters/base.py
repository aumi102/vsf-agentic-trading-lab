from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import os
import ssl
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class AccessStatus(str, Enum):
    VERIFIED = "verified"
    REJECTED_RESPONSE = "rejected_response"
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
    target_name: str = ""
    config_file: str = ""
    target_skipped_reason: str = ""
    auth_env_missing: str = ""
    auth_in: str = ""
    auth_param: str = ""
    verify_ssl: bool = True

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["access_status"] = self.access_status.value
        return data


class SourceAdapter:
    source_name: str = "unknown"

    def __init__(self, raw_store: Any | None = None, probe_targets: list[Any] | None = None) -> None:
        self.raw_store = raw_store
        self.probe_targets = probe_targets or []

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

    def probe_configured_targets(self, targets: list[Any], symbols: list[str], start: str, end: str, run_id: str) -> list[SourceProbeResult]:
        return [self._probe_configured_target(target, symbols=symbols, start=start, end=end, run_id=run_id) for target in targets]

    def _probe_configured_target(self, target: Any, *, symbols: list[str], start: str, end: str, run_id: str) -> SourceProbeResult:
        url = str(getattr(target, "url", "") or "").strip()
        target_name = str(getattr(target, "name", "") or "")
        dataset = str(getattr(target, "dataset", "") or target_name or "configured_target")
        likely_tables = list(getattr(target, "likely_canonical_tables", []) or [])
        terms_notes = str(getattr(target, "terms_notes", "") or "")
        config_file = str(getattr(target, "config_file", "") or "")
        method = str(getattr(target, "method", "GET") or "GET").upper()

        if method not in {"GET", "POST"}:
            return self._configured_target_not_run(
                target=target,
                symbols=symbols,
                start=start,
                end=end,
                access_status=AccessStatus.NOT_CONFIGURED,
                auth_status="unsupported_method",
                reason=f"unsupported_method:{method}",
                next_action="Only GET and POST source probes are supported for now.",
            )
        body_json = getattr(target, "body_json", None)
        if method == "POST" and body_json is not None and not isinstance(body_json, dict):
            return self._configured_target_not_run(
                target=target,
                symbols=symbols,
                start=start,
                end=end,
                access_status=AccessStatus.NOT_CONFIGURED,
                auth_status="invalid_body_json",
                reason="invalid_body_json",
                next_action="Set body_json to an object for POST probes.",
            )

        lower_url = url.lower()
        if not url or "example.com" in lower_url or "replace-with" in lower_url:
            return self._configured_target_not_run(
                target=target,
                symbols=symbols,
                start=start,
                end=end,
                access_status=AccessStatus.NOT_CONFIGURED,
                auth_status="placeholder_or_missing_url",
                reason="placeholder_url",
                next_action="Replace placeholder URL with a real candidate endpoint before probing.",
            )

        auth_env = str(getattr(target, "auth_env", "") or "").strip()
        auth_in = str(getattr(target, "auth_in", "") or "header").strip() or "header"
        auth_param = str(getattr(target, "auth_param", "") or "").strip()
        verify_ssl = bool(getattr(target, "verify_ssl", True))
        headers = {"User-Agent": "vsf-source-probe/0.1"}
        headers.update({str(key): str(value) for key, value in dict(getattr(target, "headers", {}) or {}).items()})
        if auth_env:
            token = os.getenv(auth_env, "").strip()
            if not token:
                return self._configured_target_not_run(
                    target=target,
                    symbols=symbols,
                    start=start,
                    end=end,
                    access_status=AccessStatus.NOT_CONFIGURED,
                    auth_status="missing_auth_env",
                    reason="auth_env_missing",
                    next_action=f"Set {auth_env} in the environment before probing this target.",
                    auth_env_missing=auth_env,
                )
            if auth_in == "query":
                if not auth_param:
                    return self._configured_target_not_run(
                        target=target,
                        symbols=symbols,
                        start=start,
                        end=end,
                        access_status=AccessStatus.NOT_CONFIGURED,
                        auth_status="missing_auth_param",
                        reason="auth_param_missing",
                        next_action="Set auth_param for query-param authentication.",
                    )
                url = _append_query_param(url, auth_param, token)
            else:
                auth_header = str(getattr(target, "auth_header", "") or "Authorization")
                auth_prefix = str(getattr(target, "auth_prefix", "") or "")
                headers[auth_header] = f"{auth_prefix}{token}"

        request_params = dict(getattr(target, "request_params", {}) or {})
        request_params.update({"target_name": target_name, "config_file": config_file})
        request_params["method"] = method
        request_params["verify_ssl"] = verify_ssl
        body_bytes = None
        if method == "POST":
            body_json = body_json if body_json is not None else {}
            body_bytes = json.dumps(body_json, ensure_ascii=False).encode("utf-8")
            request_params["body_present"] = True
            request_params["body_size_bytes"] = len(body_bytes)
            request_params["body_json_keys"] = sorted(str(key) for key in body_json.keys())
            sensitive_body_keys = sorted(str(key) for key in body_json if _is_sensitive_key(str(key)))
            if sensitive_body_keys:
                request_params["body_json_sensitive_keys_redacted"] = sensitive_body_keys
            headers.setdefault("Content-Type", "application/json")
        else:
            request_params["body_present"] = False
            request_params["body_size_bytes"] = 0
        request_params["header_names"] = sorted(headers.keys())
        response_validation = {
            "expected_content_type_contains": list(getattr(target, "expected_content_type_contains", []) or []),
            "expected_body_startswith_json": bool(getattr(target, "expected_body_startswith_json", False)),
            "reject_body_contains": list(getattr(target, "reject_body_contains", []) or []),
            "min_body_bytes": int(getattr(target, "min_body_bytes", 0) or 0),
        }
        if any(response_validation.values()):
            request_params["response_validation"] = response_validation
        if auth_env:
            request_params["auth_env"] = auth_env
            request_params["auth_in"] = auth_in
            if auth_param:
                request_params["auth_param"] = auth_param

        return self._probe_url(
            url=url,
            dataset=dataset,
            symbols=symbols,
            start=start,
            end=end,
            run_id=run_id,
            likely_canonical_tables=likely_tables,
            request_params=request_params,
            headers=headers or None,
            method=method,
            body_bytes=body_bytes,
            verify_ssl=verify_ssl,
            auth_status="configured_target",
            terms_notes=terms_notes,
            target_name=target_name,
            config_file=config_file,
            auth_in=auth_in if auth_env else "",
            auth_param=auth_param if auth_env else "",
            response_validation=response_validation,
        )

    def _configured_target_not_run(
        self,
        *,
        target: Any,
        symbols: list[str],
        start: str,
        end: str,
        access_status: AccessStatus,
        auth_status: str,
        reason: str,
        next_action: str,
        auth_env_missing: str = "",
    ) -> SourceProbeResult:
        return SourceProbeResult(
            source_name=self.source_name,
            adapter_name=self.adapter_name,
            access_status=access_status,
            auth_status=auth_status,
            endpoint_or_surface=str(getattr(target, "url", "") or "configured target"),
            datasets=[str(getattr(target, "dataset", "") or "configured_target")],
            sample_symbols=symbols,
            sample_start=start,
            sample_end=end,
            likely_canonical_tables=list(getattr(target, "likely_canonical_tables", []) or []),
            terms_notes=str(getattr(target, "terms_notes", "") or ""),
            warnings=[reason],
            next_action=next_action,
            target_name=str(getattr(target, "name", "") or ""),
            config_file=str(getattr(target, "config_file", "") or ""),
            target_skipped_reason=reason,
            auth_env_missing=auth_env_missing,
            auth_in=str(getattr(target, "auth_in", "") or ""),
            auth_param=str(getattr(target, "auth_param", "") or ""),
            verify_ssl=bool(getattr(target, "verify_ssl", True)),
        )

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
        method: str = "GET",
        body_bytes: bytes | None = None,
        verify_ssl: bool = True,
        auth_status: str = "configured",
        terms_notes: str = "",
        target_name: str = "",
        config_file: str = "",
        auth_in: str = "",
        auth_param: str = "",
        response_validation: dict[str, Any] | None = None,
    ) -> SourceProbeResult:
        request = Request(
            url,
            data=body_bytes,
            headers=headers or {"User-Agent": "vsf-source-probe/0.1"},
            method=method,
        )
        ssl_context = None if verify_ssl else ssl._create_unverified_context()
        try:
            with urlopen(request, timeout=10, context=ssl_context) as response:
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
                endpoint_or_surface=_redact_sensitive_url(url),
                datasets=[dataset],
                sample_symbols=symbols,
                sample_start=start,
                sample_end=end,
                http_status=exc.code,
                terms_notes=terms_notes,
                errors=[str(exc)],
                next_action="Verify credentials, access rights, and provider terms.",
                target_name=target_name,
                config_file=config_file,
                auth_in=auth_in,
                auth_param=auth_param,
                verify_ssl=verify_ssl,
            )
        except (TimeoutError, URLError, OSError) as exc:
            return SourceProbeResult(
                source_name=self.source_name,
                adapter_name=self.adapter_name,
                access_status=AccessStatus.ERROR,
                auth_status=auth_status,
                endpoint_or_surface=_redact_sensitive_url(url),
                datasets=[dataset],
                sample_symbols=symbols,
                sample_start=start,
                sample_end=end,
                terms_notes=terms_notes,
                errors=[str(exc)],
                next_action="Retry manually and verify the endpoint/configuration.",
                target_name=target_name,
                config_file=config_file,
                auth_in=auth_in,
                auth_param=auth_param,
                verify_ssl=verify_ssl,
            )

        validation_reasons = _validate_response_payload(
            payload=payload,
            content_type=content_type,
            validation=response_validation or {},
        )
        access_status = AccessStatus.REJECTED_RESPONSE if validation_reasons else AccessStatus.VERIFIED
        stored_status = access_status.value if validation_reasons else "success"
        error_text = ";".join(validation_reasons) if validation_reasons else None

        raw_paths: list[str] = []
        metadata_paths: list[str] = []
        original_fields: list[str] = []
        row_count = 0
        if self.raw_store is not None:
            fetch = self.raw_store.write_payload(
                source_name=self.source_name,
                adapter_name=self.adapter_name,
                dataset=dataset,
                endpoint_or_surface=_redact_sensitive_url(url),
                payload=payload,
                request_params=request_params or {"url": url},
                symbol=",".join(symbols),
                start=start,
                end=end,
                run_id=run_id,
                access_status=access_status.value,
                auth_mode=auth_status,
                http_status=http_status,
                content_type=content_type,
                status=stored_status,
                terms_notes=terms_notes,
                error=error_text,
            )
            raw_paths = [fetch.raw_path] if fetch.raw_path else []
            metadata_paths = [fetch.metadata_path] if fetch.metadata_path else []
            original_fields = fetch.original_fields
            row_count = fetch.row_count

        return SourceProbeResult(
            source_name=self.source_name,
            adapter_name=self.adapter_name,
            access_status=access_status,
            auth_status=auth_status,
            endpoint_or_surface=_redact_sensitive_url(url),
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
            warnings=validation_reasons or ["raw_sample_captured_but_schema_not_promoted"],
            errors=validation_reasons,
            next_action=(
                "Fix request headers/cookies or endpoint until response validation passes."
                if validation_reasons
                else "Inspect raw sample fields before promoting this source to ingestion."
            ),
            target_name=target_name,
            config_file=config_file,
            auth_in=auth_in,
            auth_param=auth_param,
            verify_ssl=verify_ssl,
        )


def _append_query_param(url: str, key: str, value: str) -> str:
    parts = urlsplit(url)
    query_items = parse_qsl(parts.query, keep_blank_values=True)
    query_items = [(existing_key, existing_value) for existing_key, existing_value in query_items if existing_key != key]
    query_items.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query_items), parts.fragment))


def _redact_url_query_param(url: str, key: str) -> str:
    parts = urlsplit(url)
    query_items = []
    for existing_key, existing_value in parse_qsl(parts.query, keep_blank_values=True):
        if existing_key == key:
            query_items.append((existing_key, "<redacted>"))
        else:
            query_items.append((existing_key, existing_value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query_items), parts.fragment))


def _redact_sensitive_url(url: str) -> str:
    parts = urlsplit(url)
    query_items = []
    for existing_key, existing_value in parse_qsl(parts.query, keep_blank_values=True):
        if _is_sensitive_key(existing_key):
            query_items.append((existing_key, "<redacted>"))
        else:
            query_items.append((existing_key, existing_value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query_items), parts.fragment))


def _is_sensitive_key(key: str) -> bool:
    return any(token in key.lower() for token in ("api_key", "token", "secret", "password", "auth", "key", "cookie"))


def _validate_response_payload(*, payload: bytes, content_type: str, validation: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    expected_content_types = [str(value).lower() for value in validation.get("expected_content_type_contains", []) if str(value)]
    lower_content_type = (content_type or "").lower()
    for expected in expected_content_types:
        if expected not in lower_content_type:
            reasons.append(f"response_content_type_missing:{expected}")

    if validation.get("expected_body_startswith_json"):
        stripped = payload.lstrip()
        if not (stripped.startswith(b"{") or stripped.startswith(b"[")):
            reasons.append("response_body_not_json")

    min_body_bytes = int(validation.get("min_body_bytes", 0) or 0)
    if min_body_bytes and len(payload) < min_body_bytes:
        reasons.append(f"response_body_too_small:{len(payload)}<{min_body_bytes}")

    body_text = payload.decode("utf-8", errors="replace").lower()
    for marker in validation.get("reject_body_contains", []) or []:
        marker_text = str(marker)
        if marker_text and marker_text.lower() in body_text:
            reasons.append(f"response_body_contains_rejected_marker:{marker_text}")
    return reasons
