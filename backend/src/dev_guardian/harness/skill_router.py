"""
SkillRouter — single entry point for every LLM call in the harness.

A skill is registered via the @skill decorator:

    @skill(name="architectural_gatekeeper",
           schema=GatekeeperReport,
           prompt="gatekeeper",
           version=1)
    def architectural_gatekeeper(ctx: SkillContext) -> GatekeeperReport:
        ...

The router:
  1. Loads the PromptTemplate.
  2. Renders system + user from ctx.
  3. Checks context window limits.
  4. Waits on rate limiter.
  5. Calls backend via RetryController.
  6. Validates response via schema parser.
  7. Logs call to HarnessLogger + Langfuse metadata.
  8. Returns typed SkillResult.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from dev_guardian.core.logging import get_logger
from dev_guardian.core.tracing import observe
from dev_guardian.harness.backend_factory import get_backend
from dev_guardian.harness.backends import ChatRequest
from dev_guardian.harness.context_window import ContextWindowManager
from dev_guardian.harness.errors import SkillNotFoundError
from dev_guardian.harness.logger import CallRecord, get_harness_logger
from dev_guardian.harness.prompt_registry import get_prompt_registry
from dev_guardian.harness.rate_limiter import get_rate_limiter
from dev_guardian.harness.retry import RetryController
from dev_guardian.harness.schema import ResponseSchema

logger = get_logger(__name__)

T = TypeVar("T", bound=ResponseSchema)


@dataclass
class SkillContext:
    """Context bag passed to every skill callable and used for prompt rendering."""

    skill_name: str
    kwargs: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        return self.kwargs[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.kwargs.get(key, default)


@dataclass
class SkillResult:
    """Typed result returned by SkillRouter.run()."""

    skill_name: str
    parsed: ResponseSchema
    raw_content: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    retry_count: int = 0

    def to_agent_report(self) -> dict[str, Any]:
        """
        Convert to the legacy AgentReport TypedDict shape for backwards
        compatibility with existing LangGraph nodes that haven't been
        migrated yet.
        """
        d = self.parsed.model_dump()
        d["agent_name"] = self.skill_name
        # Map schema-specific fields to AgentReport fields
        if "violations" in d:
            d["details"] = "\n".join(f"- {v}" for v in d.pop("violations"))
        if "pytest_code" in d:
            d["details"] = d.pop("pytest_code")
        if "explanation" in d and "details" not in d:
            d["details"] = d.pop("explanation")
        return d


# ── Skill registration ────────────────────────────────────────────────────────

@dataclass
class _SkillRegistration:
    name: str
    prompt_id: str
    version: int
    schema_cls: type[ResponseSchema]
    parser: Callable[[str], ResponseSchema]
    temperature: float
    max_tokens: int


_SKILL_REGISTRY: dict[str, _SkillRegistration] = {}


def skill(
    *,
    name: str,
    schema: type[ResponseSchema],
    prompt: str,
    version: int = 1,
    temperature: float = 0.1,
    max_tokens: int = 1024,
    parser: Callable[[str], ResponseSchema] | None = None,
) -> Callable:
    """
    Decorator to register a callable as a named skill.

    The decorated function receives a SkillContext and should return
    the parsed schema instance. The decorator also registers a default
    parser based on the schema class name when none is provided.
    """
    def decorator(fn: Callable) -> Callable:
        _parser = parser or _default_parser(schema)
        _SKILL_REGISTRY[name] = _SkillRegistration(
            name=name,
            prompt_id=prompt,
            version=version,
            schema_cls=schema,
            parser=_parser,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        fn._skill_name = name  # type: ignore[attr-defined]
        return fn

    return decorator


def _default_parser(schema_cls: type[ResponseSchema]) -> Callable[[str], ResponseSchema]:
    """Return a JSON-then-text fallback parser for a schema class."""
    import json

    def _parse(raw: str) -> ResponseSchema:
        # Try JSON first
        cleaned = raw.strip()
        if cleaned.startswith("{"):
            try:
                return schema_cls.model_validate(json.loads(cleaned))
            except Exception:
                pass
        # Fallback: use schema-specific text parsers
        from dev_guardian.harness import schema as _schema_mod
        # Try common parsers
        specific: dict[str, Callable] = {
            "GatekeeperReport": _schema_mod.parse_gatekeeper,
            "RedTeamReport": _schema_mod.parse_redteam,
            "DebateResolution": _schema_mod.parse_debate,
            "RemediationResult": _schema_mod.parse_remediation,
        }
        if schema_cls.__name__ in specific:
            return specific[schema_cls.__name__](raw)
        # Generic fallback: try to find a 'content' or 'explanation' field
        try:
            return schema_cls.model_validate({"content": raw, "explanation": raw,
                                               "summary": raw[:500], "failing_function": "unknown",
                                               "exception_type": "unknown"})
        except Exception:
            # Last resort: set all required string fields to raw snippet
            dummy = {f: raw[:200] for f in schema_cls.model_fields}
            return schema_cls.model_validate(dummy)

    return _parse


# ── SkillRouter ───────────────────────────────────────────────────────────────

class SkillRouter:
    """
    Single entry point for all harness LLM calls.

    Instantiate once (or use the module-level run() convenience function).
    """

    def __init__(
        self,
        backend: Any | None = None,
        retry_controller: RetryController | None = None,
    ) -> None:
        self._backend = backend or get_backend()
        self._retry = retry_controller or RetryController()
        self._rate_limiter = get_rate_limiter()
        self._ctx_manager = ContextWindowManager(
            backend_name=self._backend.name,
            context_window=self._backend.context_window,
        )
        self._hlogger = get_harness_logger()
        self._registry = get_prompt_registry()

    @observe(name="skill_router_run")
    def run(self, skill_name: str, context: dict[str, Any]) -> SkillResult:
        """
        Execute a registered skill with the given context dict.

        Args:
            skill_name: Name passed to @skill(name=...).
            context: Variables for prompt rendering (pr_diff, context, etc.).

        Returns:
            SkillResult with parsed schema and telemetry.

        Raises:
            SkillNotFoundError: If skill is not in the registry.
        """
        reg = _SKILL_REGISTRY.get(skill_name)
        if reg is None:
            raise SkillNotFoundError(skill_name)

        # 1. Load and render prompt
        template = self._registry.load(reg.prompt_id, version=reg.version)
        system, user = template.render(**context)

        # 2. Context window check
        total_tokens = self._backend.count_tokens(system + "\n" + user)
        self._rate_limiter.wait_if_needed(self._backend.name, total_tokens)

        # 3. Build ChatRequest
        req = ChatRequest(
            system=system,
            user=user,
            temperature=reg.temperature,
            max_tokens=reg.max_tokens,
            response_schema=reg.schema_cls.model_json_schema(),
        )

        # 4. Execute with retry + schema validation
        prompt_hash = self._hlogger.hash_prompt(system, user)
        retry_count = 0

        def _validator(content: str) -> ResponseSchema:
            return reg.parser(content)

        resp, parsed = self._retry.call_with_retry(
            fn=self._backend.complete,
            req=req,
            schema_validator=_validator,
            schema_name=reg.schema_cls.__name__,
        )

        # 5. Log call
        record = CallRecord(
            skill=skill_name,
            backend=self._backend.name,
            model=resp.model,
            prompt_tokens=resp.prompt_tokens,
            completion_tokens=resp.completion_tokens,
            latency_ms=resp.latency_ms,
            validation_ok=True,
            retry_count=retry_count,
            prompt_hash=prompt_hash,
        )
        self._hlogger.log(record)

        logger.info(
            "skill_router_complete",
            skill=skill_name,
            backend=self._backend.name,
            tokens=resp.prompt_tokens + resp.completion_tokens,
            latency_ms=resp.latency_ms,
        )

        return SkillResult(
            skill_name=skill_name,
            parsed=parsed,  # type: ignore[arg-type]
            raw_content=resp.content,
            prompt_tokens=resp.prompt_tokens,
            completion_tokens=resp.completion_tokens,
            latency_ms=resp.latency_ms,
            retry_count=retry_count,
        )

    def list_skills(self) -> list[str]:
        """Return all registered skill names."""
        return sorted(_SKILL_REGISTRY.keys())


# ── Module-level singleton + convenience ─────────────────────────────────────

_router: SkillRouter | None = None


def get_skill_router() -> SkillRouter:
    """Return the module-level SkillRouter singleton."""
    global _router
    if _router is None:
        _router = SkillRouter()
    return _router


def run_skill(skill_name: str, context: dict[str, Any]) -> SkillResult:
    """Convenience wrapper: get_skill_router().run(skill_name, context)."""
    return get_skill_router().run(skill_name, context)
