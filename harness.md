# The Harness — A Story in Concepts

## Chapter -1: What this project even is

Before any of this makes sense, you need to know what's being built.

This project is called **Agentic Dev Guardian**. The one-line pitch: a
system that reads an entire codebase, builds a live map of how every piece
of it connects, and then uses that map plus a language model to
autonomously watch over the codebase — reviewing pull requests, hunting
for exploitable bugs, writing incident postmortems, planning safe
refactors, and generating architecture docs that stay in sync with the
actual code, not a stale wiki page someone wrote two years ago.

It works in two stages:

1. **Index.** A Tree-sitter parser walks a target codebase and extracts
   every function, class, import, and call relationship, then writes that
   as a graph into **Memgraph** (a graph database) — edges like `IMPORTS`,
   `CALLS`, `INHERITS_FROM` — plus a semantic vector index in **Qdrant**
   so the system can also find code by *meaning*, not just by structural
   edges. This combination — structural graph search plus semantic vector
   search — is called **GraphRAG** (Retrieval-Augmented Generation over a
   graph). It's the difference between "find every function that calls
   `auth_check`" (a graph query) and "find code that looks like it's
   doing authentication" (a vector search) — the system can do both and
   combine them.

2. **Act.** Once the codebase is indexed, a set of **agents** — each one a
   node in a **LangGraph** state machine, which is a framework for
   wiring multiple LLM-driven steps together into a pipeline with typed
   state passed between them — query that graph and use an LLM to make
   judgment calls. This project defines five agent pipelines, each
   triggered by a CLI command:

   - **`evaluate`** — feed it a pull request diff. `Gatekeeper` agent
     checks it against the dependency graph for architecture violations
     (did you remove a function something else still calls? did you add
     an import that breaks a layering rule?). `Red Team` agent tries to
     write a failing test that exploits the change. `Remediation` agent
     proposes a fix if problems were found. Ends in one verdict:
     approve, remediate, or reject.
   - **`audit`** — proactively finds the riskiest functions in a codebase
     (highest "blast radius" — the most other code that depends on them)
     and red-teams them without waiting for a PR to touch them.
   - **`incident`** — you paste in a production stack trace.
     `IncidentTriager` figures out which function actually failed,
     `SandboxReproducer` tries to reproduce it, `HotfixScribe` writes a
     blueprint for the fix.
   - **`refactor`** — describe a migration in plain English or by pattern
     name (e.g. "migrate pydantic v1 to v2"). `PatternTranslator` turns
     that into a graph query, finds every affected piece of code, and
     `MigrationScribe` drafts a batched, validated migration plan.
   - **`docs`** — walks the live graph and has an LLM narrate it into a
     human-readable architecture wiki, regenerated from the real code
     graph instead of hand-maintained.

Every one of those agents — nine of them across the five pipelines — needs
to talk to a large language model to do its actual reasoning. Right now
that model is **Groq**, running Meta's `llama-3.3-70b-versatile` — chosen
because it's fast and nearly free, which matters when a single `evaluate`
or `audit` run can trigger a dozen LLM calls back to back.

That's the "what" and the "why" of the whole project: turn a codebase into
a queryable graph, then point autonomous agents at that graph so a human
doesn't have to manually review every PR, hunt for every landmine
function, or keep docs from rotting.

Now — the part this document is actually about. All nine of those agents
need to talk to that LLM. And *how* they talk to it turned out to be its
own, separate engineering problem, big enough to deserve its own layer.
That layer is called **the harness**. Everything from here down is the
story of why it exists and what problem each piece of it solves.

## Chapter 0: The disease before the cure

Picture nine agents — Gatekeeper, Red Team, Remediation, IncidentTriager,
SandboxReproducer, HotfixScribe, PatternTranslator, MigrationScribe, the
docs narrators. Each one talks to an LLM to do its job. Nine agents, nine
separate relationships with the outside world. Each one opens its own
connection, writes its own instructions, and — this is the important part
— *hopes* the model answers in the shape it expects.

That hope is the disease. An LLM is not a function. It does not have a
type signature the compiler enforces. You ask it for `VERDICT: PASS` and
most of the time you get that, and some of the time you get "Sure, here's
my analysis..." and your regex finds nothing and silently defaults to
`"warn"` — the software equivalent of shrugging. Nobody notices until a
FAIL slips through as a WARN in production.

That's the actual problem the harness exists to solve. Not "call an API,"
but "turn an unreliable, rate-limited, occasionally-lying text generator
into something a state machine can trust." Everything below is a specific
answer to a specific way that trust breaks.

## Chapter 1: The contract problem — schemas as a border checkpoint

The first failure mode: the model says something, and downstream code
just... believes it. No checkpoint. A missing `REASONING:` line means an
empty string flows into a report that gets shown to a human reviewer, who
now has a PASS/FAIL verdict with zero justification and no way to tell if
that's a bug or the model genuinely had nothing to say.

