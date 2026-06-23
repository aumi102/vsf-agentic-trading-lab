"""Safe DeepAgents/OpenAI environment diagnostic.

This script never prints full API keys. By default it performs import/env checks
only. Use ``--live`` for a minimal LLM call with redacted errors.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass


def redact(text: object) -> str:
    """Redact OpenAI-style credential fragments from arbitrary text."""
    return re.sub(r"sk-(?:proj-)?[A-Za-z0-9_*\-]+", "sk-<redacted>", str(text))


def _key_info() -> tuple[bool, int, str, bool, bool]:
    key = os.environ.get("OPENAI_API_KEY") or ""
    present = bool(key)
    suffix = key[-4:] if present and len(key) >= 4 else ""
    expected_prefix = key.startswith("sk-") or key.startswith("sk-proj-")
    project_prefix = key.startswith("sk-proj-")
    return present, len(key), suffix, expected_prefix, project_prefix


def _import_available(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def print_env() -> None:
    present, length, suffix, expected_prefix, project_prefix = _key_info()
    conda_env = os.environ.get("CONDA_DEFAULT_ENV") or ""
    print(f"OPENAI_API_KEY_PRESENT={present}")
    print(f"OPENAI_API_KEY_LENGTH={length}")
    print(f"OPENAI_API_KEY_SUFFIX4={suffix if present else ''}")
    print(f"OPENAI_API_KEY_EXPECTED_PREFIX={expected_prefix}")
    print(f"OPENAI_API_KEY_PROJECT_PREFIX={project_prefix}")
    if present and not expected_prefix:
        print("OPENAI_API_KEY_PREFIX_WARNING=key does not start with sk- or sk-proj-")
    print(f"VSF_DEEPAGENTS_MODEL={os.environ.get('VSF_DEEPAGENTS_MODEL') or ''}")
    print(f"PYTHON_EXECUTABLE={sys.executable}")
    print(f"CONDA_DEFAULT_ENV={conda_env}")
    for module in ("deepagents", "langchain", "langchain_openai", "openai"):
        print(f"IMPORT_{module}={_import_available(module)}")


def live_check(model: str | None, timeout_seconds: int) -> int:
    present, *_ = _key_info()
    if not present:
        print("LIVE_STATUS=SKIPPED")
        print("LIVE_CAVEAT=OPENAI_API_KEY is not set")
        return 0
    model_name = model or os.environ.get("VSF_DEEPAGENTS_MODEL") or "gpt-4.1-mini"
    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(model=model_name, temperature=0, timeout=timeout_seconds)
        response = llm.invoke("Reply with exactly: OK")
        content = getattr(response, "content", "")
        print(f"LIVE_STATUS=OK")
        print(f"LIVE_MODEL={model_name}")
        print(f"LIVE_RESPONSE={str(content).strip()[:80]}")
        return 0
    except Exception as exc:
        safe = redact(exc)
        credential_failure = any(token in safe.lower() for token in ("401", "invalid_api_key", "incorrect api key"))
        print("LIVE_STATUS=FAILED_CREDENTIAL" if credential_failure else "LIVE_STATUS=FAILED")
        print(f"LIVE_MODEL={model_name}")
        if credential_failure:
            print("LIVE_DIAGNOSIS=OpenAI credential is invalid or stale in this process. Restart shell/backend after setting OPENAI_API_KEY.")
        print(f"LIVE_ERROR={safe}")
        return 2 if credential_failure else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely inspect DeepAgents/OpenAI environment.")
    parser.add_argument("--live", action="store_true", help="Make a minimal live LLM call.")
    parser.add_argument("--model", default=None, help="Override model for --live.")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    args = parser.parse_args()
    print_env()
    if args.live:
        return live_check(args.model, args.timeout_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
