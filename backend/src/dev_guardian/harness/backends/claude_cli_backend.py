"""
Claude CLI backend — shells out to the locally installed `claude` binary.

Unlike every other backend, this one needs no provider API key: it rides
whatever auth the `claude` CLI already has (subscription login or its own
ANTHROPIC_API_KEY), so `audit_codebase` can run through a user's existing
Claude Code access instead of a separate console.anthropic.com key.

Every harness call is a one-shot completion, not an agentic session, so
tool use is disabled — a security-audit backend spawning Bash/Edit against
the repo it's auditing would be its own vulnerability.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time

from dev_guardian.harness.backends import ChatRequest, ChatResponse
from dev_guardian.harness.errors import BackendUnavailableError

# ponytail: fixed list, not a wildcard — a tool the CLI adds later would be
# allowed by default until this list grows too. Upgrade if that bites.
_DISALLOWED_TOOLS = (
    "Bash Edit Write NotebookEdit WebFetch WebSearch Agent Task "
    "Read Grep Glob"
)
_TIMEOUT_SECONDS = 300
_JSON_ONLY_INSTRUCTION = (
    "\n\nRespond with ONLY a single valid JSON object matching the "
    "required schema. No markdown fences, no prose before or after."
)


class ClaudeCLIBackend:
    """Backend implementing LLMBackend by shelling out to `claude -p`."""

    name: str = "claude_cli"
    default_model: str = "sonnet"
    context_window: int = 200_000

    def __init__(self) -> None:
        self._binary = shutil.which("claude")
        if self._binary is None:
            raise BackendUnavailableError(
                "claude_cli", "`claude` binary not found on PATH"
            )

    def complete(self, req: ChatRequest, *, model: str | None = None) -> ChatResponse:
        """Execute a completion via a non-interactive `claude -p` subprocess."""
        target_model = model or self.default_model
        system = req.system
        if req.response_schema is not None:
            system = system + _JSON_ONLY_INSTRUCTION

        cmd = [
            self._binary,
            "-p",
            req.user,
            "--system-prompt",
            system,
            "--model",
            target_model,
            "--output-format",
            "json",
            "--disallowedTools",
            _DISALLOWED_TOOLS,
        ]

        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise BackendUnavailableError(
                self.name, f"claude CLI timed out after {_TIMEOUT_SECONDS}s"
            ) from exc
        latency_ms = int((time.monotonic() - t0) * 1000)

        if proc.returncode != 0:
            raise BackendUnavailableError(
                self.name, f"claude CLI exited {proc.returncode}: {proc.stderr[:500]}"
            )

        try:
            raw = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise BackendUnavailableError(
                self.name, f"claude CLI produced non-JSON output: {proc.stdout[:500]}"
            ) from exc

        if raw.get("is_error"):
            raise BackendUnavailableError(self.name, str(raw.get("result", raw)))

        usage = raw.get("usage") or {}
        model_usage = next(iter((raw.get("modelUsage") or {}).values()), {})

        return ChatResponse(
            content=raw.get("result", ""),
            model=model_usage.get("canonicalModel", target_model),
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            latency_ms=latency_ms,
        )

    def count_tokens(self, text: str) -> int:
        """Approximate token count (word-based heuristic; matches other backends)."""
        words = len(text.split())
        return max(1, int(words / 0.75))
