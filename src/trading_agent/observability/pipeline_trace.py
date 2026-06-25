"""Anti-blackbox pipeline trace for the mentor demo.

The mentor's feedback was that knowing *which tool was called* is not enough. For
every demo action the UI/API must be able to show:

  * where we are in the data pipeline (source -> raw -> ... -> agent_answer);
  * which agent / sub-agent handled the request;
  * what each agent decided and the concise reason for that decision;
  * which tools were allowed vs rejected, and why;
  * what the final answer is based on (source, tables, query mode);
  * what caveats apply and what the next recommended action is.

This module builds a structured, JSON-serializable trace object that captures all
of the above. It deliberately exposes only concise *decision reasons* (e.g.
"Classified as backtest because the query contains compare/backtest/strategy"),
never hidden chain-of-thought or private model reasoning.

The trace is rule-derived and read-only: it never runs tools itself. Callers pass
in the query plus the already-computed tool result so the trace reflects what
actually happened.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

# Canonical data-pipeline path every answer is positioned against.
PIPELINE_PATH: tuple[str, ...] = (
    "source",
    "raw",
    "bronze",
    "silver",
    "gold",
    "signal",
    "backtest",
    "validation",
    "agent_answer",
)

# The known domains the router can route a query into.
DOMAINS: tuple[str, ...] = (
    "market_summary",
    "financial_report",
    "backtest",
    "event_news",
    "validation",
    "system",
)

# Map the rule-agent intents (questdb_agent_service.classify) onto trace domains.
INTENT_TO_DOMAIN: dict[str, str] = {
    "db_health": "system",
    "latest_ohlcv": "market_summary",
    "latest_features": "market_summary",
    "latest_signal": "market_summary",
    "symbol_summary": "market_summary",
    "ohlcv_window": "market_summary",
    "backtest_results": "backtest",
    "financial_report": "financial_report",
    "event_unavailable": "event_news",
    "unsupported": "system",
}

# Where in the pipeline each domain's answer is sourced from + the tables it reads.
DOMAIN_PIPELINE: dict[str, dict[str, Any]] = {
    "market_summary": {
        "current_step": "signal",
        "upstream_tables": ["daily_prices", "feature_snapshots", "signals", "securities"],
    },
    "financial_report": {
        "current_step": "silver",
        "upstream_tables": ["fa_balance_sheet", "fa_income_statement", "fa_cash_flow", "fa_notes", "fa_metric_mapping"],
    },
    "backtest": {
        "current_step": "backtest",
        "upstream_tables": ["backtest_runs", "backtest_metrics", "backtest_equity_curve", "backtest_trades"],
    },
    "event_news": {
        "current_step": "bronze",
        "upstream_tables": ["event_news_items", "event_news_raw_payloads"],
    },
    "validation": {
        "current_step": "validation",
        "upstream_tables": ["daily_prices", "feature_snapshots", "signals", "backtest_runs", "fa_balance_sheet"],
    },
    "system": {
        "current_step": "validation",
        "upstream_tables": ["daily_prices", "feature_snapshots", "signals"],
    },
}

# Domain-specialist agent identity (the sub-agent that handles the request after routing).
DOMAIN_AGENTS: dict[str, dict[str, str]] = {
    "market_summary": {
        "agent_name": "MarketDataAgent",
        "role": "read persisted OHLCV / features / deterministic signals from QuestDB",
    },
    "financial_report": {
        "agent_name": "FinancialReportAgent",
        "role": "read persisted Vietcap financial-report facts from QuestDB FA tables",
    },
    "backtest": {
        "agent_name": "BacktestAgent",
        "role": "read persisted Backtrader research results; never run live Backtrader",
    },
    "event_news": {
        "agent_name": "EventNewsAgent",
        "role": "read official disclosure records only; never use OHLCV as an event proxy",
    },
    "validation": {
        "agent_name": "ValidationAgent",
        "role": "run read-only validation gates / readiness diagnostics",
    },
    "system": {
        "agent_name": "SystemAgent",
        "role": "report QuestDB table health and system status",
    },
}

# Tool groups each domain is allowed to use, and the tools it must reject.
ALLOWED_TOOLS: dict[str, list[str]] = {
    "market_summary": ["get_symbol_summary", "get_latest_ohlcv", "get_latest_features", "get_latest_signal", "get_ohlcv_window"],
    "financial_report": ["get_latest_financial_report", "get_financial_metrics", "get_financial_report_summary"],
    "backtest": ["get_latest_backtest_metrics", "get_backtest_strategy_comparison", "get_backtest_slippage_scenarios", "get_backtest_equity_curve"],
    "event_news": ["get_symbol_event_news"],
    "validation": ["run_all_gates", "run_mentor_demo_readiness"],
    "system": ["get_table_health", "query_questdb"],
}

REJECTED_TOOLS: dict[str, list[str]] = {
    "market_summary": ["run_ma_backtest", "run_backtrader"],
    "financial_report": ["get_latest_ohlcv", "get_symbol_summary"],
    "backtest": ["run_ma_backtest", "run_backtrader", "run_backtrader_questdb_persist"],
    "event_news": ["get_latest_ohlcv", "get_symbol_summary", "get_latest_financial_report"],
    "validation": [],
    "system": [],
}


@dataclass
class AgentStep:
    """One agent/sub-agent's contribution to handling a request."""

    agent_name: str
    role: str
    decision: str
    reason: str
    input_summary: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    rejected_tools: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PipelineTrace:
    """Builder for a single anti-blackbox trace record."""

    def __init__(self, user_query: str, domain: str, *, request_id: str | None = None) -> None:
        self.request_id = request_id or uuid.uuid4().hex[:12]
        self.user_query = user_query
        self.domain = domain if domain in DOMAINS else "system"
        pipeline = DOMAIN_PIPELINE.get(self.domain, DOMAIN_PIPELINE["system"])
        self.pipeline_position: dict[str, Any] = {
            "layer": "agent_answer",
            "path": list(PIPELINE_PATH),
            "current_step": pipeline["current_step"],
            "upstream_tables": list(pipeline["upstream_tables"]),
        }
        self.agents: list[AgentStep] = []
        self.final_answer_basis: dict[str, Any] = {
            "source": "QuestDB",
            "tables": list(pipeline["upstream_tables"]),
            "query_mode": "REST",
            "caveats": [],
        }
        self.next_actions: list[dict[str, Any]] = []

    # -- builders ------------------------------------------------------------
    def add_agent(self, step: AgentStep) -> "PipelineTrace":
        self.agents.append(step)
        return self

    def set_pipeline_position(
        self,
        *,
        current_step: str | None = None,
        upstream_tables: list[str] | None = None,
        layer: str | None = None,
    ) -> "PipelineTrace":
        if current_step is not None:
            self.pipeline_position["current_step"] = current_step
        if upstream_tables is not None:
            self.pipeline_position["upstream_tables"] = list(upstream_tables)
        if layer is not None:
            self.pipeline_position["layer"] = layer
        return self

    def set_final_basis(
        self,
        *,
        source: str = "QuestDB",
        tables: list[str] | None = None,
        query_mode: str = "REST",
        caveats: list[str] | None = None,
    ) -> "PipelineTrace":
        self.final_answer_basis = {
            "source": source,
            "tables": list(tables if tables is not None else self.final_answer_basis["tables"]),
            "query_mode": query_mode,
            "caveats": list(caveats or []),
        }
        return self

    def set_next_actions(self, actions: list[dict[str, Any]]) -> "PipelineTrace":
        self.next_actions = list(actions or [])
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "user_query": self.user_query,
            "domain": self.domain,
            "pipeline_position": self.pipeline_position,
            "agents": [agent.to_dict() for agent in self.agents],
            "final_answer_basis": self.final_answer_basis,
            "next_actions": self.next_actions,
        }


