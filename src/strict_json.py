"""Strict JSON loading for untrusted certificate files.

Rejects duplicate keys, NaN/Infinity, excessive nesting, and non-object roots.
This module deliberately has no dependency on the certificate producer.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Iterable
import json

class StrictJSONError(ValueError):
    pass

def _pairs(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise StrictJSONError(f"duplicate key: {key!r}")
        out[key] = value
    return out

def _constant(token: str) -> Any:
    raise StrictJSONError(f"non-finite numeric token: {token}")

def _depth(value: Any, limit: int, depth: int = 0) -> None:
    if depth > limit:
        raise StrictJSONError(f"JSON nesting exceeds {limit}")
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise StrictJSONError("object key is not a string")
            _depth(v, limit, depth + 1)
    elif isinstance(value, list):
        for v in value:
            _depth(v, limit, depth + 1)

def loads_strict(data: str, *, max_bytes: int = 64 * 1024 * 1024,
                 max_depth: int = 256) -> dict[str, Any]:
    if len(data.encode('utf-8')) > max_bytes:
        raise StrictJSONError(f"JSON exceeds {max_bytes} bytes")
    try:
        value = json.loads(data, object_pairs_hook=_pairs, parse_constant=_constant)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise StrictJSONError(str(exc)) from exc
    if not isinstance(value, dict):
        raise StrictJSONError("top-level JSON value must be an object")
    _depth(value, max_depth)
    return value

def load_strict(path: str | Path, **kwargs: Any) -> dict[str, Any]:
    p = Path(path)
    max_bytes = kwargs.get("max_bytes", 64 * 1024 * 1024)
    if type(max_bytes) is not int or max_bytes < 0:
        raise StrictJSONError("invalid byte limit")
    try:
        size = p.stat().st_size
    except OSError as exc:
        raise StrictJSONError(str(exc)) from exc
    if size > max_bytes:
        raise StrictJSONError(f"JSON exceeds {max_bytes} bytes")
    try:
        data = p.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise StrictJSONError(str(exc)) from exc
    return loads_strict(data, **kwargs)
