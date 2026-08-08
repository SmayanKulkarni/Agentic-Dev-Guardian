"""
Phase 1 — Unit tests for RateLimiter token-bucket logic.
"""
from __future__ import annotations

from dev_guardian.harness.rate_limiter import RateLimiter


class TestRateLimiter:
    def test_first_request_always_passes(self):
        limiter = RateLimiter(overrides={"groq": 10_000})
        wait = limiter.check_and_consume("groq", 100)
        assert wait == 0.0

    def test_budget_exhaustion_returns_positive_wait(self):
        limiter = RateLimiter(overrides={"groq": 100})
        limiter.check_and_consume("groq", 90)
        wait = limiter.check_and_consume("groq", 20)
        assert wait > 0

    def test_budget_refills_over_time(self):
        limiter = RateLimiter(overrides={"groq": 50})
        limiter.check_and_consume("groq", 50)
        wait = limiter.check_and_consume("groq", 1)
        assert wait > 0
        # Simulate time passing by clearing the internal deque
        limiter._buckets["groq"]._usage.clear()
        wait2 = limiter.check_and_consume("groq", 1)
        assert wait2 == 0.0

    def test_unknown_backend_uses_default_limit(self):
        limiter = RateLimiter()
        wait = limiter.check_and_consume("unknown_backend", 100)
        assert wait == 0.0

    def test_multiple_backends_are_independent(self):
        limiter = RateLimiter(overrides={"groq": 50, "anthropic": 50})
        limiter.check_and_consume("groq", 50)
        wait_groq = limiter.check_and_consume("groq", 1)
        wait_anthropic = limiter.check_and_consume("anthropic", 1)
        assert wait_groq > 0
        assert wait_anthropic == 0.0

    def test_thread_safety_no_exception(self):
        import threading
        limiter = RateLimiter(overrides={"groq": 10_000})
        errors: list[Exception] = []

        def worker():
            try:
                for _ in range(20):
                    limiter.check_and_consume("groq", 10)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []


class TestEnvTpmOverride:
    """GUARDIAN_TPM replaces the per-provider defaults for every backend."""

    def test_env_override_applies_to_all_backends(self, monkeypatch):
        monkeypatch.setenv("GUARDIAN_TPM", "500")
        limiter = RateLimiter()
        assert limiter.check_and_consume("groq", 400) == 0.0
        assert limiter.check_and_consume("groq", 400) > 0.0

    def test_explicit_overrides_beat_the_env(self, monkeypatch):
        monkeypatch.setenv("GUARDIAN_TPM", "500")
        limiter = RateLimiter(overrides={"groq": 5_000})
        assert limiter.check_and_consume("groq", 4_000) == 0.0

    def test_garbage_env_is_ignored(self, monkeypatch):
        monkeypatch.setenv("GUARDIAN_TPM", "lots")
        limiter = RateLimiter()
        assert limiter.check_and_consume("groq", 11_000) == 0.0