# -- router helpers ----------------------------------------------------------
def classify_domain(query: str) -> tuple[str, str]:
    """Return (domain, intent) for a free-text query using the rule agent classifier.

    Imported lazily so this module stays usable without the full tool layer.
    """
    try:
        from trading_agent.agent.questdb_agent_service import classify
    except Exception:  # pragma: no cover - defensive
        return "system", "unsupported"
    intent = classify(query or "")
    return INTENT_TO_DOMAIN.get(intent, "system"), intent


# Tools that unambiguously identify a domain. The *actual* tools that ran are the
# strongest signal — stronger than a keyword guess or a missing/nested intent — so
# they take priority when deriving the trace domain.
_DOMAIN_TOOL_SETS: tuple[tuple[str, frozenset[str]], ...] = (
    ("event_news", frozenset({"get_symbol_event_news"})),
    ("financial_report", frozenset({
        "get_latest_financial_report", "get_financial_metrics", "get_financial_report_summary",
    })),
    ("backtest", frozenset({
        "get_latest_backtest_metrics", "get_backtest_strategy_comparison",
        "get_backtest_slippage_scenarios", "get_backtest_equity_curve",
    })),
    ("market_summary", frozenset({
        "get_symbol_summary", "get_latest_ohlcv", "get_latest_features",
        "get_latest_signal", "get_ohlcv_window", "get_market_summary",
    })),
    ("system", frozenset({"get_questdb_health", "get_table_health", "query_questdb"})),
)