The concept here is a **border checkpoint**: every response, before it's
allowed to enter the rest of the system, must prove it has the right
shape. Pydantic schemas are that checkpoint. `reasoning: str = Field(min_length=5)`
isn't pedantry — it's the difference between "the model explained itself"
and "the model produced four bytes that happen to satisfy a string type."
A schema turns "probably fine" into "provably fine, or rejected."

The deeper idea worth sitting with: **once you have a schema, a validation
failure becomes information, not just an error.** That distinction drives
the entire retry design later — a failure that carries "here's exactly
what was wrong" is a failure you can hand back to the thing that caused it
and ask it to fix itself.

## Chapter 2: Text-parsing as compatibility layer, not victory condition

Interesting design choice: the old regex parsers (`VERDICT:` line-scanning,
section extraction between ALL-CAPS headers) weren't deleted when the
schema layer arrived. They got demoted to fallback status — used only when
the model doesn't return clean JSON.

Why keep the ugly thing? Because **structured output from an LLM is a
request, not a guarantee.** You can ask for JSON in the system prompt and
still get prose back, especially from a smaller/cheaper model (this
project runs on Groq's Llama 70B — fast and cheap, but less obedient than
a frontier model about output formatting). Rather than betting the whole
pipeline on the model's compliance, there are two independent paths to the
same typed destination: JSON-first, structured-text-second. This is a
general resilience principle — when you can't fully control an upstream
system's behavior, build more than one road to the answer you need.

## Chapter 3: The rate limit — a shared, finite resource

Nine agents, one Groq account, one hard ceiling: 12,000 tokens per minute
on the free tier. If each agent is oblivious to the others, this is
exactly the "tragedy of the commons" — every individual actor behaves
reasonably in isolation, and the shared resource still gets exhausted,
because nobody's watching the total.

The **token bucket** is the classic answer to "how much of a shared,
regenerating resource can I use right now without starving others or
myself." A sliding 60-second window tracks every token spent; before any
call goes out, the system asks "does this fit in what's left of the
budget," and if not, it computes exactly how long until enough budget
frees up and waits that long — not a fixed retry delay, a *computed* one
based on when the oldest reservation ages out of the window.

