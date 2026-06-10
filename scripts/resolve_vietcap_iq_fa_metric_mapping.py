"""
Offline Option C mapping resolver for Vietcap IQ FA metric codes.

Implements the hybrid gated mapping lookup order described in:
  docs/data_sources/vietcap_iq_fa_mapping_integration_strategy.md §6.2–6.3

Lookup priority:
  1. Per-symbol (firm-type-specific) primary mapping
  2. Union consensus fallback (conflict-free, section-matched codes only)
  3. conflict_skipped / not_covered / no_mapping_available

This module is pure offline logic:
  - No network calls.
  - No DB writes.
  - No parser code changes.
  - Never touches or emits the legacy `line_item_name` column.

Design reference:
  docs/data_sources/vietcap_iq_fa_mapping_integration_strategy.md
  docs/data_sources/vietcap_iq_fa_firm_type_determination.md
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_MAPPING_STATUSES: frozenset[str] = frozenset({
    "primary",
    "consensus_fallback",
    "conflict_skipped",
    "not_covered",
    "no_mapping_available",
    "section_mismatch",
})

# Output columns produced by the resolver (never includes legacy line_item_name)
MAPPING_RESULT_COLUMNS: list[str] = [
    "line_item_name_en",
    "line_item_name_vi",
    "mapping_status",
    "mapping_source_symbol",
    "mapping_source_run_id",
    "mapping_conflict",
    "mapping_group",
]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MappingResult:
    """Immutable result of resolving one (section, line_item_code) pair."""

    line_item_name_en: str = ""
    line_item_name_vi: str = ""
    mapping_status: str = "not_covered"
    mapping_source_symbol: str = ""
    mapping_source_run_id: str = ""
    mapping_conflict: str = "false"
    mapping_group: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "line_item_name_en": self.line_item_name_en,
            "line_item_name_vi": self.line_item_name_vi,
            "mapping_status": self.mapping_status,
            "mapping_source_symbol": self.mapping_source_symbol,
            "mapping_source_run_id": self.mapping_source_run_id,
            "mapping_conflict": self.mapping_conflict,
            "mapping_group": self.mapping_group,
        }


# ---------------------------------------------------------------------------
# CSV loaders
# ---------------------------------------------------------------------------


def load_primary_mapping(path: Path) -> list[dict]:
    """Load a per-symbol primary mapping CSV (_MAPPING_COLUMNS schema).

    Skips rows with an empty line_item_code (section-level display headers).
    Expected columns: section, line_item_code, line_item_name_en,
                      line_item_name_vi, level, parent.
    """
    rows: list[dict] = []
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            code = row.get("line_item_code", "").strip()
            if not code:
                continue
            rows.append(row)
    return rows


def load_union_mapping(path: Path) -> list[dict]:
    """Load a union mapping CSV (_UNION_COLUMNS schema).

    Returns all rows including conflicting ones so the resolver can flag them.
    Expected columns: section, line_item_code, line_item_name_en_consensus,
                      conflict, sources, names_per_source, level, parent.
    """
    rows: list[dict] = []
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            code = row.get("line_item_code", "").strip()
            if not code:
                continue
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


class MappingResolver:
    """Option C hybrid gated mapping resolver.

    Construction:
      primary_rows  -- rows from load_primary_mapping(); None or [] if unavailable.
      union_rows    -- rows from load_union_mapping().
      primary_source_symbol -- symbol whose mapping payload was used (e.g. 'VCI').
      primary_source_run_id -- run_id of the mapping probe (e.g. '20260610T025420Z').
      mapping_group -- firm-type group: 'securities' / 'bank' / 'insurance' / 'general'.
      has_primary   -- False for 'general' firms where no primary mapping is expected.
                       True means primary should exist; if primary_rows is empty, all
                       results will be no_mapping_available.

    The legacy `line_item_name` column is never read, set, or returned.
    """

    def __init__(
        self,
        primary_rows: list[dict] | None,
        union_rows: list[dict],
        primary_source_symbol: str,
        primary_source_run_id: str,
        mapping_group: str,
        has_primary: bool = True,
    ) -> None:
        self._group = mapping_group
        self._primary_symbol = primary_source_symbol
        self._primary_run_id = primary_source_run_id
        self._has_primary = has_primary

        # Primary index: code → row  (each code appears in exactly one section)
        self._primary: dict[str, dict] = {}
        if has_primary and primary_rows:
            for row in primary_rows:
                code = row.get("line_item_code", "").strip()
                if code:
                    self._primary[code] = row

        # Union indexes
        # _union_all: code → row (all codes, including conflicting)
        # _union_clean: (section, code) → row (non-conflicting only, for fast lookup)
        self._union_all: dict[str, dict] = {}
        self._union_clean: dict[tuple[str, str], dict] = {}
        for row in union_rows:
            code = row.get("line_item_code", "").strip()
            section = row.get("section", "").strip()
            if not code:
                continue
            self._union_all[code] = row
            if row.get("conflict", "false") == "false":
                self._union_clean[(section, code)] = row

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def resolve(self, section: str, line_item_code: str) -> MappingResult:
        """Resolve mapping for one (section, line_item_code) pair."""
        code = line_item_code.strip()
        sec = section.strip()

        # Firm type has no primary mapping (general); skip directly to union
        if not self._has_primary:
            return self._union_resolve(sec, code)

        # Primary mapping expected but nothing was loaded
        if not self._primary:
            return MappingResult(
                mapping_status="no_mapping_available",
                mapping_group=self._group,
                mapping_conflict="false",
            )

        # Primary lookup
        prow = self._primary.get(code)
        if prow is not None:
            p_section = prow.get("section", "").strip()
            if p_section == sec:
                return MappingResult(
                    line_item_name_en=prow.get("line_item_name_en", ""),
                    line_item_name_vi=prow.get("line_item_name_vi", ""),
                    mapping_status="primary",
                    mapping_source_symbol=self._primary_symbol,
                    mapping_source_run_id=self._primary_run_id,
                    mapping_conflict="false",
                    mapping_group=self._group,
                )
            # Code is in primary but under a different section
            return MappingResult(
                mapping_status="section_mismatch",
                mapping_group=self._group,
                mapping_conflict="false",
            )

        # Primary miss → union fallback
        return self._union_resolve(sec, code)

    def resolve_many(self, rows: Sequence[dict]) -> list[dict]:
        """Resolve mapping for a sequence of fact rows.

        Each input row must contain 'section' and 'line_item_code' keys.
        Returns new dicts with mapping result fields merged in, in input order.
        The legacy 'line_item_name' key in input rows is passed through unchanged.
        """
        result: list[dict] = []
        for row in rows:
            mapping = self.resolve(row["section"], row["line_item_code"])
            merged = dict(row)
            merged.update(mapping.as_dict())
            result.append(merged)
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _union_resolve(self, section: str, code: str) -> MappingResult:
        """Union consensus fallback resolution."""
        urow = self._union_all.get(code)
        if urow is None:
            return MappingResult(
                mapping_status="not_covered",
                mapping_group=self._group,
                mapping_conflict="false",
            )
        if urow.get("conflict", "false") == "true":
            return MappingResult(
                mapping_status="conflict_skipped",
                mapping_group=self._group,
                mapping_conflict="true",
            )
        # Non-conflicting — check section match
        u_section = urow.get("section", "").strip()
        if u_section != section:
            return MappingResult(
                mapping_status="section_mismatch",
                mapping_group=self._group,
                mapping_conflict="false",
            )
        return MappingResult(
            line_item_name_en=urow.get("line_item_name_en_consensus", ""),
            line_item_name_vi="",  # union CSV has no per-code VI name
            mapping_status="consensus_fallback",
            mapping_source_symbol="union",
            mapping_source_run_id="",
            mapping_conflict="false",
            mapping_group=self._group,
        )


# ---------------------------------------------------------------------------
# Convenience constructors
# ---------------------------------------------------------------------------


def build_resolver(
    primary_path: Path | None,
    union_path: Path,
    primary_source_symbol: str,
    primary_source_run_id: str,
    mapping_group: str,
) -> MappingResolver:
    """Build a MappingResolver from CSV file paths.

    Pass primary_path=None to create a general-firm resolver (has_primary=False).
    """
    union_rows = load_union_mapping(union_path)
    if primary_path is None:
        return MappingResolver(
            primary_rows=None,
            union_rows=union_rows,
            primary_source_symbol=primary_source_symbol,
            primary_source_run_id=primary_source_run_id,
            mapping_group=mapping_group,
            has_primary=False,
        )
    primary_rows = load_primary_mapping(primary_path)
    return MappingResolver(
        primary_rows=primary_rows,
        union_rows=union_rows,
        primary_source_symbol=primary_source_symbol,
        primary_source_run_id=primary_source_run_id,
        mapping_group=mapping_group,
        has_primary=True,
    )
