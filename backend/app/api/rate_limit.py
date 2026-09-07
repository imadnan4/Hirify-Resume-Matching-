"""Fixed-window rate limiter for public endpoints. In-memory; single process default.

Reads APPLY_RATE_LIMIT_PER_MIN from the environment on every call so tests can
retune it with monkeypatch. For multi-worker deploys, front with the platform
rate limiter and keep this as defense in depth.
"""
import os
import time

_hits: dict[str, list[float]] = {}


def check_rate_limit(key: str, limit: int | None = None, window_s: int = 60) -> bool:
    """True when the call is allowed (and recorded). False when over the limit."""
    if limit is None:
        try:
            limit = int(os.getenv("APPLY_RATE_LIMIT_PER_MIN", "30"))
        except ValueError:
            limit = 30
    now = time.monotonic()
    calls = [t for t in _hits.get(key, []) if now - t < window_s]
    if len(calls) >= limit:
        _hits[key] = calls
        return False
    calls.append(now)
    _hits[key] = calls
    return True


def reset_rate_limits() -> None:
    _hits.clear()
