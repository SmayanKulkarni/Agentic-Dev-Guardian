"""
Structured Logging Configuration for Agentic Dev Guardian.

Architecture Blueprint Reference: Phase 1 — Core Python Package.
Uses `structlog` for JSON-structured, machine-parseable logs that can be
consumed by Langfuse tracing in Phase 3.
"""

import structlog


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Return a configured structlog logger instance.

    Args:
        name: The module name to bind to the logger (typically __name__).

    Returns:
        A structlog BoundLogger with JSON rendering and timestamp injection.
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    from typing import cast

    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
