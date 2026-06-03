from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProbeTarget:
    source_name: str
    name: str
    dataset: str
    url: str
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    request_params: dict[str, Any] = field(default_factory=dict)
    likely_canonical_tables: list[str] = field(default_factory=list)
    terms_notes: str = ""
    auth_env: str = ""
    auth_header: str = "Authorization"
    auth_prefix: str = ""
    auth_in: str = "header"
    auth_param: str = ""
    verify_ssl: bool = True
    expected_content_type_contains: list[str] = field(default_factory=list)
    expected_body_startswith_json: bool = False
    reject_body_contains: list[str] = field(default_factory=list)
    min_body_bytes: int = 0
    config_file: str = ""

    def auth_token_from_env(self) -> str | None:
        if not self.auth_env:
            return None
        return os.getenv(self.auth_env)


def load_probe_targets(path: str | Path) -> dict[str, list[ProbeTarget]]:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid source probe config JSON at {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"Invalid source probe config at {path}: top-level value must be an object.")

    targets: dict[str, list[ProbeTarget]] = {}
    for source_name, entries in raw.items():
        if not isinstance(source_name, str):
            raise ValueError(f"Invalid source probe config at {path}: source names must be strings.")
        if not isinstance(entries, list):
            raise ValueError(f"Invalid source probe config at {path}: `{source_name}` must be a list.")
        targets[source_name] = [_target_from_dict(path, source_name, index, entry) for index, entry in enumerate(entries)]
    return targets


def _target_from_dict(path: Path, source_name: str, index: int, entry: Any) -> ProbeTarget:
    if not isinstance(entry, dict):
        raise ValueError(f"Invalid target #{index} for `{source_name}` in {path}: target must be an object.")
    name = _string_field(entry, "name", default=f"{source_name}_target_{index}")
    dataset = _string_field(entry, "dataset", default=name)
    url = _string_field(entry, "url", default="")
    method = _string_field(entry, "method", default="GET").upper()
    headers = _dict_field(entry, "headers")
    request_params = _dict_field(entry, "request_params")
    likely_tables = _string_list_field(entry, "likely_canonical_tables")
    terms_notes = _string_field(entry, "terms_notes", default="")
    auth_env = _string_field(entry, "auth_env", default="")
    auth_header = _string_field(entry, "auth_header", default="Authorization")
    auth_prefix = _string_field(entry, "auth_prefix", default="")
    auth_in = _string_field(entry, "auth_in", default="header") or "header"
    if auth_in not in {"header", "query"}:
        raise ValueError(f"Invalid source probe target field `auth_in`: expected `header` or `query`.")
    auth_param = _string_field(entry, "auth_param", default="")
    verify_ssl = _bool_field(entry, "verify_ssl", default=True)
    expected_content_type_contains = _string_or_string_list_field(entry, "expected_content_type_contains")
    expected_body_startswith_json = _bool_field(entry, "expected_body_startswith_json", default=False)
    reject_body_contains = _string_list_field(entry, "reject_body_contains")
    min_body_bytes = _int_field(entry, "min_body_bytes", default=0)
    return ProbeTarget(
        source_name=source_name,
        name=name,
        dataset=dataset,
        url=url,
        method=method,
        headers={str(key): str(value) for key, value in headers.items()},
        request_params=request_params,
        likely_canonical_tables=likely_tables,
        terms_notes=terms_notes,
        auth_env=auth_env,
        auth_header=auth_header,
        auth_prefix=auth_prefix,
        auth_in=auth_in,
        auth_param=auth_param,
        verify_ssl=verify_ssl,
        expected_content_type_contains=expected_content_type_contains,
        expected_body_startswith_json=expected_body_startswith_json,
        reject_body_contains=reject_body_contains,
        min_body_bytes=min_body_bytes,
        config_file=str(path),
    )


def _string_field(entry: dict[str, Any], key: str, default: str = "") -> str:
    value = entry.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"Invalid source probe target field `{key}`: expected string.")
    return value


def _dict_field(entry: dict[str, Any], key: str) -> dict[str, Any]:
    value = entry.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"Invalid source probe target field `{key}`: expected object.")
    return value


def _bool_field(entry: dict[str, Any], key: str, default: bool) -> bool:
    value = entry.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"Invalid source probe target field `{key}`: expected boolean.")
    return value


def _int_field(entry: dict[str, Any], key: str, default: int) -> int:
    value = entry.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Invalid source probe target field `{key}`: expected integer.")
    return value


def _string_list_field(entry: dict[str, Any], key: str) -> list[str]:
    value = entry.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Invalid source probe target field `{key}`: expected list of strings.")
    return list(value)


def _string_or_string_list_field(entry: dict[str, Any], key: str) -> list[str]:
    value = entry.get(key, [])
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Invalid source probe target field `{key}`: expected string or list of strings.")
    return list(value)
