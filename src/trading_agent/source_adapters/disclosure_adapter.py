from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


BRONZE_SCHEMA_VERSION = "official_disclosure_bronze_v1"
BRONZE_PARSER_VERSION = "official_disclosure_parser_v1"

_REQUIRED_FIELDS: frozenset[str] = frozenset({
    "source_family",
    "exchange",
    "disclosure_id",
    "crawled_at",
    "schema_version",
    "parser_version",
})


class DisclosurePitStatus(str, Enum):
    CANONICAL_TIMESTAMP_AVAILABLE = "canonical_timestamp_available"
    DATE_ONLY_AVAILABLE = "date_only_available"
    OFFICIAL_TIMESTAMP_MISSING = "official_timestamp_missing"
    NON_CANONICAL = "non_canonical"
    NOT_APPLICABLE = "not_applicable"
    BLOCKED = "blocked"


class DisclosureQualityStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


_BLOCKED_ACCESS_STATUSES: frozenset[str] = frozenset({
    "blocked",
    "auth_required",
    "rejected_response",
    "not_configured",
    "error",
    "js_app_shell",
})


@dataclass(frozen=True)
class DisclosureTarget:
    source_family: str
    exchange: str
    official_domain: str
    adapter_name: str
    dataset: str
    symbol: str = ""
    url: str = ""
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    request_params: dict[str, Any] = field(default_factory=dict)
    terms_notes: str = ""
    ssl_verify: bool = True

    @property
    def is_configured(self) -> bool:
        return bool(self.url.strip())


@dataclass
class DisclosureRecord:
    source_family: str
    exchange: str
    official_domain: str
    adapter_name: str
    disclosure_id: str
    symbol: str
    issuer_name: str
    document_category: str
    title: str
    published_at: str
    published_date: str
    effective_at: str
    page_url: str
    document_url: str
    attachment_name: str
    attachment_type: str
    language: str
    crawled_at: str
    raw_path: str
    metadata_path: str
    body_sha256: str
    parser_version: str
    schema_version: str
    quality_status: str
    pit_status: str
    warning_codes: list[str]
    error_codes: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def assign_pit_status(
    *,
    published_at: str,
    published_date: str,
    access_status: str,
) -> str:
    if access_status in _BLOCKED_ACCESS_STATUSES:
        return DisclosurePitStatus.BLOCKED.value
    if published_at:
        return DisclosurePitStatus.CANONICAL_TIMESTAMP_AVAILABLE.value
    if published_date:
        return DisclosurePitStatus.DATE_ONLY_AVAILABLE.value
    return DisclosurePitStatus.OFFICIAL_TIMESTAMP_MISSING.value


def check_disclosure_quality(record: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    """Returns (quality_status, warning_codes, error_codes)."""
    warnings: list[str] = []
    errors: list[str] = []

    for fname in sorted(_REQUIRED_FIELDS):
        val = record.get(fname)
        if val is None or (isinstance(val, str) and not val.strip()):
            errors.append(f"missing_{fname}")

    existing_errors = record.get("error_codes") or []
    if isinstance(existing_errors, list):
        errors.extend(existing_errors)

    if not record.get("published_date") and not record.get("published_at"):
        warnings.append("publication_date_unknown")
    if not record.get("title"):
        warnings.append("title_missing")
    if not record.get("symbol"):
        warnings.append("symbol_not_resolved")

    if errors:
        return DisclosureQualityStatus.FAIL.value, warnings, errors
    if warnings:
        return DisclosureQualityStatus.WARN.value, warnings, []
    return DisclosureQualityStatus.PASS.value, [], []
