"""Retry with backoff + simple throttle for LLM calls (standard library only).
Demo (fake failures, no API cost):  python -m src.common.llm_guard"""

import random
import threading
import time
from functools import lru_cache

import yaml
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, Field

from config.settings import PROJECT_ROOT
from src.common.logging import get_logger

log = get_logger(__name__)
LIMITS_FILE = PROJECT_ROOT / "config" / "llm.yaml"
TRANSIENT_CODES = {429, 500, 502, 503, 504}
TRANSIENT_WORDS = (
    "resource_exhausted",
    "unavailable",
    "overloaded",
    "rate limit",
    "deadline exceeded",
    "timed out",
)


class LlmLimits(BaseModel):
    max_attempts: int = Field(4, ge=1, le=10)
    base_delay_seconds: float = Field(2.0, ge=0)
    max_delay_seconds: float = Field(30.0, ge=0)
    min_interval_seconds: float = Field(0.0, ge=0)  # 0 = no throttle


def load_limits() -> LlmLimits:
    if not LIMITS_FILE.exists():
        return LlmLimits()
    return LlmLimits(**(yaml.safe_load(LIMITS_FILE.read_text("utf-8")) or {}))


def is_transient(exc: BaseException) -> bool:
    """True for errors worth retrying (rate limit, overload, timeout)."""
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    for attr in ("code", "status_code", "status"):
        if getattr(exc, attr, None) in TRANSIENT_CODES:
            return True
    text = str(exc).lower()
    return any(w in text for w in TRANSIENT_WORDS)


def backoff_delay(attempt: int, limits: LlmLimits, jitter=random.random) -> float:
    raw = min(limits.max_delay_seconds, limits.base_delay_seconds * 2 ** (attempt - 1))
    return raw * (0.5 + 0.5 * jitter())


class Throttle:
    """Guarantees at least min_interval seconds between calls (thread-safe)."""

    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next)
            self._next = start + self.min_interval
        if start > now:
            time.sleep(start - now)


@lru_cache(maxsize=1)
def shared_throttle() -> Throttle:
    return Throttle(load_limits().min_interval_seconds)


def call_resilient(fn, *args, limits=None, throttle=None, sleep=time.sleep, **kwargs):
    limits = limits or load_limits()
    throttle = throttle or shared_throttle()
    for attempt in range(1, limits.max_attempts + 1):
        throttle.wait()
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if attempt == limits.max_attempts or not is_transient(exc):
                raise
            delay = backoff_delay(attempt, limits)
            log.warning(
                "transient error (attempt %d/%d): %s; retry in %.1fs",
                attempt,
                limits.max_attempts,
                str(exc)[:80],
                delay,
            )
            sleep(delay)


def resilient(runnable: Runnable) -> Runnable:
    """Wrap any chain/model so .invoke() retries transient errors."""
    return RunnableLambda(lambda x: call_resilient(runnable.invoke, x))


def main() -> None:
    limits = LlmLimits(base_delay_seconds=0.1)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return "ok"

    print(
        "1) flaky x2 then ok ->",
        call_resilient(flaky, limits=limits),
        f"(calls={calls['n']})",
    )
    try:
        call_resilient(lambda: 1 / 0, limits=limits)
    except ZeroDivisionError:
        print("2) non-transient error raised immediately (no retry)")
    try:
        call_resilient(
            lambda: (_ for _ in ()).throw(TimeoutError("x")),
            limits=LlmLimits(max_attempts=2, base_delay_seconds=0.1),
        )
    except TimeoutError:
        print("3) gives up after max_attempts")

    from src.common.llm import get_chat_model, response_text

    print(
        "4) real call ->", response_text(resilient(get_chat_model()).invoke("Say OK"))
    )


if __name__ == "__main__":
    main()
