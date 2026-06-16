from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class MvpQualityResult:
    table: str
    row_count: int
    status: str
    fail_count: int
    warn_count: int
    pass_count: int
    reasons: dict[str, int]

    def as_dict(self) -> dict[str, object]:
        return {
            "table": self.table,
            "row_count": self.row_count,
            "status": self.status,
            "fail_count": self.fail_count,
            "warn_count": self.warn_count,
            "pass_count": self.pass_count,
            "reasons": self.reasons,
        }


def summarize_quality(table: str, row_statuses: Iterable[tuple[str, list[str]]]) -> MvpQualityResult:
    statuses = list(row_statuses)
    counts = Counter(status for status, _ in statuses)
    reasons = Counter(reason for _, row_reasons in statuses for reason in row_reasons)
    fail_count = counts.get("fail", 0)
    warn_count = counts.get("warn", 0)
    pass_count = counts.get("pass", 0)
    status = "fail" if fail_count else "warn" if warn_count else "pass"
    return MvpQualityResult(
        table=table,
        row_count=len(statuses),
        status=status,
        fail_count=fail_count,
        warn_count=warn_count,
        pass_count=pass_count,
        reasons=dict(sorted(reasons.items())),
    )


def check_duplicate_daily_price_keys(df: pd.DataFrame) -> list[str]:
    required = ["security_id", "trade_date", "source_id"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        return [f"missing_{column}" for column in missing]
    if df.duplicated(required).any():
        return ["duplicate_security_id_trade_date_source_id"]
    return []


def classify_daily_price_row(row: pd.Series) -> tuple[str, list[str]]:
    reasons: list[str] = []
    for field in ["security_id", "symbol", "trade_date", "source_id", "raw_path"]:
        value = row.get(field)
        if value is None or str(value).strip() == "":
            reasons.append(f"missing_{field}")
    for field in ["open", "high", "low", "close"]:
        if pd.isna(row.get(field)):
            reasons.append(f"missing_{field}")
    price_fields_present = all(not pd.isna(row.get(field)) for field in ["open", "high", "low", "close"])
    if price_fields_present:
        high = float(row["high"])
        low = float(row["low"])
        open_ = float(row["open"])
        close = float(row["close"])
        if high < max(open_, close) or low > min(open_, close) or high < low:
            reasons.append("ohlc_inconsistent")
    volume = row.get("volume")
    if volume is not None and not pd.isna(volume) and float(volume) < 0:
        reasons.append("negative_volume")
    if reasons:
        return "fail", sorted(set(reasons))
    if row.get("adjustment_status") == "unknown":
        return "warn", ["adjustment_status_unknown"]
    return "pass", []


def classify_security_row(row: pd.Series) -> tuple[str, list[str]]:
    reasons = []
    for field in ["security_id", "symbol", "exchange", "issuer_name", "source_id", "raw_path"]:
        value = row.get(field)
        if value is None or str(value).strip() == "":
            reasons.append(f"missing_{field}")
    return ("fail", reasons) if reasons else ("pass", [])
