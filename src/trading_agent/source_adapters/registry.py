from __future__ import annotations

from trading_agent.source_adapters.base import SourceAdapter
from trading_agent.source_adapters.fred_adapter import FredAdapter
from trading_agent.source_adapters.hose_adapter import HoseAdapter
from trading_agent.source_adapters.vbma_adapter import VbmaAdapter
from trading_agent.source_adapters.vietcap_iq_adapter import VietcapIqAdapter


ADAPTERS: dict[str, type[SourceAdapter]] = {
    "hose": HoseAdapter,
    "vietcap_iq": VietcapIqAdapter,
    "vbma": VbmaAdapter,
    "fred": FredAdapter,
}

DEFAULT_SOURCES = list(ADAPTERS.keys())


def get_adapter_class(source_name: str) -> type[SourceAdapter]:
    try:
        return ADAPTERS[source_name]
    except KeyError as exc:
        known = ", ".join(sorted(ADAPTERS))
        raise ValueError(f"Unknown source `{source_name}`. Known sources: {known}") from exc


def create_adapters(source_names: list[str], raw_store=None, probe_targets_by_source: dict[str, list[object]] | None = None) -> list[SourceAdapter]:
    probe_targets_by_source = probe_targets_by_source or {}
    return [
        get_adapter_class(source_name)(raw_store=raw_store, probe_targets=probe_targets_by_source.get(source_name, []))
        for source_name in source_names
    ]


def parse_source_names(value: str | None) -> list[str]:
    if value is None or value.strip().lower() == "all":
        return DEFAULT_SOURCES.copy()
    names = [part.strip() for part in value.split(",") if part.strip()]
    for name in names:
        get_adapter_class(name)
    return names
