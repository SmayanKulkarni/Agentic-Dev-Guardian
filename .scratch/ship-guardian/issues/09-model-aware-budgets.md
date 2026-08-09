# Context budget and rate limits: keyed by backend or by model?

Type: grilling
Status: resolved
Blocked by: 04

## Question

Surfaced by ticket 01. Two harness modules assume the backend name determines the limits, which
stops being true the moment one backend can front several models.

- `context_window.py` — `_SAFE_PROMPT_TOKENS` is keyed by backend name, defaulting to 8,000 for
  unknown keys. A local 32K model routed through the `"openai"` backend inherits a 128K-shaped
  budget and silently over-fills. Key off the model, take an explicit user override, or query the
  runtime for its context length?
- `rate_limiter.py` — `_DEFAULT_TPM` hardcodes `groq: 12_000`. A local model has no TPM limit at
  all. Does an unknown backend get an infinite bucket or a conservative default? `RateLimiter`
  already accepts an `overrides` dict, so this is a wiring decision.
- Does the answer need a per-model registry, or is one user-supplied number per install enough?
  (The lazy option: one `GUARDIAN_CONTEXT_TOKENS` setting, no registry to maintain.)

## Answer

**Both budgets already key off the model, not the backend name** — `ContextWindowManager` takes
the live backend's `context_window`, and `SkillRouter` passes it. The backend-name table is now
only a fallback for callers that construct the manager bare. `_DEFAULT_TPM` likewise carries
effectively-infinite buckets for `ollama` and `local`, and a conservative one for `huggingface`.

**No per-model registry.** A self-hosted engine can serve any model at any context length, and
only the operator knows which — a registry would be permanently stale. The ticket's own lazy
option won:

- `GUARDIAN_CONTEXT_TOKENS` — one number, overrides everything, including the backend's declared
  window. Unset or unparseable is ignored, with a warning.
- `GUARDIAN_TPM` — one tokens-per-minute ceiling applied to every backend, beaten only by an
  explicit `RateLimiter(overrides=...)` from calling code.

**Unknown backends** keep a conservative 10,000 TPM default rather than an infinite bucket:
guessing "unlimited" for something that turns out to be a metered API costs the user money and
a 429 storm, while guessing "limited" only costs some latency the override removes.

Querying the runtime for its context length (Ollama's `/api/show`) was rejected: it adds a
provider-specific call to a code path that must stay provider-neutral, and it answers only for
one of the six providers.

Covered by new tests in `test_harness_context_window.py` and `test_harness_rate_limiter.py`.