def domain_from_tool_calls(tool_calls: list[dict[str, Any]]) -> str | None:
    """Return the domain implied by the tools that actually ran, or None."""
    names = {str(call.get("tool") or "") for call in (tool_calls or [])}
    for domain, tools in _DOMAIN_TOOL_SETS:
        if names & tools:
            return domain
    return None


def _intent_from_result(result: dict[str, Any]) -> str | None:
    """Find the rule-agent intent at the top level or nested under data (deep mode)."""
    intent = result.get("intent")
    if not intent and isinstance(result.get("data"), dict):
        intent = result["data"].get("intent")
    return str(intent) if intent else None


def derive_domain(query: str, result: dict[str, Any]) -> tuple[str, str]:
    """Derive (domain, intent) with tool calls taking priority.

    Priority: actual tool calls -> intent (top-level or nested) -> query keywords.
    This keeps the trace correct for the deep/guarded path, where the intent is
    nested under ``data`` and a naive top-level lookup would wrongly fall back to
    ``system``.
    """
    intent = _intent_from_result(result) or ""
    by_tools = domain_from_tool_calls(result.get("tool_calls") or [])
    if by_tools:
        return by_tools, (intent or by_tools)
    if intent:
        return INTENT_TO_DOMAIN.get(intent, "system"), intent
    return classify_domain(query)


def router_reason(domain: str, query: str, intent: str) -> str:
    """Concise, non-private decision reason for the routing step."""
    q = (query or "").lower()
    if domain == "event_news":
        return (
            "Classified as event_news because the query mentions events/news; "
            "market price tools are rejected so no OHLCV proxy is used."
        )
    if domain == "financial_report":
        return "Classified as financial_report because the query references financial-statement terms."
    if domain == "backtest":
        trigger = next((kw for kw in ("compare", "backtest", "strategy", "strategies", "simulate") if kw in q), "backtest")
        return f"Classified as backtest because the query contains '{trigger}'; persisted rows are used (no live Backtrader)."
    if domain == "market_summary":
        return "Classified as market_summary because the query targets a ticker's latest market state."
    if domain == "system":
        if intent == "db_health":
            return "Classified as system because the query asks about QuestDB/table health."
        return "No specialist domain matched; routed to system/diagnostic handling."
    return f"Routed to {domain}."


def router_step(domain: str, query: str, intent: str) -> AgentStep:
    """Build the RouterAgent step for a query."""
    return AgentStep(
        agent_name="RouterAgent",
        role="classify user intent and choose the allowed tool group",
        decision=f"route -> {domain}",
        reason=router_reason(domain, query, intent),
        input_summary=_short(query),
        allowed_tools=list(ALLOWED_TOOLS.get(domain, [])),
        rejected_tools=list(REJECTED_TOOLS.get(domain, [])),
        caveats=[],
    )


def specialist_step(
    domain: str,
    *,
    decision: str,
    reason: str,
    input_summary: str = "",
    tool_calls: list[dict[str, Any]] | None = None,
    caveats: list[str] | None = None,
) -> AgentStep:
    """Build the domain-specialist agent step."""
    agent = DOMAIN_AGENTS.get(domain, DOMAIN_AGENTS["system"])
    return AgentStep(
        agent_name=agent["agent_name"],
        role=agent["role"],
        decision=decision,
        reason=reason,
        input_summary=input_summary,
        allowed_tools=list(ALLOWED_TOOLS.get(domain, [])),
        rejected_tools=list(REJECTED_TOOLS.get(domain, [])),
        caveats=list(caveats or []),
        tool_calls=list(tool_calls or []),
    )


def _short(text: str, limit: int = 160) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


