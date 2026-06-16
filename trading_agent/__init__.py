"""Local checkout shim for the src-layout trading_agent package."""

from __future__ import annotations

from pathlib import Path


_SRC_PACKAGE = Path(__file__).resolve().parent.parent / "src" / "trading_agent"
if _SRC_PACKAGE.is_dir():
    __path__.append(str(_SRC_PACKAGE))
