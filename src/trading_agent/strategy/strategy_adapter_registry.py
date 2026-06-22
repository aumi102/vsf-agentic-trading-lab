from __future__ import annotations

from typing import Any


PENDING_STATUS = "pending_mentor_approval"
INTERFACE_PREVIEW_STATUS = "interface_preview"


# Static, read-only registry of strategy adapter families. Only ``noop`` is
# implemented as an interface preview; every other family stays disabled and
# pending a mentor-approved strategy contract before any real adapter is built.
_REGISTRY: tuple[dict[str, Any], ...] = (
    {
        "family": "noop",
        "status": INTERFACE_PREVIEW_STATUS,
        "implemented": True,
        "enabled": True,
        "requires_mentor_approval": False,
        "notes": "No-op interface preview; emits NO_SIGNAL intents only.",
    },
    {
        "family": "moving_average",
        "status": PENDING_STATUS,
        "implemented": False,
        "enabled": False,
        "requires_mentor_approval": True,
        "notes": "Trend crossover candidate; rules pending mentor approval.",
    },
    {
        "family": "momentum",
        "status": PENDING_STATUS,
        "implemented": False,
        "enabled": False,
        "requires_mentor_approval": True,
        "notes": "Trailing-momentum candidate; rules pending mentor approval.",
    },
    {
        "family": "breakout",
        "status": PENDING_STATUS,
        "implemented": False,
        "enabled": False,
        "requires_mentor_approval": True,
        "notes": "Range-breakout candidate; rules pending mentor approval.",
    },
    {
        "family": "mean_reversion",
        "status": PENDING_STATUS,
        "implemented": False,
        "enabled": False,
        "requires_mentor_approval": True,
        "notes": "Mean-reversion candidate; rules pending mentor approval.",
    },
)


def list_strategy_adapters() -> list[dict[str, Any]]:
    """Return a copy of every registered strategy adapter family."""
    return [dict(entry) for entry in _REGISTRY]


def get_strategy_adapter_family(family: str) -> dict[str, Any]:
    """Look up a family by name.

    Returns ``{"ok": True, "family": <entry>}`` when registered, otherwise
    ``{"ok": False, "reason": "unknown_family:<family>"}``.
    """
    key = str(family or "").strip().lower()
    for entry in _REGISTRY:
        if entry["family"] == key:
            return {"ok": True, "reason": None, "family": dict(entry)}
    return {"ok": False, "reason": f"unknown_family:{family}", "family": None}


def validate_family_enabled(family: str) -> dict[str, Any]:
    """Validate that a family is registered and currently enabled.

    Unknown families block with ``unknown_family:<family>`` and registered but
    disabled families block with ``family_not_enabled:<family>``.
    """
    found = get_strategy_adapter_family(family)
    if not found["ok"]:
        return {"ok": False, "reason": found["reason"]}
    if not found["family"]["enabled"]:
        return {"ok": False, "reason": f"family_not_enabled:{found['family']['family']}"}
    return {"ok": True, "reason": None}
