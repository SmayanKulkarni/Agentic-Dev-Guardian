# Provider selection contract

Type: grilling
Status: resolved
Blocked by: 01

## Question

`skill_router.py:192` hardcodes `backend or GroqBackend()`. The Protocol and three adapters already
exist. How does a user say which provider they want?

- What is the selection input — a `GUARDIAN_PROVIDER` setting, inference from whichever API key is
  present, or an explicit `guardian init` choice? What is the precedence when several keys exist?
- What is the default when *no* key is set at all? Hard failure with a clear message, or fall back
  to a local model?
- Where does the factory live, and what does it do when the selected provider's optional dependency
  (`anthropic`, `openai`) isn't installed? Those are extras in `pyproject.toml`, so a naive import fails.
- Model choice per provider: one hardcoded default each, or user-overridable? `llama-3.3-70b-versatile`
  is Groq-specific and appears in prompts and docs.
- Does `GUARDIAN_USE_HARNESS=0` (the legacy direct-Groq path in 9 modules) survive the release, or
  does provider-agnosticism kill it? Keeping it means every provider decision has two implementations.

- **Structured output** (from ticket 01): no backend currently sends `response_format`, so all JSON
  parsing is prompt-hope. Is a JSON flag on `ChatRequest` part of the provider contract, given local
  models need it most but cloud models benefit equally?
- **Local models** are the `openai` backend with a `base_url` and no real key (ticket 01). Does that
  present to the user as a distinct provider choice ("ollama") or as `openai` plus a base-url setting?

Blocks: 06, 09.

## Answer

1. **Selection input**: `GUARDIAN_PROVIDER` env var, explicit, no key-sniffing/inference.
   Values: `groq | anthropic | openai | ollama | local | huggingface`.
2. **No provider set**: defaults to `groq` (preserves today's zero-config behavior). Set to an
   unknown value, or the selected provider's required key is missing: hard fail with a clear
   message — no silent fallback.
3. **Factory**: new `harness/backend_factory.py::get_backend(name: str) -> LLMBackend`. Replaces
   the `backend or GroqBackend()` line in `SkillRouter.__init__` (`skill_router.py:192`). A
   missing optional dependency (`anthropic`, `openai`) is handled where it already is — each
   backend's `__init__` catches `ImportError` and raises `BackendUnavailableError` with the
   `pip install "agentic-dev-guardian[extra]"` hint. The factory just lets that propagate.
4. **Model choice**: each backend keeps its hardcoded `default_model`
   (`llama-3.3-70b-versatile`, `claude-3-5-haiku-20241022`, `gpt-4o-mini`, etc.), overridable by
   an optional `GUARDIAN_MODEL` env var honored by every backend.
5. **`GUARDIAN_USE_HARNESS=0`**: killed, not kept. The legacy direct-Groq path in the 9 modules
   (`gatekeeper.py`, `red_team.py`, `remediation.py`, `migration_scribe.py`,
   `pattern_translator.py`, `hotfix_scribe.py`, `graph.py`, `adr_generator.py`,
   `structure_explainer.py`) is migrated onto the harness/`SkillRouter` path as part of this
   ticket's implementation. Keeping both means every provider decision needs two
   implementations — provider-agnosticism only holds if there's one path.
6. **Structured output**: `ChatRequest` gets `response_schema: dict | None` — a full JSON Schema,
   not a bare bool. Groq and any OpenAI-compatible backend (openai/ollama/local/huggingface) send
   it natively via `response_format={"type": "json_schema", "json_schema": {...}}`. Anthropic has
   no native json_schema mode: emulate via tool-forcing — define a single tool matching the
   schema and force `tool_choice`, extract the tool-call arguments as the JSON result. This is
   new scope inside `anthropic_backend.py`, not just a wiring change.
7. **Local / self-hosted providers**: three named providers, not one `openai`+`base_url`
   catch-all (superseding ticket 01's "no dedicated adapter" conclusion — user wants Ollama and
   Hugging Face as first-class choices). All three are OpenAI-wire-compatible, so implement as
   one shared base class parameterized by `base_url`, `default_model`, `key_env_var`,
   `key_required`, with thin subclasses/configs:
   - `ollama`: `base_url=http://localhost:11434/v1`, key optional (placeholder), default model
     `qwen3:8b`.
   - `local`: generic self-hosted engine (TGI, vLLM, LM Studio). `base_url` required with no
     default, key optional, no safe default model — error message suggests `qwen3-8b-instruct`
     as a starting point.
   - `huggingface`: HF Inference Providers router, `base_url=https://router.huggingface.co/v1`,
     key required (`HF_TOKEN`), default model `Qwen/Qwen3-8B-Instruct`.
   `openai` remains cloud-only (`OPENAI_API_KEY` required, no `base_url` override) now that
   local/self-hosted have their own named providers.
8. Ticket 01's other findings carry into implementation: `context_window.py` must key context
   budgets by **model**, not backend name, and `rate_limiter.py` needs an effectively-infinite
   bucket for providers with no real TPM ceiling (ollama, local; huggingface may still need one).

Model floor for all local/self-hosted defaults: Qwen3-class, 8B+, per ticket 01's research.
