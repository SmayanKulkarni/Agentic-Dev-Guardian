"""
Tests for HarnessLogger (SQLite-backed call record store).

Covers:
- CallRecord creation and cost estimation
- hash_prompt determinism and uniqueness
- log() writes a row that recent() can read back
- recent() respects n limit and returns newest first
- log() silently swallows write failures (never crashes callers)
- Thread-safe concurrent writes
- DB isolation via temp path per test
"""
from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

from dev_guardian.harness.logger import CallRecord, HarnessLogger


def _temp_logger() -> HarnessLogger:
    """Return a HarnessLogger backed by a fresh temp database."""
    tmp = tempfile.mktemp(suffix=".sqlite")
    return HarnessLogger(db_path=Path(tmp))


def _make_record(**overrides) -> CallRecord:
    defaults = dict(
        skill="gatekeeper",
        backend="groq",
        model="llama-3.3-70b-versatile",
        prompt_tokens=200,
        completion_tokens=100,
        latency_ms=420,
    )
    defaults.update(overrides)
    return CallRecord(**defaults)


class TestCallRecord:
    def test_ts_auto_set(self):
        before = time.time()
        rec = _make_record()
        after = time.time()
        assert before <= rec.ts <= after

    def test_explicit_ts_preserved(self):
        rec = _make_record(ts=1234567890.0)
        assert rec.ts == 1234567890.0

    def test_cost_estimate_groq(self):
        rec = _make_record(backend="groq", prompt_tokens=500_000, completion_tokens=500_000)
        # 1M tokens * $0.59/1M = $0.59
        assert abs(rec.cost_usd_estimate - 0.59) < 0.001

    def test_cost_estimate_anthropic(self):
        rec = _make_record(backend="anthropic", prompt_tokens=500_000, completion_tokens=500_000)
        assert abs(rec.cost_usd_estimate - 3.00) < 0.001

    def test_cost_estimate_zero_tokens(self):
        rec = _make_record(prompt_tokens=0, completion_tokens=0)
        assert rec.cost_usd_estimate == 0.0

    def test_cost_estimate_unknown_backend_uses_fallback(self):
        rec = _make_record(backend="unknown_llm", prompt_tokens=1_000_000, completion_tokens=0)
        assert rec.cost_usd_estimate > 0  # fallback rate applies

    def test_validation_ok_defaults_true(self):
        rec = _make_record()
        assert rec.validation_ok is True

    def test_retry_count_defaults_zero(self):
        rec = _make_record()
        assert rec.retry_count == 0

    def test_error_type_defaults_none(self):
        rec = _make_record()
        assert rec.error_type is None


class TestHarnessLoggerPersistence:
    def test_log_and_retrieve(self):
        hlog = _temp_logger()
        rec = _make_record()
        hlog.log(rec)
        rows = hlog.recent(n=10)
        assert len(rows) == 1
        row = rows[0]
        assert row["skill"] == "gatekeeper"
        assert row["backend"] == "groq"
        assert row["prompt_tokens"] == 200
        assert row["completion_tokens"] == 100
        assert row["latency_ms"] == 420

    def test_recent_returns_newest_first(self):
        hlog = _temp_logger()
        base = 1_700_000_000.0  # non-zero epoch seconds
        for i in range(5):
            hlog.log(_make_record(skill=f"skill_{i}", ts=base + i))
        rows = hlog.recent(n=5)
        skills = [r["skill"] for r in rows]
        assert skills[0] == "skill_4"
        assert skills[-1] == "skill_0"

    def test_recent_respects_n_limit(self):
        hlog = _temp_logger()
        for _ in range(10):
            hlog.log(_make_record())
        rows = hlog.recent(n=3)
        assert len(rows) == 3

    def test_recent_empty_db_returns_empty_list(self):
        hlog = _temp_logger()
        assert hlog.recent() == []

    def test_validation_ok_stored_as_int_readable_as_bool(self):
        hlog = _temp_logger()
        hlog.log(_make_record(validation_ok=False))
        row = hlog.recent(n=1)[0]
        # SQLite stores as 0/1 integer; truthy comparison
        assert not row["validation_ok"]

    def test_multiple_records_all_retrievable(self):
        hlog = _temp_logger()
        for i in range(25):
            hlog.log(_make_record(skill=f"s{i}", prompt_tokens=i * 10))
        rows = hlog.recent(n=100)
        assert len(rows) == 25

    def test_error_type_stored_and_retrieved(self):
        hlog = _temp_logger()
        hlog.log(_make_record(error_type="RateLimitError", validation_ok=False))
        row = hlog.recent(n=1)[0]
        assert row["error_type"] == "RateLimitError"

    def test_cost_estimate_persisted(self):
        hlog = _temp_logger()
        rec = _make_record(prompt_tokens=1_000_000, completion_tokens=0, backend="groq")
        hlog.log(rec)
        row = hlog.recent(n=1)[0]
        assert row["cost_usd_estimate"] > 0


class TestHarnessLoggerRobustness:
    def test_log_failure_does_not_raise(self):
        """If the DB write fails, caller should not get an exception."""
        hlog = _temp_logger()
        # Corrupt the path to trigger a write failure
        hlog._db_path = Path("/nonexistent/path/that/cannot/exist.sqlite")
        # Should silently swallow the error
        hlog.log(_make_record())  # Must not raise

    def test_recent_on_missing_db_returns_empty(self):
        hlog = _temp_logger()
        hlog._db_path = Path("/nonexistent/db.sqlite")
        result = hlog.recent()
        assert result == []

    def test_concurrent_writes_no_data_loss(self):
        hlog = _temp_logger()
        errors: list[Exception] = []

        def writer(i: int):
            try:
                for j in range(5):
                    hlog.log(_make_record(skill=f"s{i}_{j}"))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        rows = hlog.recent(n=200)
        assert len(rows) == 50  # 10 threads × 5 writes each


class TestHashPrompt:
    def test_deterministic(self):
        h1 = HarnessLogger.hash_prompt("system text", "user text")
        h2 = HarnessLogger.hash_prompt("system text", "user text")
        assert h1 == h2

    def test_different_inputs_give_different_hashes(self):
        h1 = HarnessLogger.hash_prompt("sys A", "usr A")
        h2 = HarnessLogger.hash_prompt("sys B", "usr B")
        assert h1 != h2

    def test_hash_length_is_16_chars(self):
        h = HarnessLogger.hash_prompt("s", "u")
        assert len(h) == 16

    def test_order_sensitive(self):
        h1 = HarnessLogger.hash_prompt("A", "B")
        h2 = HarnessLogger.hash_prompt("B", "A")
        assert h1 != h2

    def test_empty_inputs(self):
        h = HarnessLogger.hash_prompt("", "")
        assert len(h) == 16  # still returns a valid hash
