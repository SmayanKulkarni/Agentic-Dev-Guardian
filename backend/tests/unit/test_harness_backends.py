"""
Tests for harness backend protocol (ChatRequest / ChatResponse Pydantic models)
and the LLMBackend protocol interface.

These are pure unit tests — no live API calls. They verify:
- ChatRequest field validation
- ChatResponse field validation
- Default values
- count_tokens returns int >= 0
- Backend protocol compliance via a stub
"""
from __future__ import annotations

from dev_guardian.harness.backends import ChatRequest, ChatResponse


class TestChatRequest:
    def test_basic_creation(self):
        req = ChatRequest(system="You are a helper.", user="Hello?", temperature=0.2, max_tokens=512)
        assert req.system == "You are a helper."
        assert req.user == "Hello?"
        assert req.temperature == 0.2
        assert req.max_tokens == 512

    def test_defaults(self):
        req = ChatRequest(system="sys", user="usr")
        assert 0.0 <= req.temperature <= 1.0
        assert req.max_tokens > 0

    def test_empty_system_allowed(self):
        req = ChatRequest(system="", user="question")
        assert req.system == ""

    def test_empty_user_allowed(self):
        req = ChatRequest(system="sys", user="")
        assert req.user == ""

    def test_temperature_range(self):
        ChatRequest(system="s", user="u", temperature=0.0)
        ChatRequest(system="s", user="u", temperature=1.0)

    def test_max_tokens_positive(self):
        req = ChatRequest(system="s", user="u", max_tokens=4096)
        assert req.max_tokens == 4096

    def test_immutable_copy_via_model_copy(self):
        req = ChatRequest(system="orig", user="orig")
        req2 = req.model_copy(update={"user": "updated"})
        assert req2.user == "updated"
        assert req.user == "orig"


class TestChatResponse:
    def test_basic_creation(self):
        resp = ChatResponse(
            content="The answer is 42.",
            model="llama-3.3-70b-versatile",
            prompt_tokens=15,
            completion_tokens=5,
            latency_ms=120,
        )
        assert resp.content == "The answer is 42."
        assert resp.model == "llama-3.3-70b-versatile"
        assert resp.prompt_tokens == 15
        assert resp.completion_tokens == 5
        assert resp.latency_ms == 120

    def test_token_counts_non_negative(self):
        resp = ChatResponse(content="ok", model="m", prompt_tokens=0, completion_tokens=0, latency_ms=0)
        assert resp.prompt_tokens == 0
        assert resp.completion_tokens == 0

    def test_total_tokens_property(self):
        resp = ChatResponse(content="x", model="m", prompt_tokens=100, completion_tokens=50, latency_ms=10)
        assert resp.prompt_tokens + resp.completion_tokens == 150

    def test_empty_content_allowed(self):
        resp = ChatResponse(content="", model="m", prompt_tokens=5, completion_tokens=0, latency_ms=5)
        assert resp.content == ""


class TestStubBackend:
    """Verify the LLMBackend protocol can be satisfied by a minimal stub."""

    def _make_stub(self, response_content: str = "stub response"):
        from dev_guardian.harness.backends import ChatResponse

        class StubBackend:
            name = "stub"

            def complete(self, req: ChatRequest) -> ChatResponse:
                return ChatResponse(
                    content=response_content,
                    model="stub-model",
                    prompt_tokens=10,
                    completion_tokens=5,
                    latency_ms=1,
                )

            def count_tokens(self, text: str) -> int:
                return max(1, len(text) // 4)

        return StubBackend()

    def test_stub_complete_returns_chat_response(self):
        stub = self._make_stub("hello")
        req = ChatRequest(system="s", user="u")
        resp = stub.complete(req)
        assert isinstance(resp, ChatResponse)
        assert resp.content == "hello"

    def test_stub_count_tokens_returns_int(self):
        stub = self._make_stub()
        n = stub.count_tokens("the quick brown fox")
        assert isinstance(n, int)
        assert n > 0

    def test_stub_count_tokens_empty_string(self):
        stub = self._make_stub()
        n = stub.count_tokens("")
        assert isinstance(n, int)
        assert n >= 0

    def test_stub_has_name_attribute(self):
        stub = self._make_stub()
        assert hasattr(stub, "name")
        assert isinstance(stub.name, str)
