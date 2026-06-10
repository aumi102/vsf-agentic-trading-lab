# Vietcap IQ FA Mapping Resolver — Tests

## Status

| Item | State |
|------|-------|
| Resolver implemented | **Done** — `scripts/resolve_vietcap_iq_fa_metric_mapping.py` |
| Resolver tests | **Done** — `tests/test_resolve_vietcap_iq_fa_metric_mapping.py` (74 tests) |
| Parser integration | **Done** — resolver wired; 65 new integration tests; 5-payload dry-run: 53,013 rows, 0 errors |
| Current parser output | Updated — `line_item_name_en`, `line_item_name_vi`, `mapping_status`, `mapping_source_symbol`, `mapping_source_run_id`, `mapping_conflict`, `mapping_group` added |
| DB writes | Blocked — not in scope |
| Backtests | Blocked — not in scope |

## What was implemented

`scripts/resolve_vietcap_iq_fa_metric_mapping.py` is a pure offline Option C hybrid
gated mapping resolver. It has no network calls, no DB clients, and no parser changes.

**Resolution order (Option C):**

1. Per-symbol primary mapping (firm-type-specific CSV) — status `primary`
2. Union consensus fallback (conflict-free, section-matched only) — status `consensus_fallback`
3. Conflict-flagged union codes — status `conflict_skipped`
4. Codes absent from both — status `not_covered`
5. Firm type has a primary mapping expected but none loaded — status `no_mapping_available`
6. Code found but section does not match — status `section_mismatch`

**Key design invariants:**

- `line_item_name` (legacy empty column in parser output) is never read, set, or returned.
- `has_primary=False` (general firms) uses union-only resolution; failure → `not_covered`,
  not `no_mapping_available`.
- `has_primary=True` with empty primary rows → ALL codes get `no_mapping_available`.
- Union CSV has no per-code Vietnamese names; `line_item_name_vi=""` for `consensus_fallback`.
- Primary index is keyed by code (each code appears in exactly one section); section is
  checked after lookup.
- `mapping_source_symbol="union"` for consensus fallback; `mapping_source_run_id=""`.

**Public API:**

```python
from resolve_vietcap_iq_fa_metric_mapping import (
    build_resolver,          # convenience ctor from CSV paths
    MappingResolver,         # core class
    MappingResult,           # frozen dataclass; .as_dict() → dict[str, str]
    load_primary_mapping,    # load per-symbol primary CSV
    load_union_mapping,      # load union CSV
    MAPPING_RESULT_COLUMNS,  # list of 7 output column names
    VALID_MAPPING_STATUSES,  # frozenset of 6 valid status strings
)

resolver = build_resolver(
    primary_path=Path("..."),          # None for general firms
    union_path=Path("..."),
    primary_source_symbol="VCI",
    primary_source_run_id="20260610T025420Z",
    mapping_group="securities",
)
result: MappingResult = resolver.resolve(section, line_item_code)
rows_out: list[dict] = resolver.resolve_many(rows_in)  # preserves line_item_name
```

## Test coverage

74 tests across 17 groups (all inline CSV fixtures; no live network; no DB):

| # | Group | What is verified |
|---|-------|-----------------|
| 1 | `TestPrimaryLookupHit` | status=`primary`; names populated; source/run-id correct |
| 2 | `TestPrimaryMissConsensusFallback` | miss falls through; `consensus_fallback`; source=`union` |
| 3 | `TestPrimarySectionMismatch` | code in primary but wrong section → `section_mismatch` |
| 4 | `TestUnionSectionMismatch` | miss to union; union section doesn't match → `section_mismatch` |
| 5 | `TestConflictSkipped` | conflict=true → `conflict_skipped`; `mapping_conflict="true"` |
| 6 | `TestNotCovered` | absent from both → `not_covered`; names empty |
| 7 | `TestNoPrimaryUnionFallback` | `has_primary=False`; union hit → `consensus_fallback` |
| 8 | `TestNoPrimaryNoUnionFallback` | `has_primary=False`; no union → `not_covered`; `has_primary=True` empty → `no_mapping_available` |
| 9 | `TestNoInventedNames` | empty names for all non-name-bearing statuses |
| 10 | `TestDeterministicBatch` | `resolve_many` same order, same output, all columns present |
| 11 | `TestNoNetworkImports` | no `httpx`/`requests` in source |
| 12 | `TestNoDBNoBacktest` | no `questdb`/`sqlite3`/`.sqlite`; no DB files written |
| 13 | `TestBackwardsCompatibility` | `line_item_name` passed through; not added; not in `as_dict()` |
| 14 | `TestLoadPrimaryMapping` | loader skips empty-code rows; preserves all columns |
| 15 | `TestLoadUnionMapping` | loader includes conflict rows; skips empty codes |
| 16 | `TestBuildResolver` | CSV-path constructor; `primary_path=None` → general |
| 17 | `TestMappingResultSchema` | `as_dict()` shape; `VALID_MAPPING_STATUSES`; every resolve returns valid status |

## What is NOT implemented here

- **Parser integration**: `scripts/parse_vietcap_iq_fa_payloads_dry_run.py` is unchanged.
  `line_item_name_en` and `line_item_name_vi` do not yet appear in parser output.
- **DB writes**: resolver is pure in-memory; no QuestDB or SQLite interaction.
- **Backtests / live probes / full-history fetch**: out of scope.

## Next step

Wire the resolver into the parser so that `line_item_name_en` and `line_item_name_vi`
appear in parser output. This requires:

1. Integrating `plan_vietcap_iq_fa_firm_type_mapping.py` Approach D classification to
   determine firm type and select the correct primary mapping CSV per symbol.
2. Calling `build_resolver()` and `resolver.resolve_many()` inside the parser.
3. Adding `line_item_name_en`, `line_item_name_vi`, and the 5 `mapping_*` columns to
   `_LONG_FORMAT_COLUMNS` in the parser.

Parser integration does not unblock DB writes by itself — see §15 of
`vietcap_iq_fa_ingestion_v2_readiness.md` for the full gate list.
