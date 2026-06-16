from __future__ import annotations

from pathlib import Path
from typing import Any

from trading_agent.agent.orchestrator import BUILD_INSTRUCTION, answer_market_query
from trading_agent.tools._store import DEFAULT_DB_PATH
from trading_agent.tools.feature_tool import compute_latest_features
from trading_agent.tools.market_data_tool import get_latest_market_data
from trading_agent.tools.report_tool import compose_market_answer
from trading_agent.tools.risk_tool import assess_symbol_risk
from trading_agent.tools.signal_tool import evaluate_active_signals

SUPPORTED_SCENARIOS = ("market_brief", "risk_check", "compare")


def run_demo(
    scenario: str,
    *,
    symbol: str | None = None,
    symbols: list[str] | None = None,
    query: str | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    path = Path(db_path)

    if scenario not in SUPPORTED_SCENARIOS:
        return {
            "status": "invalid_scenario",
            "scenario": scenario,
            "input": {"symbol": symbol, "symbols": symbols, "query": query},
            "tool_call_trace": [],
            "outputs": {},
            "answer_markdown": (
                f"Kịch bản `{scenario}` không hợp lệ. "
                f"Các kịch bản được hỗ trợ: {', '.join(SUPPORTED_SCENARIOS)}."
            ),
            "caveats": [f"Unknown scenario: {scenario}"],
            "not_financial_advice": True,
        }

    if not path.exists():
        return {
            "status": "missing_store",
            "scenario": scenario,
            "input": {"symbol": symbol, "symbols": symbols, "query": query},
            "tool_call_trace": [],
            "outputs": {},
            "answer_markdown": (
                f"Chưa có MVP SQLite store tại `{path}`. "
                f"Hãy chạy `{BUILD_INSTRUCTION}` trước khi chạy demo."
            ),
            "caveats": [f"MVP store missing: {path}", f"Build command: {BUILD_INSTRUCTION}"],
            "not_financial_advice": True,
        }

    if scenario == "market_brief":
        return _run_market_brief(symbol=symbol, query=query, path=path)
    if scenario == "risk_check":
        return _run_risk_check(symbol=symbol, path=path)
    return _run_compare(symbols=symbols or [], path=path)


def _run_market_brief(
    symbol: str | None,
    query: str | None,
    path: Path,
) -> dict[str, Any]:
    result = answer_market_query(query=query, symbol=symbol, db_path=path)
    sym = result.get("symbol")
    trace = _build_trace_from_outputs(sym, result.get("tool_outputs", {}))
    return {
        "status": result["status"],
        "scenario": "market_brief",
        "input": {"symbol": symbol, "query": query},
        "tool_call_trace": trace,
        "outputs": result.get("tool_outputs", {}),
        "answer_markdown": result.get("answer_markdown", ""),
        "caveats": result.get("caveats", []),
        "not_financial_advice": True,
    }


def _run_risk_check(symbol: str | None, path: Path) -> dict[str, Any]:
    if not symbol:
        return {
            "status": "needs_symbol",
            "scenario": "risk_check",
            "input": {"symbol": symbol},
            "tool_call_trace": [],
            "outputs": {},
            "answer_markdown": "Vui lòng truyền `--symbol` cho kịch bản risk_check.",
            "caveats": ["No symbol provided for risk_check."],
            "not_financial_advice": True,
        }
    sym = symbol.strip().upper()
    market = get_latest_market_data(sym, path)
    features = compute_latest_features(sym, path)
    signal = evaluate_active_signals(sym, path)
    risk = assess_symbol_risk(sym, path)
    report = compose_market_answer(sym, language="vi", db_path=path)
    outputs: dict[str, Any] = {
        "market_data": market,
        "features": features,
        "signal": signal,
        "risk": risk,
        "report": report,
    }
    trace = _build_trace_from_outputs(sym, outputs)
    status = "ok" if market.get("status") == "ok" else str(market.get("status") or "not_found")

    caveats: list[str] = []
    for v in outputs.values():
        caveats.extend(v.get("caveats") or [])

    risk_flags = risk.get("risk_flags") or []
    risk_lines = "\n".join(f"- `{flag}`" for flag in risk_flags) if risk_flags else "- Không có cờ rủi ro."
    caveat_lines = "\n".join(f"- {c}" for c in sorted(set(str(c) for c in caveats))) or "- Không có caveat bổ sung."

    if market.get("status") == "ok":
        answer = (
            f"## {sym} — Kiểm tra rủi ro\n\n"
            f"**Ngày:** `{market.get('latest_date')}`\n\n"
            f"**Cờ rủi ro:**\n{risk_lines}\n\n"
            f"**Chất lượng rủi ro:** `{risk.get('quality_status')}`\n\n"
            "### Caveat\n"
            f"{caveat_lines}\n\n"
            "_Đây là demo công cụ nội bộ, không phải khuyến nghị đầu tư hoặc lệnh giao dịch._"
        )
    else:
        answer = (
            f"## {sym} — Kiểm tra rủi ro\n\n"
            "Chưa có dữ liệu thị trường trong MVP store cho mã này.\n\n"
            "_Đây không phải là khuyến nghị đầu tư._"
        )

    return {
        "status": status,
        "scenario": "risk_check",
        "input": {"symbol": symbol},
        "tool_call_trace": trace,
        "outputs": outputs,
        "answer_markdown": answer,
        "caveats": sorted(set(str(c) for c in caveats)),
        "not_financial_advice": True,
    }


def _run_compare(symbols: list[str], path: Path) -> dict[str, Any]:
    if not symbols:
        return {
            "status": "needs_symbol",
            "scenario": "compare",
            "input": {"symbols": symbols},
            "tool_call_trace": [],
            "outputs": {},
            "answer_markdown": "Vui lòng truyền `--symbols` cho kịch bản compare.",
            "caveats": ["No symbols provided for compare."],
            "not_financial_advice": True,
        }

    rows: list[dict[str, Any]] = []
    all_trace: list[dict[str, Any]] = []
    caveats: list[str] = []
    any_ok = False

    for raw_sym in symbols:
        sym = raw_sym.strip().upper()
        market = get_latest_market_data(sym, path)
        features = compute_latest_features(sym, path)
        signal = evaluate_active_signals(sym, path)
        risk = assess_symbol_risk(sym, path)
        sub_outputs: dict[str, Any] = {
            "market_data": market,
            "features": features,
            "signal": signal,
            "risk": risk,
        }
        all_trace.extend(_build_trace_from_outputs(sym, sub_outputs))
        for v in sub_outputs.values():
            caveats.extend(v.get("caveats") or [])

        if market.get("status") == "ok":
            any_ok = True
            feat_vals = features.get("features", {}) if features.get("status") == "ok" else {}
            rows.append({
                "symbol": sym,
                "status": "ok",
                "latest_date": market.get("latest_date"),
                "close": market.get("ohlcv", {}).get("close"),
                "return_1d": feat_vals.get("return_1d"),
                "return_5d": feat_vals.get("return_5d"),
                "return_20d": feat_vals.get("return_20d"),
                "signal_action": signal.get("action") if signal.get("status") == "ok" else None,
                "risk_flags": risk.get("risk_flags") or [],
                "quality_status": market.get("quality_status"),
            })
        else:
            rows.append({
                "symbol": sym,
                "status": "not_found",
                "latest_date": None,
                "close": None,
                "return_1d": None,
                "return_5d": None,
                "return_20d": None,
                "signal_action": None,
                "risk_flags": [],
                "quality_status": None,
            })

    overall_status = "ok" if any_ok else "not_found"
    header = "| Symbol | Status | Date | Close | R1D | R5D | R20D | Signal | Risk Flags | Quality |\n"
    sep = "|---|---|---|---|---|---|---|---|---|---|\n"
    table_lines = []
    for row in rows:
        def _pct(v: object) -> str:
            if v is None:
                return "N/A"
            return f"{float(v) * 100:.2f}%"

        def _fmt(v: object, d: int = 2) -> str:
            if v is None:
                return "N/A"
            if isinstance(v, float):
                return f"{v:.{d}f}"
            return str(v)

        risk_str = ", ".join(row["risk_flags"]) if row["risk_flags"] else "none"
        table_lines.append(
            f"| {row['symbol']} | {row['status']} | {row['latest_date'] or 'N/A'} | "
            f"{_fmt(row['close'])} | {_pct(row['return_1d'])} | "
            f"{_pct(row['return_5d'])} | {_pct(row['return_20d'])} | "
            f"{row['signal_action'] or 'N/A'} | {risk_str} | {row['quality_status'] or 'N/A'} |"
        )

    answer = (
        "## So sánh nhiều mã\n\n"
        + header
        + sep
        + "\n".join(table_lines)
        + "\n\n_Không xếp hạng theo thứ tự đầu tư. "
        "Đây là demo công cụ nội bộ, không phải khuyến nghị đầu tư hoặc lệnh giao dịch._"
    )

    return {
        "status": overall_status,
        "scenario": "compare",
        "input": {"symbols": symbols},
        "tool_call_trace": all_trace,
        "outputs": {"rows": rows},
        "answer_markdown": answer,
        "caveats": sorted(set(str(c) for c in caveats)),
        "not_financial_advice": True,
    }


def _build_trace_from_outputs(
    symbol: str | None,
    outputs: dict[str, Any],
) -> list[dict[str, Any]]:
    tool_order = ["market_data", "features", "signal", "risk", "report"]
    trace = []
    for tool_name in tool_order:
        if tool_name not in outputs:
            continue
        out = outputs[tool_name]
        trace.append({
            "tool_name": tool_name,
            "symbol": symbol,
            "status": out.get("status"),
            "quality_status": out.get("quality_status"),
        })
    return trace
