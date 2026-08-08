"""
The tracing shim is what makes langfuse an optional extra: every agent module
imports `observe` from `dev_guardian.core.tracing`, so if the no-op fallback
stops behaving like a decorator, 13 modules fail to import at once.
"""
from __future__ import annotations

import dev_guardian.core.tracing as tracing


def _fallback_observe():
    """The no-op branch, regardless of whether langfuse is installed here."""
    source = tracing.__loader__.get_source("dev_guardian.core.tracing")
    namespace: dict = {}
    # Re-execute the module with the langfuse import forced to fail.
    exec(  # noqa: S102 - executing our own module source, under test
        source.replace("from langfuse import observe", "raise ImportError"),
        namespace,
    )
    assert namespace["LANGFUSE_AVAILABLE"] is False
    return namespace["observe"]


def test_no_op_observe_preserves_the_function_when_called_with_arguments():
    observe = _fallback_observe()

    @observe(name="some_span")
    def add(a: int, b: int) -> int:
        return a + b

    assert add(2, 3) == 5
    assert add.__name__ == "add"


def test_no_op_observe_preserves_the_function_when_used_bare():
    observe = _fallback_observe()

    @observe
    def double(x: int) -> int:
        return x * 2

    assert double(4) == 8
    assert double.__name__ == "double"


def test_module_exports_observe_whichever_branch_is_taken():
    assert callable(tracing.observe)
    assert isinstance(tracing.LANGFUSE_AVAILABLE, bool)


def test_agent_modules_import_observe_from_the_shim_not_langfuse():
    """Guards the whole point: a direct `from langfuse import observe` anywhere
    in the package would re-impose the hard dependency."""
    from pathlib import Path

    shim = Path(tracing.__file__)
    package = shim.parents[1]
    offenders = [
        str(path.relative_to(package))
        for path in package.rglob("*.py")
        if path != shim and "from langfuse import" in path.read_text()
    ]
    assert offenders == [], f"import langfuse directly: {offenders}"
