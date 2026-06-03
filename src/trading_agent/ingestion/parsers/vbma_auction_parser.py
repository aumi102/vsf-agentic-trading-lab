from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd


SOURCE_NAME = "vbma"
SCHEMA_VERSION = "vbma_auction_dry_run_v1"
PARSER_VERSION = "vbma_auction_parser_v1"
XLSX_SIGNATURE = b"PK\x03\x04"

CANONICAL_COLUMNS = [
    "bond_code",
    "issuer",
    "tenor_years",
    "auction_or_issue_date",
    "offered_amount_billion_vnd",
    "bid_amount_billion_vnd",
    "winning_amount_billion_vnd",
    "winning_yield_pct",
    "bid_yield_max_pct",
    "bid_yield_min_pct",
]

HEADER_MAP = {
    "ma trai phieu": "bond_code",
    "ma£ tra¡i phiaº¿u": "bond_code",
    "to chuc phat hanh": "issuer",
    "ta»• cha»©c pha¡t ha nh": "issuer",
    "ky han (nam)": "tenor_years",
    "ka»³ haº¡n (naƒm)": "tenor_years",
    "ngay tcph": "auction_or_issue_date",
    "nga y tcph": "auction_or_issue_date",
    "gia tri goi thau (ty dong)": "offered_amount_billion_vnd",
    "gia¡ tra»‹ ga» i thaº§u (ta»· a‘a»“ng)": "offered_amount_billion_vnd",
    "gia tri dat thau (ty dong)": "bid_amount_billion_vnd",
    "gia¡ tra»‹ a‘aº·t thaº§u (ta»· a‘a»“ng)": "bid_amount_billion_vnd",
    "gia tri trung thau (ty dong)": "winning_amount_billion_vnd",
    "gia¡ tra»‹ truºng thaº§u (ta»· a‘a»“ng)": "winning_amount_billion_vnd",
    "lai suat trung thau (%/y)": "winning_yield_pct",
    "la£i suaº¥t truºng thaº§u (%/y)": "winning_yield_pct",
    "lai suat dau thau max": "bid_yield_max_pct",
    "la£i suaº¥t a‘aº¥u thaº§u max": "bid_yield_max_pct",
    "lai suat dau thau min": "bid_yield_min_pct",
    "la£i suaº¥t a‘aº¥u thaº§u min": "bid_yield_min_pct",
}

REQUIRED_COLUMNS = ["bond_code", "issuer", "tenor_years", "auction_or_issue_date"]
AMOUNT_COLUMNS = ["offered_amount_billion_vnd", "bid_amount_billion_vnd", "winning_amount_billion_vnd"]
YIELD_COLUMNS = ["winning_yield_pct", "bid_yield_max_pct", "bid_yield_min_pct"]
NUMERIC_COLUMNS = ["tenor_years", *AMOUNT_COLUMNS, *YIELD_COLUMNS]


@dataclass(frozen=True)
class VbmaParseResult:
    bond_instruments: pd.DataFrame
    bond_auction_results: pd.DataFrame
    validation_summary: dict[str, Any]


def is_xlsx_payload(path: str | Path) -> bool:
    path = Path(path)
    with path.open("rb") as handle:
        head = handle.read(4)
    if head != XLSX_SIGNATURE:
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
        return "[Content_Types].xml" in names and any(name.startswith("xl/") for name in names)
    except zipfile.BadZipFile:
        return False


