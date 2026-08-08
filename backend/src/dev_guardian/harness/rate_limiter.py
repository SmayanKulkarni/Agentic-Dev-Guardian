"""
Token-bucket rate limiter — prevents Groq 12k TPM 429 errors.

Reads the per-backend TPM budget from GuardianSettings and tracks
consumed tokens with a simple sliding-window approach.
Thread-safe via threading.Lock.
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from dev_guardian.core.logging import get_logger

logger = get_logger(__name__)

# Default TPM limits per backend (tokens per minute)
_DEFAULT_TPM: dict[str, int] = {
    "groq": 12_000,           # Groq on-demand tier hard limit
    "anthropic": 40_000,      # Claude conservative default
    "openai": 60_000,         # GPT-4o conservative default
    "ollama": 10_000_000,     # local server, no real TPM ceiling
    "local": 10_000_000,      # self-hosted engine, no real TPM ceiling
    "huggingface": 60_000,    # shared router tier, conservative default
}


def _env_override() -> dict[str, int]:
    """
    GUARDIAN_TPM — one tokens-per-minute ceiling for every backend (ticket 09).

    The defaults above suit the vendors' published tiers; a paid tier or a
    self-hosted engine has different limits, and the operator is the only one
    who knows them. Ignored when unset or unparseable.
    """
    raw = os.environ.get("GUARDIAN_TPM", "").strip()
    if not raw:
        return {}
    try:
        value = int(raw)
    except ValueError:
        logger.warning("invalid_tpm_env", value=raw)
        return {}
    if value <= 0:
        return {}
    return dict.fromkeys(_DEFAULT_TPM, value)


@dataclass
class _TokenBucket:
    tpm_limit: int
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _usage: deque[tuple[float, int]] = field(default_factory=deque, repr=False)

    def consume(self, tokens: int) -> float:
        """
        Attempt to consume `tokens` from the bucket.

        Returns 0.0 if successful, or the number of seconds to wait
        before the budget refills enough to accommodate the request.
        """
        now = time.monotonic()
        window = 60.0

        with self._lock:
            # Evict usage records older than 60 seconds
            while self._usage and (now - self._usage[0][0]) >= window:
                self._usage.popleft()

            used = sum(t for _, t in self._usage)
            remaining = self.tpm_limit - used

            if tokens <= remaining:
                self._usage.append((now, tokens))
                return 0.0

            # Calculate how long until enough budget frees up
            if self._usage:
                oldest_ts, oldest_tokens = self._usage[0]
                wait = window - (now - oldest_ts) + 0.5  # 0.5s buffer
            else:
                wait = 1.0

            logger.warning(
                "rate_limiter_wait",
                used=used,
                limit=self.tpm_limit,
                requested=tokens,
                wait_seconds=round(wait, 1),
            )
            return wait


class RateLimiter:
    """
    Per-backend token-bucket rate limiter.

    Usage::
        limiter = RateLimiter()
        wait = limiter.check("groq", estimated_tokens=500)
        if wait > 0:
            time.sleep(wait)
        limiter.record("groq", actual_tokens=487)
    """

    def __init__(self, overrides: dict[str, int] | None = None) -> None:
        limits = {**_DEFAULT_TPM, **_env_override(), **(overrides or {})}
        self._buckets: dict[str, _TokenBucket] = {
            name: _TokenBucket(tpm_limit=tpm) for name, tpm in limits.items()
        }

    def _bucket(self, backend: str) -> _TokenBucket:
        if backend not in self._buckets:
            fallback = _env_override().get(backend, 10_000)
            self._buckets[backend] = _TokenBucket(
                tpm_limit=_DEFAULT_TPM.get(backend, fallback)
            )
        return self._buckets[backend]

    def check_and_consume(self, backend: str, tokens: int) -> float:
        """
        Check if `tokens` fit in the budget and consume them if so.

        Returns seconds to wait (0 = proceed immediately).
        """
        return self._bucket(backend).consume(tokens)

    def wait_if_needed(self, backend: str, tokens: int) -> None:
        """Block until the rate limit allows `tokens` to be consumed."""
        while True:
            wait = self.check_and_consume(backend, tokens)
            if wait <= 0:
                return
            logger.info("rate_limiter_sleeping", backend=backend, seconds=round(wait, 1))
            time.sleep(wait)


# Module-level singleton — shared across all SkillRouter calls
_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Return the module-level RateLimiter singleton."""
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter()
    return _limiter
