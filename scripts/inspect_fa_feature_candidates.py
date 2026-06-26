"""Inspect fa_metric_mapping and FA fact tables for safe feature-readiness.

Reports which candidate metrics are source-backed (consensus mapping) and have
fact coverage across the universe. Does NOT invent metric names and does NOT
write any feature values. If the candidate set is too thin, prints a recommendation
to defer fa_feature_snapshots until coverage improves.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (str(SRC), str(ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from trading_agent.storage import questdb_client as qdb  # noqa: E402

# Candidate seed names. Each entry: (display_name, family, list of regex patterns
# applied case-insensitively against metric_name_en).
CANDIDATES: list[dict] = [
    {
        "feature": "revenue / net revenue",
        "family": "INCOME_STATEMENT",
        "patterns": [r"\brevenue\b", r"^net sales$", r"^net revenue$", r"^sales\b", r"\bdoanh thu\b"],
    },
    {
        "feature": "net profit",
        "family": "INCOME_STATEMENT",
        "patterns": [r"net profit", r"profit after tax", r"profit for the year",
                     r"\bnet income\b", r"\bl?净利润\b", r"\blợi nhuận sau thuế\b"],
    },
    {
        "feature": "total assets",
        "family": "BALANCE_SHEET",
        "patterns": [r"\btotal assets\b", r"\bassets total\b", r"\btổng tài sản\b"],
    },
    {
        "feature": "equity",
        "family": "BALANCE_SHEET",
        "patterns": [r"^equity$", r"total equity", r"owners' equity", r"shareholders' equity",
                     r"vốn chủ sở hữu", r"\bvốn cs hữu\b"],
    },
    {
        "feature": "operating cash flow",
        "family": "CASH_FLOW",
        "patterns": [r"operating cash flow", r"cash from operating",
                     r"net cash.*operating", r"lưu chuyển tiền.*hoạt động"],
    },
]

# Minimum thresholds to call a candidate "ready": consensus mapping exists AND
# at least this many distinct symbols have a non-null metric value in the family
# table. Thresholds are conservative; tune as coverage grows.
MIN_DISTINCT_SYMBOLS = 10


def _table_exists(client, base_url: str, table: str) -> bool:
    _, rows = qdb.exec_rows(client, base_url, "SHOW TABLES")
    return table in {str(row[0]) for row in rows if row}


def _rows(client, base_url: str, sql: str) -> list[list]:
    try:
        _, rows = qdb.exec_rows(client, base_url, sql)
        return rows
    except Exception as exc:
        return [["ERR", f"{type(exc).__name__}: {exc}"][:2]]


def _count(client, base_url: str, sql: str) -> int:
    try:
        return int(qdb.exec_scalar(client, base_url, sql, 0))
    except Exception:
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect FA feature-readiness (no writes).")
    parser.add_argument("--questdb-url", default=qdb.DEFAULT_QUESTDB_URL)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    base_url = args.questdb_url.rstrip("/")

    out: dict = {"questdb_url": base_url, "candidates": []}

    with qdb.open_client(timeout_seconds=60.0) as client:
        mapping_present = _table_exists(client, base_url, "fa_metric_mapping")
        if not mapping_present:
            out["mapping_present"] = False
            out["recommendation"] = "fa_metric_mapping is missing; defer fa_feature_snapshots."
            print(json.dumps(out, indent=2, ensure_ascii=False) if args.json else _human(out))
            return 0
        out["mapping_present"] = True
        out["mapping_rows"] = _count(client, base_url, "SELECT count() FROM fa_metric_mapping")

        # Pull all mapping rows with non-empty English name and consensus status.
        rows = _rows(
            client, base_url,
            "SELECT metric_code, metric_name_en, statement_type FROM fa_metric_mapping "
            "WHERE quality_status = 'source_backed_consensus' AND metric_name_en IS NOT NULL "
            "AND metric_name_en != ''",
        )

        for cand in CANDIDATES:
            family = cand["family"]
            patterns = [re.compile(p, re.IGNORECASE) for p in cand["patterns"]]
            matched_codes: list[str] = []
            for row in rows:
                if len(row) < 3:
                    continue
                code, name_en, family_in = row[0], row[1] or "", row[2] or ""
                if family_in != family:
                    continue
                if not isinstance(name_en, str):
                    continue
                if any(p.search(name_en) for p in patterns):
                    matched_codes.append(str(code))

            # Coverage: how many distinct symbols have a non-null metric_value for these codes?
            coverage_symbols = 0
            coverage_rows = 0
            if matched_codes:
                code_list = ",".join(f"'{c}'" for c in matched_codes)
                family_table = {
                    "BALANCE_SHEET": "fa_balance_sheet",
                    "INCOME_STATEMENT": "fa_income_statement",
                    "CASH_FLOW": "fa_cash_flow",
                    "NOTE": "fa_notes",
                }.get(family)
                if family_table and _table_exists(client, base_url, family_table):
                    coverage_symbols = _count(
                        client, base_url,
                        f"SELECT count_distinct(symbol) FROM {family_table} "
                        f"WHERE metric_code IN ({code_list}) AND metric_value IS NOT NULL",
                    )
                    coverage_rows = _count(
                        client, base_url,
                        f"SELECT count() FROM {family_table} "
                        f"WHERE metric_code IN ({code_list}) AND metric_value IS NOT NULL",
                    )

            out["candidates"].append({
                "feature": cand["feature"],
                "family": family,
                "matched_metric_codes": matched_codes,
                "matched_count": len(matched_codes),
                "coverage_symbols": coverage_symbols,
                "coverage_rows": coverage_rows,
                "ready": len(matched_codes) > 0 and coverage_symbols >= MIN_DISTINCT_SYMBOLS,
            })

    ready = [c for c in out["candidates"] if c["ready"]]
    if ready:
        out["recommendation"] = (
            f"{len(ready)} candidate(s) ready: " + ", ".join(c["feature"] for c in ready)
            + ". Safe to author scripts/build_fa_feature_snapshots.py for these."
        )
    else:
        out["recommendation"] = (
            "Insufficient source-backed coverage for any candidate. Defer fa_feature_snapshots "
            "until consensus mapping and fact coverage both grow."
        )

    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(_human(out))
    return 0


def _human(out: dict) -> str:
    lines = ["FA feature candidate inspection", "=" * 50]
    lines.append(f"  mapping_present : {out.get('mapping_present')}  rows={out.get('mapping_rows', 0)}")
    for c in out["candidates"]:
        flag = "READY" if c["ready"] else "WAIT "
        lines.append(
            f"  [{flag}] {c['feature']:25s} family={c['family']:18s} "
            f"codes={c['matched_count']:3d} coverage_syms={c['coverage_symbols']:5d} coverage_rows={c['coverage_rows']:7d}"
        )
    lines.append("")
    lines.append(f"  recommendation: {out.get('recommendation')}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
