"""
HarnessLogger — SQLite-backed call record store.

Writes one row per LLM call so `dev-guardian logs` can surface latency,
token usage, retry counts, and validation failures without Langfuse.

Schema (CallRecord):
    id, ts, skill, backend, model, prompt_hash, prompt_tokens,
    completion_tokens, latency_ms, validation_ok, retry_count,
    error_type, cost_usd_estimate
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dev_guardian.core.logging import get_logger

logger = get_logger(__name__)

_DB_PATH = Path(os.environ.get("GUARDIAN_LOG_DB", "~/.local/share/guardian/harness.sqlite")).expanduser()

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS call_records (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                REAL    NOT NULL,
    skill             TEXT    NOT NULL,
    backend           TEXT    NOT NULL,
    model             TEXT    NOT NULL,
    prompt_hash       TEXT    NOT NULL,
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms        INTEGER NOT NULL DEFAULT 0,
    validation_ok     INTEGER NOT NULL DEFAULT 1,
    retry_count       INTEGER NOT NULL DEFAULT 0,
    error_type        TEXT,
    cost_usd_estimate REAL    NOT NULL DEFAULT 0.0
)
"""

# Rough cost estimates per 1M tokens (input+output blended)
_COST_PER_1M: dict[str, float] = {
    "groq": 0.59,
    "anthropic": 3.00,
    "openai": 0.60,
}


@dataclass
class CallRecord:
    skill: str
    backend: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    validation_ok: bool = True
    retry_count: int = 0
    error_type: str | None = None
    prompt_hash: str = ""
    ts: float = 0.0
    cost_usd_estimate: float = 0.0

    def __post_init__(self) -> None:
        if not self.ts:
            self.ts = time.time()
        if not self.prompt_hash:
            self.prompt_hash = ""
        rate = _COST_PER_1M.get(self.backend, 1.0)
        total_tokens = self.prompt_tokens + self.completion_tokens
        self.cost_usd_estimate = (total_tokens / 1_000_000) * rate


class HarnessLogger:
    """
    Logs every harness LLM call to a local SQLite database.

    Usage::
        hlog = HarnessLogger()
        hlog.log(CallRecord(...))
        records = hlog.recent(n=20)
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path))

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(_CREATE_TABLE)
            conn.commit()

    def log(self, record: CallRecord) -> None:
        """Insert a CallRecord into the database."""
        try:
            row = asdict(record)
            row["validation_ok"] = int(row["validation_ok"])
            columns = ", ".join(row.keys())
            placeholders = ", ".join("?" for _ in row)
            sql = f"INSERT INTO call_records ({columns}) VALUES ({placeholders})"
            with self._conn() as conn:
                conn.execute(sql, list(row.values()))
                conn.commit()
        except Exception as exc:
            logger.warning("harness_logger_write_failed", error=str(exc))

    def recent(self, n: int = 20) -> list[dict[str, Any]]:
        """Return the `n` most recent call records as dicts."""
        try:
            with self._conn() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM call_records ORDER BY ts DESC LIMIT ?", (n,)
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception as exc:
            logger.warning("harness_logger_read_failed", error=str(exc))
            return []

    @staticmethod
    def hash_prompt(system: str, user: str) -> str:
        """Return a short SHA-256 fingerprint of the prompt for dedup tracking."""
        combined = f"{system}\n{user}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]


# Module-level singleton
_hlogger: HarnessLogger | None = None


def get_harness_logger() -> HarnessLogger:
    global _hlogger
    if _hlogger is None:
        _hlogger = HarnessLogger()
    return _hlogger
