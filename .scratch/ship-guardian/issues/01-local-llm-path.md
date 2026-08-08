# Local LLM / SLM support path

Type: research
Status: resolved

## Question

The destination requires Guardian to work with "any API key or a local LLM / SLM if required."
What is the lightest path to local-model support?

- Does pointing the existing `openai_backend.py` at an OpenAI-compatible `base_url` (Ollama,
  llama.cpp server, LM Studio, vLLM) cover it, or does a dedicated backend adapter earn its place?
- Which locally-runnable small models can reliably produce the structured output the prompts in
  `backend/prompts/*.yaml` demand (the agents parse JSON verdicts out of completions)?
- What breaks at small context windows? `harness/context_window.py` is parameterised by backend
  name — what does it need to know about a local model?
- Does `harness/rate_limiter.py` need a no-op path for local models (no TPM limit to respect)?

Answer feeds the provider-selection contract in ticket 04.

## Answer

**No dedicated local backend adapter is needed.** Every mainstream local runtime — Ollama,
llama.cpp's server, LM Studio, vLLM — exposes the same OpenAI-compatible `/v1/chat/completions`
surface. Ollama serves it at `http://localhost:11434/v1`, and requires an `api_key` field that it
then ignores. So "local model" is just `openai_backend.py` pointed at a different `base_url`.

**Two small changes make the existing backend work locally** (`harness/backends/openai_backend.py`):

1. Read `OPENAI_BASE_URL` (or a Guardian-specific setting) and pass it to `openai.OpenAI(...)`.
   The constructor currently passes `api_key` only.
2. The constructor hard-fails when `OPENAI_API_KEY` is empty (`BackendUnavailableError`). When a
   `base_url` is set, the key must become optional — defaulting to a placeholder — or every local
   user is forced to invent a fake key.

**The real gap is structured output, and it is not local-specific.** The agents parse JSON verdicts
out of raw completions, but `openai_backend.py` never sends `response_format` — neither does the
Groq one. Prompt-only JSON is where small models fail. The fix that makes local models viable:

- Add an optional JSON/`response_format` flag to `ChatRequest` and honour it in every backend.
- Ollama's OpenAI-compatible endpoint supports `response_format`; its native API additionally takes
  a full JSON Schema in `format`, constraining generation at the token level so malformed JSON is
  mechanically impossible. With grammar constraints, model quality matters much less than prompting.
- Unsupported on Ollama's OpenAI surface: `logprobs`, `tool_choice`, `logit_bias`. None are used.

**Model floor**: Qwen3-class at 8B and up is the safe recommendation for code reasoning plus
structured output (32K context, extendable). Granite4 and Gemma3 also handle function calling;
Llama 3.2 3B / Gemma 3 2B are fast but too weak to trust on the agents' nested JSON verdicts.
Recommend documenting one blessed default rather than a matrix.

**Two harness assumptions break under a local model:**

- `context_window.py` — `_SAFE_PROMPT_TOKENS` is keyed by **backend name**, falling back to 8,000
  for unknown keys. A local model routed through the backend named `"openai"` inherits the OpenAI
  entry, which is sized for a 128K cloud model. A local 32K model would silently over-fill its
  context. The budget has to key off the **model**, or take an explicit override.
- `rate_limiter.py` — `_DEFAULT_TPM` hardcodes `groq: 12_000`. A local model has no TPM limit, so it
  needs an effectively infinite bucket, not a default one. `RateLimiter.__init__` already accepts an
  `overrides` dict, so this is a wiring decision, not new machinery.

`count_tokens` is a `words / 0.75` heuristic — imprecise but provider-neutral, fine to leave alone.

Sources:
- [Ollama OpenAI compatibility](https://docs.ollama.com/openai)
- [Reliable JSON from local LLMs](https://llmconfigurator.com/en/guides/llm-json-structured-output)
- [Structured output with Ollama](https://www.glukhov.org/llm-performance/ollama/llm-structured-output-with-ollama-in-python-and-go/)
- [Best local LLMs for structured output](https://insiderllm.com/guides/structured-output-local-llms/)