# -- high-level constructors -------------------------------------------------
def trace_from_rule_result(
    query: str,
    result: dict[str, Any],
    *,
    query_mode: str = "REST",
    next_actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a full trace dict from the rule agent's structured result.

    `result` is the dict returned by questdb_agent_service.answer_query (rule) or
    answer_query_deepagents (deep). It carries tool_calls, caveats, status and an
    intent (top-level for rule, nested under ``data`` for deep). Domain is derived
    tool-call-first so the trace matches what actually ran.
    """
    domain, intent = derive_domain(query, result)
    status = str(result.get("status") or "")
    tool_calls = list(result.get("tool_calls") or [])
    caveats = list(result.get("caveats") or [])

    trace = PipelineTrace(query, domain)
    trace.add_agent(router_step(domain, query, intent))

    decision = _specialist_decision(domain, status, tool_calls)
    reason = _specialist_reason(domain, status, intent)
    trace.add_agent(
        specialist_step(
            domain,
            decision=decision,
            reason=reason,
            input_summary=_short(query),
            tool_calls=tool_calls,
            caveats=caveats,
        )
    )
    # Position + final basis reflect the tables the executed tools touched.
    tables = _tables_from_tool_calls(domain, tool_calls)
    trace.set_pipeline_position(upstream_tables=tables)
    trace.set_final_basis(tables=tables, query_mode=query_mode, caveats=caveats)
    if next_actions is not None:
        trace.set_next_actions(next_actions)
    return trace.to_dict()


def _specialist_decision(domain: str, status: str, tool_calls: list[dict[str, Any]]) -> str:
    names = ", ".join(str(call.get("tool")) for call in tool_calls if call.get("tool")) or "none"
    if status in {"ok", "partial"}:
        return f"answered using {names}"
    if status in {"unavailable", "unsupported"}:
        return f"declined / unavailable (tools attempted: {names})"
    return f"error (tools attempted: {names})"


def _specialist_reason(domain: str, status: str, intent: str) -> str:
    if domain == "event_news" and status in {"unavailable", "unsupported"}:
        return "Event/news data is unavailable; OHLCV proxy is forbidden, so the answer is 'unavailable'."
    if domain == "backtest":
        return "Used persisted backtest rows because the agent runtime must not run live Backtrader."
    if domain == "financial_report" and status in {"unavailable", "unsupported"}:
        return "FA tables hold no rows for this symbol; market data is not substituted for financial reports."
    if status in {"ok", "partial"}:
        return "Persisted QuestDB rows satisfied the query; only read-only SELECT/SHOW statements were used."
    return "Query could not be satisfied from persisted QuestDB data under the read-only guardrails."


def _tables_from_tool_calls(domain: str, tool_calls: list[dict[str, Any]]) -> list[str]:
    tool_tables = {
        "get_latest_ohlcv": ["daily_prices"],
        "get_ohlcv_window": ["daily_prices"],
        "get_latest_features": ["feature_snapshots"],
        "get_latest_signal": ["signals"],
        "get_symbol_summary": ["daily_prices", "feature_snapshots", "signals"],
        "get_table_health": ["daily_prices"],
        "get_latest_financial_report": ["fa_balance_sheet", "fa_income_statement", "fa_cash_flow", "fa_notes", "fa_metric_mapping"],
        "get_financial_report_summary": ["fa_balance_sheet", "fa_income_statement", "fa_cash_flow", "fa_notes", "fa_metric_mapping"],
        "get_financial_metrics": ["fa_balance_sheet", "fa_income_statement", "fa_cash_flow", "fa_notes", "fa_metric_mapping"],
        "get_latest_backtest_metrics": ["backtest_runs", "backtest_metrics"],
        "get_backtest_strategy_comparison": ["backtest_runs", "backtest_metrics"],
        "get_backtest_slippage_scenarios": ["backtest_runs", "backtest_metrics"],
        "get_backtest_equity_curve": ["backtest_runs", "backtest_equity_curve"],
        "get_symbol_event_news": ["event_news_items"],
    }
    tables: list[str] = []
    for call in tool_calls:
        for table in tool_tables.get(str(call.get("tool")), []):
            if table not in tables:
                tables.append(table)
    if not tables:
        tables = list(DOMAIN_PIPELINE.get(domain, DOMAIN_PIPELINE["system"])["upstream_tables"])
    return tables
