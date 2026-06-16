from __future__ import annotations

from pathlib import Path

from trading_agent.tools._store import DEFAULT_DB_PATH
from trading_agent.tools.feature_tool import compute_latest_features
from trading_agent.tools.market_data_tool import get_latest_market_data
from trading_agent.tools.risk_tool import assess_symbol_risk
from trading_agent.tools.signal_tool import evaluate_active_signals


def compose_market_answer(symbol: str, language: str = "vi", db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, object]:
    normalized = symbol.strip().upper()
    market = get_latest_market_data(normalized, db_path)
    features = compute_latest_features(normalized, db_path)
    signal = evaluate_active_signals(normalized, db_path)
    risk = assess_symbol_risk(normalized, db_path)
    if language != "vi":
        caveat = "Only Vietnamese report text is implemented in the MVP."
    else:
        caveat = ""
    answer = _compose_vietnamese(normalized, market, features, signal, risk)
    caveats = [caveat] if caveat else []
    return {
        "status": "ok" if market.get("status") == "ok" else "not_available",
        "symbol": normalized,
        "language": language,
        "answer_markdown": answer,
        "tool_outputs": {
            "market_data": market,
            "features": features,
            "signal": signal,
            "risk": risk,
        },
        "caveats": caveats,
    }


def _fmt(value: object, digits: int = 2) -> str:
    if value is None:
        return "không có dữ liệu"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _pct(value: object) -> str:
    if value is None:
        return "không có dữ liệu"
    return f"{float(value) * 100:.2f}%"


def _compose_vietnamese(symbol: str, market: dict[str, object], features: dict[str, object], signal: dict[str, object], risk: dict[str, object]) -> str:
    if market.get("status") != "ok":
        return (
            f"## {symbol}\n\n"
            "Chưa có dữ liệu thị trường trong MVP store cho mã này. "
            "Không đưa ra nhận định khi thiếu dữ liệu quan sát được.\n\n"
            "_Đây không phải là khuyến nghị đầu tư._"
        )
    ohlcv = market["ohlcv"]
    feature_values = features.get("features", {}) if features.get("status") == "ok" else {}
    caveats = []
    for output in [market, features, signal, risk]:
        caveats.extend(output.get("caveats") or [])
    caveat_text = "\n".join(f"- {item}" for item in sorted(set(caveats))) or "- Không có caveat bổ sung từ tool."
    return (
        f"## {symbol} - tóm tắt MVP\n\n"
        f"- Ngày dữ liệu mới nhất: `{market['latest_date']}`.\n"
        f"- Giá đóng cửa: `{_fmt(ohlcv.get('close'))}`; khối lượng: `{_fmt(ohlcv.get('volume'), 0)}`.\n"
        f"- Return 1D / 5D / 20D: `{_pct(feature_values.get('return_1d'))}` / "
        f"`{_pct(feature_values.get('return_5d'))}` / `{_pct(feature_values.get('return_20d'))}`.\n"
        f"- MA20 / MA50: `{_fmt(feature_values.get('ma_20'))}` / `{_fmt(feature_values.get('ma_50'))}`.\n"
        f"- Tín hiệu rule-based: `{signal.get('action')}` (`{signal.get('reason_codes', [''])[0] if signal.get('reason_codes') else ''}`).\n"
        f"- Cờ rủi ro: `{', '.join(risk.get('risk_flags') or [])}`.\n\n"
        "### Caveat\n"
        f"{caveat_text}\n\n"
        "_Đây là demo công cụ nội bộ, không phải khuyến nghị đầu tư hoặc lệnh giao dịch._"
    )
