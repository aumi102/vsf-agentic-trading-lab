"""Load source-backed Vietcap IQ FA metric mapping into QuestDB.

This writes only the additive metadata table ``fa_metric_mapping``. It does not
modify FA fact tables or FA ingest runs.
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass

from trading_agent.storage import questdb_client as qdb  # noqa: E402

DEFAULT_MAPPING = ROOT / "data" / "processed" / "vietcap_iq" / "fa_metric_mapping_union_v2.csv"
FALLBACK_MAPPING = ROOT / "data" / "processed" / "vietcap_iq" / "fa_metric_mapping_union.csv"
REPORT_PATH = ROOT / "docs" / "data_sources" / "fa_metric_mapping_status.md"
TABLE = "fa_metric_mapping"
FA_TABLES = {
    "BALANCE_SHEET": "fa_balance_sheet",
    "INCOME_STATEMENT": "fa_income_statement",
    "CASH_FLOW": "fa_cash_flow",
    "NOTE": "fa_notes",
}
OUTPUT_COLUMNS = [
    "updated_at",
    "statement_type",
    "metric_code",
    "metric_name_vi",
    "metric_name_en",
    "source",
    "source_detail",
    "quality_status",
]


def _ddl() -> str:
    return """CREATE TABLE IF NOT EXISTS fa_metric_mapping (
        updated_at TIMESTAMP,
        statement_type SYMBOL CAPACITY 256 CACHE,
        metric_code SYMBOL CAPACITY 4096 CACHE,
        metric_name_vi STRING,
        metric_name_en STRING,
        source SYMBOL CAPACITY 256 CACHE,
        source_detail STRING,
        quality_status SYMBOL CAPACITY 256 CACHE
    ) TIMESTAMP(updated_at) PARTITION BY YEAR WAL"""


def _csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in OUTPUT_COLUMNS})
    return out.getvalue().encode("utf-8")


def _read_mapping(path: Path) -> list[dict[str, Any]]:
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for raw in csv.DictReader(fh):
            statement_type = str(raw.get("section") or "").strip().upper()
            code = str(raw.get("line_item_code") or "").strip()
            if not statement_type or not code:
                continue
            conflict = str(raw.get("conflict") or "").strip().lower() == "true"
            name_en = str(raw.get("line_item_name_en_consensus") or "").strip()
            quality = "source_backed_consensus" if name_en and not conflict else "source_mapping_conflict" if conflict else "source_mapping_name_blank"
            rows.append(
                {
                    "updated_at": updated_at,
                    "statement_type": statement_type,
                    "metric_code": code,
                    "metric_name_vi": "",
                    "metric_name_en": name_en,
                    "source": "vietcap_iq_metrics_mapping_union",
                    "source_detail": f"{path.name};sources={raw.get('sources') or ''};level={raw.get('level') or ''};parent={raw.get('parent') or ''}",
                    "quality_status": quality,
                }
            )
    return rows


def _existing_tables(client, base: str) -> set[str]:
    _, rows = qdb.exec_rows(client, base, "SHOW TABLES")
    return {str(row[0]) for row in rows if row}


def _coverage(client, base: str) -> dict[str, dict[str, Any]]:
    tables = _existing_tables(client, base)
    out: dict[str, dict[str, Any]] = {}
    for statement_type, table in FA_TABLES.items():
        if table not in tables:
            out[statement_type] = {"table": table, "present": False}
            continue
        total_codes = int(qdb.exec_scalar(client, base, f"SELECT count_distinct(metric_code) FROM {table}", 0))
        total_rows = int(qdb.exec_scalar(client, base, f"SELECT count() FROM {table}", 0))
        consensus_codes = int(
            qdb.exec_scalar(
                client,
                base,
                "SELECT count_distinct(f.metric_code) "
                f"FROM {table} f JOIN {TABLE} m "
                "ON f.metric_code = m.metric_code AND f.statement_type = m.statement_type "
                "WHERE m.quality_status = 'source_backed_consensus'",
                0,
            )
        )
        consensus_rows = int(
            qdb.exec_scalar(
                client,
                base,
                "SELECT count() "
                f"FROM {table} f JOIN {TABLE} m "
                "ON f.metric_code = m.metric_code AND f.statement_type = m.statement_type "
                "WHERE m.quality_status = 'source_backed_consensus'",
                0,
            )
        )
        out[statement_type] = {
            "table": table,
            "present": True,
            "fact_rows": total_rows,
            "fact_distinct_metric_codes": total_codes,
            "mapped_consensus_metric_codes": consensus_codes,
            "mapped_consensus_code_pct": (consensus_codes / total_codes * 100.0) if total_codes else 0.0,
            "mapped_consensus_rows": consensus_rows,
            "mapped_consensus_row_pct": (consensus_rows / total_rows * 100.0) if total_rows else 0.0,
        }
    return out


def _write_report(mapping_path: Path, inserted: int, quality_counts: dict[str, int], coverage: dict[str, dict[str, Any]]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# FA metric mapping status",
        "",
        f"- mapping_source_file: `{mapping_path}`",
        f"- questdb_table: `{TABLE}`",
        f"- rows_loaded: `{inserted}`",
        "",
        "## Mapping row quality",
        "",
        "| quality_status | rows |",
        "|---|---:|",
    ]
    for status, count in sorted(quality_counts.items()):
        lines.append(f"| `{status}` | {count:,} |")
    lines.extend(
        [
            "",
            "## Coverage against current QuestDB FA fact tables",
            "",
            "| Statement | Fact rows | Distinct codes | Consensus mapped codes | Code coverage | Consensus mapped rows | Row coverage |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for statement_type, row in coverage.items():
        if not row.get("present"):
            lines.append(f"| `{statement_type}` | table missing |  |  |  |  |  |")
            continue
        lines.append(
            f"| `{statement_type}` | {int(row['fact_rows']):,} | {int(row['fact_distinct_metric_codes']):,} | "
            f"{int(row['mapped_consensus_metric_codes']):,} | {float(row['mapped_consensus_code_pct']):.1f}% | "
            f"{int(row['mapped_consensus_rows']):,} | {float(row['mapped_consensus_row_pct']):.1f}% |"
        )
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- Mapping is source-backed from captured Vietcap IQ metric mapping artifacts, but it is still partial.",
            "- Conflicting or blank consensus rows are loaded for auditability but should not be treated as semantic metric names.",
            "- FA fact rows remain untouched; tools only enrich names when a consensus mapping is available.",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def load_mapping(questdb_url: str, mapping_path: Path, replace_table: bool) -> dict[str, Any]:
    base = questdb_url.rstrip("/")
    rows = _read_mapping(mapping_path)
    quality_counts: dict[str, int] = {}
    for row in rows:
        status = str(row["quality_status"])
        quality_counts[status] = quality_counts.get(status, 0) + 1
    with qdb.open_client(timeout_seconds=180.0) as client:
        if replace_table:
            print("REPLACING ONLY fa_metric_mapping; FA fact tables untouched")
            qdb.exec_query(client, base, f"DROP TABLE IF EXISTS {TABLE}")
        qdb.exec_query(client, base, _ddl())
        inserted = qdb.imp_csv(client, base, TABLE, _csv_bytes(rows), timeout_seconds=180.0)
        qdb.wait_wal_applied(client, base, TABLE, attempts=120)
        coverage = _coverage(client, base)
    _write_report(mapping_path, inserted, quality_counts, coverage)
    return {"rows_inserted": inserted, "quality_counts": quality_counts, "coverage": coverage, "report_path": str(REPORT_PATH)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Load Vietcap IQ FA metric mapping metadata into QuestDB.")
    parser.add_argument("--questdb-url", default=qdb.DEFAULT_QUESTDB_URL)
    parser.add_argument("--mapping-csv", default=str(DEFAULT_MAPPING if DEFAULT_MAPPING.exists() else FALLBACK_MAPPING))
    parser.add_argument("--append", action="store_true", help="Append instead of replacing fa_metric_mapping.")
    args = parser.parse_args()
    mapping_path = Path(args.mapping_csv)
    if not mapping_path.is_absolute():
        mapping_path = ROOT / mapping_path
    if not mapping_path.exists():
        print(f"error=mapping file not found: {mapping_path}", file=sys.stderr)
        return 2
    result = load_mapping(args.questdb_url, mapping_path, replace_table=not args.append)
    print(f"rows_inserted={result['rows_inserted']}")
    print("quality_counts=" + ",".join(f"{key}:{value}" for key, value in sorted(result["quality_counts"].items())))
    for statement_type, row in result["coverage"].items():
        if row.get("present"):
            print(
                f"coverage_{statement_type}=codes:{row['mapped_consensus_metric_codes']}/{row['fact_distinct_metric_codes']} "
                f"rows:{row['mapped_consensus_rows']}/{row['fact_rows']}"
            )
    print(f"report_path={result['report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