def normalize_header(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.strip().replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", text)


def header_key(value: Any) -> str:
    return _header_key_from_text(normalize_header(value))


def _header_key_candidates(value: Any) -> list[str]:
    text = normalize_header(value)
    candidates = [_header_key_from_text(text)]
    repaired = _repair_mojibake(text)
    if repaired != text:
        candidates.append(_header_key_from_text(repaired))
    return candidates


def _header_key_from_text(text: str) -> str:
    normalized = normalize_header(text).lower()
    decomposed = unicodedata.normalize("NFD", normalized)
    without_accents = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return without_accents.replace("đ", "d")


def _repair_mojibake(text: str) -> str:
    for encoding in ("cp1252", "latin1"):
        try:
            return text.encode(encoding).decode("utf-8")
        except UnicodeError:
            continue
    return text


def parse_vbma_auction_payload(raw_path: str | Path, metadata_path: str | Path) -> VbmaParseResult:
    raw_path = Path(raw_path)
    metadata_path = Path(metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    raw_bytes = raw_path.read_bytes()
    raw_content_hash = metadata.get("content_hash") or hashlib.sha256(raw_bytes).hexdigest()
    source_payload_id = f"{SOURCE_NAME}:{str(raw_content_hash)[:16]}"

    if not is_xlsx_payload(raw_path):
        raise ValueError(f"Unsupported VBMA payload type for {raw_path}: expected XLSX signature/content.")

    workbook = pd.ExcelFile(BytesIO(raw_bytes))
    source_df = _read_relevant_sheet(workbook)
    normalized = _normalize_rows(source_df, raw_content_hash=raw_content_hash, source_payload_id=source_payload_id)
    validated = _validate_rows(normalized)
    instruments = _build_bond_instruments(validated)
    summary = _build_validation_summary(
        raw_path=raw_path,
        metadata_path=metadata_path,
        metadata=metadata,
        source_df=source_df,
        auction_results=validated,
        bond_instruments=instruments,
        raw_content_hash=raw_content_hash,
    )
    return VbmaParseResult(bond_instruments=instruments, bond_auction_results=validated, validation_summary=summary)


def _read_relevant_sheet(workbook: pd.ExcelFile) -> pd.DataFrame:
    best_df: pd.DataFrame | None = None
    best_score = -1
    for sheet_name in workbook.sheet_names:
        candidate = pd.read_excel(workbook, sheet_name=sheet_name)
        candidate = candidate.dropna(how="all")
        mapped = _rename_columns(candidate)
        score = sum(1 for column in REQUIRED_COLUMNS if column in mapped.columns)
        if score > best_score:
            best_df = candidate
            best_score = score
    if best_df is None or best_score < len(REQUIRED_COLUMNS):
        raise ValueError("No VBMA auction sheet with required columns was found.")
    return best_df.dropna(how="all").reset_index(drop=True)


def _rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {}
    for column in df.columns:
        for key in _header_key_candidates(column):
            canonical = HEADER_MAP.get(key) or _canonical_from_header_key(key)
            if canonical:
                rename_map[column] = canonical
                break
    return df.rename(columns=rename_map)


def _canonical_from_header_key(key: str) -> str | None:
    if "lai" in key or "la£i" in key:
        if "trung" in key or "tru" in key:
            return "winning_yield_pct"
        if "max" in key:
            return "bid_yield_max_pct"
        if "min" in key:
            return "bid_yield_min_pct"

    if not ("gia" in key or "gia¡" in key):
        return None
    if "trung" in key or "tru" in key:
        return "winning_amount_billion_vnd"
    if "goi" in key or "ga»" in key or "ga" in key:
        return "offered_amount_billion_vnd"
    if "dat" in key or "aº·t" in key:
        return "bid_amount_billion_vnd"
    return None


def _normalize_rows(df: pd.DataFrame, *, raw_content_hash: str, source_payload_id: str) -> pd.DataFrame:
    rows = _rename_columns(df).copy()
    missing = [column for column in CANONICAL_COLUMNS if column not in rows.columns]
    for column in missing:
        rows[column] = pd.NA

    rows = rows[CANONICAL_COLUMNS].copy()
    rows["raw_row_index"] = list(df.index)
    rows["bond_code"] = rows["bond_code"].map(_clean_text)
    rows["issuer"] = rows["issuer"].map(_clean_text)
    for column in NUMERIC_COLUMNS:
        rows[column] = rows[column].map(lambda value, column=column: _clean_number_value(value, column))
        rows[column] = pd.to_numeric(rows[column], errors="coerce")
    rows["auction_or_issue_date"] = rows["auction_or_issue_date"].map(_parse_date_value)
    rows["auction_or_issue_date"] = rows["auction_or_issue_date"].where(rows["auction_or_issue_date"].notna(), pd.NA)
    rows["source_name"] = SOURCE_NAME
    rows["source_payload_id"] = source_payload_id
    rows["raw_content_hash"] = raw_content_hash
    rows["amount_unit"] = "billion_vnd"
    rows["schema_version"] = SCHEMA_VERSION
    rows["bond_id"] = rows["bond_code"].map(lambda value: f"{SOURCE_NAME}:{value}" if _has_value(value) else pd.NA)
    rows["auction_result_id"] = rows.apply(_make_auction_result_id, axis=1)
    rows["bid_to_cover_ratio"] = rows.apply(_bid_to_cover_ratio, axis=1)
    return rows


def _validate_rows(df: pd.DataFrame) -> pd.DataFrame:
    rows = df.copy()
    duplicate_key_mask = rows.duplicated(subset=["bond_code", "auction_or_issue_date"], keep=False)
    exact_duplicate_mask = rows.duplicated(
        subset=[
            "bond_code",
            "auction_or_issue_date",
            "offered_amount_billion_vnd",
            "bid_amount_billion_vnd",
            "winning_amount_billion_vnd",
            "winning_yield_pct",
            "bid_yield_max_pct",
            "bid_yield_min_pct",
        ],
        keep=False,
    )
    statuses: list[str] = []
    reasons_all: list[str] = []

    for index, row in rows.iterrows():
        fail_reasons: list[str] = []
        warn_reasons: list[str] = []
        for column in REQUIRED_COLUMNS:
            if not _has_value(row[column]):
                fail_reasons.append(f"missing_required_{column}")

        for column in [*AMOUNT_COLUMNS, *YIELD_COLUMNS]:
            if _has_value(row[column]) and row[column] < 0:
                fail_reasons.append(f"negative_{column}")

        if _has_value(row["winning_amount_billion_vnd"]) and _has_value(row["bid_amount_billion_vnd"]):
            if row["winning_amount_billion_vnd"] > row["bid_amount_billion_vnd"]:
                fail_reasons.append("winning_amount_greater_than_bid_amount")

        if _has_value(row["bid_yield_min_pct"]) and _has_value(row["bid_yield_max_pct"]):
            if row["bid_yield_min_pct"] > row["bid_yield_max_pct"]:
                warn_reasons.append("warning_bid_yield_min_greater_than_max")

        if bool(exact_duplicate_mask.loc[index]):
            fail_reasons.append("exact_duplicate_bond_auction_result_identity")
        elif bool(duplicate_key_mask.loc[index]):
            warn_reasons.append("warning_duplicate_bond_code_auction_or_issue_date")

        if fail_reasons:
            statuses.append("fail")
        elif warn_reasons:
            statuses.append("warn")
        else:
            statuses.append("pass")
        reasons_all.append(";".join(sorted(set(fail_reasons + warn_reasons))))

    rows["quality_status"] = statuses
    rows["quality_reasons"] = reasons_all
    return rows[
        [
            "auction_result_id",
            "bond_id",
            "bond_code",
            "issuer",
            "tenor_years",
            "auction_or_issue_date",
            "offered_amount_billion_vnd",
            "bid_amount_billion_vnd",
            "winning_amount_billion_vnd",
            "winning_yield_pct",
            "bid_yield_max_pct",
            "bid_yield_min_pct",
            "bid_to_cover_ratio",
            "amount_unit",
            "source_name",
            "source_payload_id",
            "raw_content_hash",
            "raw_row_index",
            "schema_version",
            "quality_status",
            "quality_reasons",
        ]
    ]


def _build_bond_instruments(auction_results: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "bond_id",
        "bond_code",
        "issuer",
        "tenor_years",
        "currency",
        "source_name",
        "source_payload_id",
        "raw_content_hash",
        "schema_version",
    ]
    instruments = auction_results[["bond_id", "bond_code", "issuer", "tenor_years", "source_name", "source_payload_id", "raw_content_hash", "schema_version"]]
    instruments = instruments[instruments["bond_code"].map(_has_value)].drop_duplicates(subset=["bond_id"]).copy()
    instruments["currency"] = "VND"
    return instruments[columns].reset_index(drop=True)


def _build_validation_summary(
    *,
    raw_path: Path,
    metadata_path: Path,
    metadata: dict[str, Any],
    source_df: pd.DataFrame,
    auction_results: pd.DataFrame,
    bond_instruments: pd.DataFrame,
    raw_content_hash: str,
) -> dict[str, Any]:
    fail_count = int((auction_results["quality_status"] == "fail").sum())
    warn_count = int((auction_results["quality_status"] == "warn").sum())
    pass_count = int((auction_results["quality_status"] == "pass").sum())
    duplicate_count = int(auction_results.duplicated(subset=["bond_code", "auction_or_issue_date"], keep=False).sum())
    exact_duplicate_count = int(
        auction_results.duplicated(
            subset=[
                "bond_code",
                "auction_or_issue_date",
                "offered_amount_billion_vnd",
                "bid_amount_billion_vnd",
                "winning_amount_billion_vnd",
                "winning_yield_pct",
                "bid_yield_max_pct",
                "bid_yield_min_pct",
            ],
            keep=False,
        ).sum()
    )
    reason_counts: dict[str, int] = {}
    warning_reason_counts: dict[str, int] = {}
    failure_reason_counts: dict[str, int] = {}
    for value in auction_results["quality_reasons"].dropna():
        for reason in str(value).split(";"):
            if reason:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
                if reason.startswith("warning_"):
                    warning_reason_counts[reason] = warning_reason_counts.get(reason, 0) + 1
                else:
                    failure_reason_counts[reason] = failure_reason_counts.get(reason, 0) + 1
    return {
        "source_name": SOURCE_NAME,
        "dataset": metadata.get("dataset", "vbma_primary_market_auction_results"),
        "raw_path": str(raw_path),
        "metadata_path": str(metadata_path),
        "raw_content_hash": raw_content_hash,
        "parser_version": PARSER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "input_row_count": int(len(source_df)),
        "bond_instrument_count": int(len(bond_instruments)),
        "bond_auction_result_count": int(len(auction_results)),
        "quality_pass_count": pass_count,
        "quality_warn_count": warn_count,
        "quality_fail_count": fail_count,
        "duplicate_bond_code_date_count": duplicate_count,
        "exact_duplicate_canonical_row_count": exact_duplicate_count,
        "quality_reason_counts": reason_counts,
        "quality_warning_reason_counts": warning_reason_counts,
        "quality_failure_reason_counts": failure_reason_counts,
        "terms_notes": metadata.get("terms_notes", ""),
    }


def _clean_text(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text in {"", "-"}:
        return None
    return text


def _clean_number_value(value: Any, column: str = "") -> Any:
    if pd.isna(value):
        return pd.NA
    if isinstance(value, str):
        text = value.strip().replace(" ", "")
        if text in {"", "-"}:
            return pd.NA
        text = _normalize_number_text(text, column)
        return text
    return value


def _parse_date_value(value: Any) -> Any:
    if pd.isna(value):
        return pd.NA
    if isinstance(value, str):
        text = value.strip()
        if not text or text == "-":
            return pd.NA
        if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", text):
            parsed = pd.to_datetime(text, errors="coerce", format="%Y-%m-%d")
        else:
            parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
    else:
        parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return pd.NA
    return parsed.strftime("%Y-%m-%d")


def _normalize_number_text(text: str, column: str = "") -> str:
    if "," not in text:
        return text
    if "." in text:
        if text.rfind(",") > text.rfind("."):
            return text.replace(".", "").replace(",", ".")
        return text.replace(",", "")

    parts = text.split(",")
    if len(parts) == 2:
        left, right = parts
        if column in AMOUNT_COLUMNS and len(right) == 3 and left.isdigit() and right.isdigit():
            return left + right
        if right.isdigit() and len(right) <= 3:
            return left + "." + right

    if all(part.isdigit() for part in parts) and all(len(part) == 3 for part in parts[1:]):
        return "".join(parts)
    return text.replace(",", ".")


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except TypeError:
        pass
    return str(value).strip() != ""


def _make_auction_result_id(row: pd.Series) -> str:
    parts = [
        SOURCE_NAME,
        str(row.get("bond_code") or ""),
        str(row.get("auction_or_issue_date") or ""),
        str(row.get("raw_row_index", "")),
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{SOURCE_NAME}:auction:{digest}"


def _bid_to_cover_ratio(row: pd.Series) -> float | None:
    bid_amount = row.get("bid_amount_billion_vnd")
    offered_amount = row.get("offered_amount_billion_vnd")
    if not _has_value(bid_amount) or not _has_value(offered_amount) or offered_amount <= 0:
        return None
    return float(bid_amount / offered_amount)
