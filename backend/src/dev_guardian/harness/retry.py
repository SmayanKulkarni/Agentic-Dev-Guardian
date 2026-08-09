"""
RetryController — exponential back-off + schema-correction retries.

On transient errors (rate-limit, timeout): exponential back-off up to
max_attempts.

On schema validation failure: appends a FORMAT CORRECTION user message
with the Pydantic error and re-invokes the backend. This is the
feedback-loop pattern from harness-patterns.md §4 (back-pressure).
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from dev_guardian.core.logging import get_logger
from dev_guardian.harness.errors import (
    HarnessError,
    RateLimitError,
    SchemaValidationError,
)

if TYPE_CHECKING:
    from dev_guardian.harness.backends import ChatRequest, ChatResponse

logger = get_logger(__name__)

_FORMAT_CORRECTION_TEMPLATE = (
    "\n\n---\nFORMAT CORRECTION REQUIRED\n"
    "Your previous response failed schema validation with these errors:\n{errors}\n\n"
    "Please reformat your response to exactly match the required structure."
)


@dataclass
class RetryController:
    """
    Executes a callable with exponential back-off and schema-correction retries.

    Args:
        max_attempts: Total attempts before raising (includes first try).
        backoff_base: Multiplier for exponential back-off delay.
        rate_limit_wait: Seconds to wait on explicit RateLimitError.
    """

    max_attempts: int = 3
    backoff_base: float = 2.0
    rate_limit_wait: float = 65.0

    def call_with_retry(
        self,
        fn: Callable[..., ChatResponse],
        req: ChatRequest,
        *,
        schema_validator: Callable[[str], Any] | None = None,
        schema_name: str = "unknown",
        extra_kwargs: dict[str, Any] | None = None,
    ) -> tuple[ChatResponse, Any]:
        """
        Call `fn(req, **extra_kwargs)` with retry logic.

        Args:
            fn: The backend.complete callable.
            req: ChatRequest to pass on each attempt.
            schema_validator: Optional callable that validates the response
                content; raises SchemaValidationError on failure.
            schema_name: Name used in error messages.
            extra_kwargs: Additional keyword args forwarded to `fn`.

        Returns:
            Tuple of (ChatResponse, parsed_schema_result).
            If no schema_validator provided, parsed_schema_result is None.
        """
        kwargs = extra_kwargs or {}
        last_exc: Exception | None = None
        current_req = req

        for attempt in range(1, self.max_attempts + 1):
            try:
                resp = fn(current_req, **kwargs)

                if schema_validator is not None:
                    try:
                        parsed = schema_validator(resp.content)
                    except SchemaValidationError as val_exc:
                        if attempt < self.max_attempts:
                            logger.warning(
                                "retry_schema_correction",
                                attempt=attempt,
                                schema=schema_name,
                                errors=val_exc.errors[:100],
                            )
                            from dev_guardian.harness.backends import ChatRequest as CR
                            correction = _FORMAT_CORRECTION_TEMPLATE.format(
                                errors=val_exc.errors
                            )
                            current_req = CR(
                                system=current_req.system,
                                user=current_req.user + correction,
                                temperature=current_req.temperature,
                                max_tokens=current_req.max_tokens,
                                stop=current_req.stop,
                                response_schema=current_req.response_schema,
                            )
                            last_exc = val_exc
                            continue
                        raise
                    return resp, parsed

                return resp, None

            except RateLimitError as exc:
                wait = exc.wait_seconds or self.rate_limit_wait
                logger.warning(
                    "retry_rate_limit",
                    attempt=attempt,
                    wait=wait,
                )
                if attempt < self.max_attempts:
                    time.sleep(wait)
                    last_exc = exc
                    continue
                raise

            except HarnessError:
                raise

            except Exception as exc:
                delay = self.backoff_base ** (attempt - 1)
                logger.warning(
                    "retry_transient_error",
                    attempt=attempt,
                    error=str(exc)[:120],
                    backoff=delay,
                )
                if attempt < self.max_attempts:
                    time.sleep(delay)
                    last_exc = exc
                    continue
                raise

        # Should not reach here, but satisfy the type checker
        assert last_exc is not None
        raise last_exc