The conceptual shift this represents: from **reactive** handling ("catch
the 429 error after it happens, then back off") to **proactive** handling
("never send the request that would have caused the 429 in the first
place"). Reactive rate-limit handling means every failure is a wasted
round-trip and a visible error in the logs. Proactive handling means the
system quietly paces itself and the ceiling is never actually hit.

## Chapter 4: Context windows — the space budget, not the time budget

A second, related resource constraint, easy to conflate with rate limiting
but conceptually distinct: it's not "how much can I send this minute," but
"how much can I send in *this one request* before the model literally
can't see the rest." A giant PR diff can blow past 8,000 tokens by itself
even with an empty rate-limit budget.

The interesting engineering decision is *where* to cut. The lazy option is
truncation — chop the text at the token limit and hope the important part
survived. This project instead tries to split at **semantic boundaries**:
function and class definitions. The reasoning is that a chunk boundary
mid-function is worse than useless — it hands the model half a function
body with no way to know what's missing, which is a recipe for a
confidently wrong analysis. A boundary at `def` or `class` at least gives
the model complete units of meaning, even if it can't see all of them at
once. This is the same intuition behind chunking strategies in any
retrieval or summarization system: respect the natural seams in the data
rather than slicing it like a ruler.

## Chapter 5: Retry — two different failures need two different medicines

This is maybe the most important conceptual distinction in the whole
harness: **not all retries are the same kind of retry**, and treating them
identically is a common mistake.

- A **transient failure** — a timeout, a flaky connection, a 429 — is a
  *timing* problem. The request was fine; the world just wasn't ready for
  it. The fix is exponential backoff: wait a little, then a little longer,
  then longer still, giving the transient condition time to clear. You are
  not changing what you're asking, only when you're asking it.

- A **schema validation failure** is a *content* problem. The request
  succeeded, the model answered, but the answer doesn't match the
  contract. Backing off and asking the identical question again
  accomplishes nothing — you'll likely get the identically malformed
  answer back. The correct medicine is different: show the model its own
  mistake. Append the actual Pydantic validation error to the
  conversation and ask again. This is a **feedback loop** in the control-
  theory sense — the system observes its own output error and uses that
  error signal to correct the next attempt, rather than blindly repeating
  the same action.

Conflating these two is the mistake most naive "just wrap it in a retry
loop" implementations make. Recognizing that failure *type* determines
correction *strategy* is the actual insight.

## Chapter 6: Prompts as versioned artifacts, not string literals

A prompt embedded directly in a Python function is invisible to change
tracking in any meaningful way — you'd need a diff tool that understands
prose to know if a subtle wording change shifted model behavior. Pulling
every prompt into its own YAML file with an explicit `version` field
reframes prompts as **configuration with a history**, not code.

Why does the version number matter? Because prompt changes are not always
improvements — a rewording that makes the prompt clearer to a human can
make an LLM *worse* at the task, unpredictably, for reasons that aren't
always obvious in advance. Versioning means you can roll back a prompt
independently of rolling back code, and you can A/B two versions of the
same prompt id without touching a single Python file. It also means a
prompt library builds up over time as a legible artifact — something a
non-engineer could review — instead of being scattered across nine agent
files as string literals nobody thinks to look at during a review.

## Chapter 7: One entry point — the router as a chokepoint by design

Before the harness, "call the LLM" was nine slightly-different
implementations of the same idea, each with its own opportunity to forget
a step — one agent might forget to log, another might not have retry
logic, a third calls a model name that doesn't exist anymore. This is the
classic failure mode of copy-paste architecture: the eleventh copy is
never quite like the first.

The router collapses this to one call path every agent must go through.
This is a **chokepoint pattern** — deliberately routing all traffic
through a single, narrow interface so that every cross-cutting concern
(rate limiting, retry, logging, schema validation, prompt loading) only
has to be implemented once and is *structurally impossible* to skip. An
agent can't forget to rate-limit itself, because the only door out of the
building has a rate limiter built into the frame.

The registration pattern (`@skill(name=..., schema=..., prompt=...)`) is
worth noting too: it's declarative. An agent doesn't call five different
setup functions in the right order — it declares *what it needs* (this
schema, this prompt, this temperature) and the router figures out *how* to
satisfy that. Declarative registration over imperative setup is a
recurring trade a lot of frameworks make, because it makes misuse harder —
there's less sequence to get wrong.

## Chapter 8: Provider abstraction — betting against lock-in

Three backend implementations (Groq, Anthropic, OpenAI) sit behind one
`Protocol`. The concept is the oldest one in this list: **program to an
interface, not an implementation.** The reason it matters here
specifically is economic as much as technical — Groq is fast and nearly
free but has a hard, punishing rate ceiling; Anthropic and OpenAI are more
expensive and more capable. A system built assuming Groq forever can't
adapt when the free tier isn't enough for a heavier task. A system built
against a `complete()`/`count_tokens()` contract can swap the backend for
a single skill, or even route different skills to different providers by
cost/capability tradeoff, without touching the calling code at all.

This is the same reasoning behind repository patterns for databases or
ports-and-adapters for external services: the thing likely to change
(which vendor, which model) is isolated behind the thing unlikely to
change (the shape of a request and a response).

## Chapter 9: Observability as a local, durable record

Every call gets logged to a local SQLite file, independent of whether an
external tracing service (Langfuse, in this case) is configured or
reachable. The concept: **your own visibility into your own system
shouldn't depend on a third party being up.** A hosted tracer is great for
rich dashboards, but if it's down, or the API key is missing, or the
network is unreachable, you still want to be able to answer "how many
retries happened last night" and "which skill is burning the most
tokens" from something you fully control. Local-first observability is a
fallback layer under the fancier one, not a replacement for it.

The other quiet idea baked into the log schema: cost isn't an
afterthought bolted on later, it's computed at write-time from token
counts and per-backend rates. Visibility into spend is treated as a
first-class signal alongside latency and error rate, not something you'd
reconstruct later from a billing dashboard days after the fact.

## Chapter 10: Migrating a live system without a leap of faith

The riskiest part of a project like this usually isn't writing the new
system — it's the moment you switch the old one off. Two ideas here work
together to make that moment boring instead of terrifying.

**The feature flag** (`GUARDIAN_USE_HARNESS`) means the old and new code
paths coexist in the same file. Nothing is deleted. The system can run
either path based on one environment variable, which means if the new
path misbehaves in production at 2am, the fix is flipping a flag, not an
emergency rollback deploy.

**Shadow-run testing** is the more interesting idea. Before trusting the
flag, you don't just test the new parser in isolation — you feed the
*exact same* raw model output into both the old parser and the new parser
and assert they produce equivalent results. This is a way of answering a
very specific question: "if I switch everything today, will any existing
behavior silently change?" It's a parity proof, not a correctness proof —
it doesn't tell you the new system is *right*, it tells you the new system
agrees with the old one, which was already trusted in production. That's
a much cheaper bar to clear before a big cutover, and it's what allowed
this migration to flip every agent at once instead of migrating them one
at a time over months.

## Closing thought

Strip away the specific libraries and file names and what's left is a
short list of general lessons for wiring unreliable, non-deterministic
external systems into something dependable: validate everything crossing
the boundary; know which failure you're looking at before you decide how
to retry it; treat shared resources as shared and budget them
proactively; keep configuration (prompts) separate from logic (code) and
version the configuration; force every caller through one disciplined
chokepoint instead of trusting nine copies to stay in sync; abstract the
vendor because vendors change; watch your own system locally, don't
outsource your only visibility; and never flip a big switch without first
proving, mechanically, that nothing downstream will notice the flip.
