"""Reusable execution-assumption guards for research backtests."""
from __future__ import annotations

from dataclasses import dataclass


EXCHANGE_PRICE_BANDS_BPS = {
    "HOSE": 700,
    "HSX": 700,
    "HNX": 1000,
    "UPCOM": 1500,
}


@dataclass(frozen=True)
class PriceBandGuardResult:
    exchange: str
    slippage_bps: float
    price_band_bps: int | None
    status: str
    caveats: tuple[str, ...]


def normalize_exchange(exchange: str | None) -> str:
    value = str(exchange or "").strip().upper()
    if value in {"", "NULL", "NONE", "N/A", "UNKNOWN"}:
        return "UNKNOWN"
    if value in {"UPCOM", "UPC"}:
        return "UPCOM"
    return value


def evaluate_price_band_guard(exchange: str | None, slippage_bps: float) -> PriceBandGuardResult:
    """Validate explicit slippage against known Vietnam exchange price bands.

    Unknown exchanges are not treated as hard failures because the current
    QuestDB `securities.exchange` values can be missing. The result makes that
    limitation explicit so persisted backtest runs remain auditable.
    """
    exchange_key = normalize_exchange(exchange)
    if slippage_bps < 0:
        return PriceBandGuardResult(
            exchange=exchange_key,
            slippage_bps=slippage_bps,
            price_band_bps=None,
            status="slippage_bps_invalid",
            caveats=("slippage_bps_must_be_non_negative",),
        )
    band = EXCHANGE_PRICE_BANDS_BPS.get(exchange_key)
    if band is None:
        return PriceBandGuardResult(
            exchange=exchange_key,
            slippage_bps=slippage_bps,
            price_band_bps=None,
            status="exchange_unknown_price_band_guard_not_fully_verified",
            caveats=("exchange_unknown_price_band_guard_not_fully_verified",),
        )
    if slippage_bps > band:
        return PriceBandGuardResult(
            exchange=exchange_key,
            slippage_bps=slippage_bps,
            price_band_bps=band,
            status="slippage_bps_exceeds_exchange_price_band",
            caveats=(f"slippage_bps_exceeds_exchange_price_band:{slippage_bps}/{band}",),
        )
    return PriceBandGuardResult(
        exchange=exchange_key,
        slippage_bps=slippage_bps,
        price_band_bps=band,
        status="price_band_guard_pass",
        caveats=(f"price_band_guard_pass:{exchange_key}:{slippage_bps}/{band}",),
    )
