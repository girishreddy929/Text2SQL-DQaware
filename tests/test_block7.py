import pytest
from langchain_core.embeddings.fake import DeterministicFakeEmbedding
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from pydantic import BaseModel

from src.adapters.llm.base import LLMProvider
from src.common import llm
from src.common.llm import response_text
from src.common.llm_guard import (
    LlmLimits,
    Throttle,
    backoff_delay,
    call_resilient,
    is_transient,
    load_limits,
)
import time


class FakeProvider(LLMProvider):
    name = "fake"

    def chat_model(self, temperature=0.0):
        return FakeListChatModel(responses=["hi"])

    def embeddings(self):
        return DeterministicFakeEmbedding(size=8)

    @property
    def chat_model_name(self):
        return "fake-chat"

    @property
    def embedding_model_name(self):
        return "fake-embed"


class CodeError(Exception):
    code = 429


def test_base_is_abstract():
    with pytest.raises(TypeError):
        LLMProvider()


def test_unknown_provider_message():
    with pytest.raises(ValueError, match="Supported: gemini"):
        llm.get_provider("nope")


def test_fake_provider_plugs_in(monkeypatch):
    monkeypatch.setitem(llm.PROVIDERS, "fake", (__name__, "FakeProvider"))
    p = llm.get_provider("fake")
    assert p.name == "fake"
    assert response_text(p.chat_model().invoke("x")) == "hi"
    assert len(p.embeddings().embed_query("a")) == 8


def test_response_text_str():
    assert response_text("  hello \n") == "hello"


def test_response_text_blocks():
    class Msg:
        content = [{"type": "text", "text": "Hel"}, {"type": "other"}, "lo"]

    assert response_text(Msg()) == "Hello"


def test_is_transient():
    assert is_transient(CodeError())
    assert is_transient(RuntimeError("429 RESOURCE_EXHAUSTED"))
    assert is_transient(TimeoutError())
    assert not is_transient(ValueError("bad request"))


def test_backoff_grows_and_caps():
    lim = LlmLimits(base_delay_seconds=2, max_delay_seconds=10)
    assert [backoff_delay(a, lim, lambda: 1.0) for a in (1, 2, 3, 4)] == [2, 4, 8, 10]
    assert backoff_delay(1, lim, lambda: 0.0) == 1.0


def test_retries_then_succeeds():
    calls, sleeps = [], []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("503 unavailable")
        return "ok"

    out = call_resilient(
        flaky, limits=LlmLimits(), throttle=Throttle(0), sleep=sleeps.append
    )
    assert out == "ok" and len(calls) == 3 and len(sleeps) == 2


def test_no_retry_on_permanent_error():
    calls = []

    def bad():
        calls.append(1)
        raise ValueError("invalid")

    with pytest.raises(ValueError):
        call_resilient(
            bad, limits=LlmLimits(), throttle=Throttle(0), sleep=lambda s: None
        )
    assert len(calls) == 1


def test_gives_up_after_max_attempts():
    calls, sleeps = [], []

    def down():
        calls.append(1)
        raise RuntimeError("503 unavailable")

    with pytest.raises(RuntimeError):
        call_resilient(
            down,
            limits=LlmLimits(max_attempts=3),
            throttle=Throttle(0),
            sleep=sleeps.append,
        )
    assert len(calls) == 3 and len(sleeps) == 2


def test_throttle_spacing():
    t = Throttle(0.05)
    start = time.monotonic()
    t.wait()
    t.wait()
    assert time.monotonic() - start >= 0.05


def test_limits_defaults():
    lim = load_limits()
    assert lim.max_attempts >= 1 and lim.min_interval_seconds >= 0


@pytest.mark.llm
def test_real_chat():
    assert (
        "ok"
        in response_text(llm.get_chat_model().invoke("Reply with the word OK")).lower()
    )


@pytest.mark.llm
def test_real_embeddings():
    assert len(llm.get_embeddings().embed_query("hello")) > 100


@pytest.mark.llm
def test_real_structured_output():
    class Answer(BaseModel):
        number: int

    out = (
        llm.get_chat_model().with_structured_output(Answer).invoke("What is 6 times 7?")
    )
    assert out.number == 42
