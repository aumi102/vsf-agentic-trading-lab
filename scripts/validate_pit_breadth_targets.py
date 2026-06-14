"""Validate the PIT breadth v2 official-source target registry."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.probe_official_disclosures import validate_pit_breadth_registry


DEFAULT_INPUT = ROOT / "config/pit_breadth_validation_v2_targets.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate PIT breadth v2 target registry.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args(argv)

    config = json.loads(args.input.read_text(encoding="utf-8"))
    validate_pit_breadth_registry(config)
    targets = config.get("targets", [])
    print(json.dumps({
        "input": str(args.input),
        "target_count": len(targets),
        "symbols": sorted({str(t.get("symbol", "")).upper() for t in targets}),
        "sectors": sorted({str(t.get("sector", "")) for t in targets}),
        "status": "valid",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
