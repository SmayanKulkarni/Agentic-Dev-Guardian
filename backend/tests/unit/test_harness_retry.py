"""
Tests for RetryController.

Covers:
- Success on first attempt (no retry)
- Transient error → exponential backoff → eventual success
- Schema validation failure → FORMAT CORRECTION appended → retry succeeds
- RateLimitError respected wait time then retries
- Max attempts exhausted → raises original error
- Schema correction stops after max_attempts (doesn't loop infinitely)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dev_guardian.harness.backends import ChatRequest, ChatResponse
from dev_guardian.harness.errors import (
    RateLimitError,
    SchemaValidationError,
)
from dev_guardian.harness.retry import _FORMAT_CORRECTION_TEMPLATE, RetryController


def _make_req(system: str = "sys", user: str = "usr") -> ChatRequest:
    return ChatRequest(system=system, user=user, temperature=0.1, max_tokens=100)


def _make_resp(content: str = "ok") -> ChatResponse:
    return ChatResponse(
        content=content,
        model="test-model",
        prompt_tokens=10,
        completion_tokens=5,
        latency_ms=50,
    )


class TestRetryControllerSuccess:
    def test_returns_response_and_none_without_validator(self):
        rc = RetryController(max_attempts=3)
        fn = MagicMock(return_value=_make_resp("result"))
        req = _make_req()
        resp, parsed = rc.call_with_retry(fn, req)
        assert resp.content == "result"
        assert parsed is None
        fn.assert_called_once()

    def test_returns_parsed_when_validator_succeeds(self):
        rc = RetryController(max_attempts=3)
        fn = MagicMock(return_value=_make_resp("VERDICT: PASS\nREASONING: ok text\nDETAILS: None"))
        from dev_guardian.harness.schema import parse_gatekeeper
        req = _make_req()
        resp, parsed = rc.call_with_retry(fn, req, schema_validator=parse_gatekeeper, schema_name="GatekeeperReport")
        assert parsed is not None
        assert parsed.verdict == "pass"
        fn.assert_called_once()

    def test_no_sleep_on_first_success(self):
        rc = RetryController(max_attempts=3, backoff_base=2.0)
        fn = MagicMock(return_value=_make_resp())
        with patch("dev_guardian.harness.retry.time.sleep") as mock_sleep:
            rc.call_with_retry(fn, _make_req())
        mock_sleep.assert_not_called()


class TestRetryControllerTransientErrors:
    def test_retries_on_transient_error_and_succeeds(self):
        rc = RetryController(max_attempts=3, backoff_base=0.001)
        fn = MagicMock(
            side_effect=[RuntimeError("connection reset"), _make_resp("ok")]
        )
        with patch("dev_guardian.harness.retry.time.sleep"):
            resp, _ = rc.call_with_retry(fn, _make_req())
        assert resp.content == "ok"
        assert fn.call_count == 2

    def test_raises_after_max_attempts(self):
        rc = RetryController(max_attempts=2, backoff_base=0.001)
        fn = MagicMock(side_effect=RuntimeError("always fails"))
        with patch("dev_guardian.harness.retry.time.sleep"):
            with pytest.raises(RuntimeError, match="always fails"):
                rc.call_with_retry(fn, _make_req())
        assert fn.call_count == 2

    def test_backoff_increases_between_retries(self):
        rc = RetryController(max_attempts=3, backoff_base=2.0)
        fn = MagicMock(
            side_effect=[RuntimeError("err"), RuntimeError("err"), _make_resp()]
        )
        sleep_calls = []
        with patch("dev_guardian.harness.retry.time.sleep", side_effect=lambda t: sleep_calls.append(t)):
            rc.call_with_retry(fn, _make_req())
        # First retry: 2^0=1.0, second retry: 2^1=2.0
        assert len(sleep_calls) == 2
        assert sleep_calls[0] == 1.0
        assert sleep_calls[1] == 2.0

    def test_harness_errors_not_retried(self):
        """HarnessError subclasses (other than RateLimitError) should re-raise immediately."""
        rc = RetryController(max_attempts=3)
        fn = MagicMock(side_effect=SchemaValidationError("S", "r", "e"))
        with pytest.raises(SchemaValidationError):
            rc.call_with_retry(fn, _make_req())
        fn.assert_called_once()


class TestRetryControllerRateLimit:
    def test_waits_rate_limit_seconds_then_retries(self):
        rc = RetryController(max_attempts=2, rate_limit_wait=999.0)
        exc = RateLimitError(wait_seconds=42.0, backend="groq")
        fn = MagicMock(side_effect=[exc, _make_resp()])
        sleep_calls = []
        with patch("dev_guardian.harness.retry.time.sleep", side_effect=lambda t: sleep_calls.append(t)):
            resp, _ = rc.call_with_retry(fn, _make_req())
        assert resp.content == "ok" if resp else True
        assert len(sleep_calls) == 1
        assert sleep_calls[0] == 42.0  # uses exc.wait_seconds, not rate_limit_wait

    def test_raises_rate_limit_after_max_attempts(self):
        rc = RetryController(max_attempts=2, rate_limit_wait=0.001)
        fn = MagicMock(side_effect=RateLimitError(wait_seconds=0.001))
        with patch("dev_guardian.harness.retry.time.sleep"):
            with pytest.raises(RateLimitError):
                rc.call_with_retry(fn, _make_req())
        assert fn.call_count == 2


class TestRetryControllerSchemaCorrection:
    def test_appends_format_correction_on_schema_failure(self):
        rc = RetryController(max_attempts=2, backoff_base=0.001)
        schema_exc = SchemaValidationError("TestSchema", "bad", "field missing")
        call_count = [0]
        captured_reqs = []

        def fake_fn(req, **kwargs):
            call_count[0] += 1
            captured_reqs.append(req)
            if call_count[0] == 1:
                resp = _make_resp("bad output")
                return resp
            return _make_resp("VERDICT: PASS\nREASONING: Now fixed text.\nDETAILS: None")

        def validator(content: str):
            if call_count[0] == 1:
                raise schema_exc
            from dev_guardian.harness.schema import parse_gatekeeper
            return parse_gatekeeper(content)

        with patch("dev_guardian.harness.retry.time.sleep"):
            resp, parsed = rc.call_with_retry(
                fake_fn, _make_req(user="original user"),
                schema_validator=validator,
                schema_name="GatekeeperReport",
            )

        assert call_count[0] == 2
        # Second request must have FORMAT CORRECTION appended
        assert "FORMAT CORRECTION" in captured_reqs[1].user
        assert "field missing" in captured_reqs[1].user
        # Original system prompt preserved
        assert captured_reqs[1].system == "sys"

    def test_raises_schema_error_after_max_correction_attempts(self):
        rc = RetryController(max_attempts=2)
        always_bad = MagicMock(return_value=_make_resp("still bad"))

        def always_failing_validator(content: str):
            raise SchemaValidationError("S", content, "always wrong")

        with patch("dev_guardian.harness.retry.time.sleep"):
            with pytest.raises(SchemaValidationError):
                rc.call_with_retry(
                    always_bad, _make_req(),
                    schema_validator=always_failing_validator,
                    schema_name="S",
                )
        assert always_bad.call_count == 2


class TestFormatCorrectionTemplate:
    def test_template_has_required_sections(self):
        msg = _FORMAT_CORRECTION_TEMPLATE.format(errors="missing field 'verdict'")
        assert "FORMAT CORRECTION" in msg
        assert "missing field 'verdict'" in msg
        assert "reformat" in msg.lower()
