"""Disk cache and free-tier rate throttler for BIRD evaluation runs."""

from __future__ import annotations
import json
from pathlib import Path
import time

from config.settings import PROJECT_ROOT

CACHE_FILE = PROJECT_ROOT / "data" / "bird" / "bird_eval_cache.json"


def make_cache_key(question_id: int, with_evidence: bool, model_name: str) -> str:
    ev_flag = "ev1" if with_evidence else "ev0"
    return f"{question_id}:{ev_flag}:{model_name}"


def load_eval_cache(path: Path = CACHE_FILE) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_eval_cache(cache: dict[str, str], path: Path = CACHE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)
    temp_path.replace(path)


class FreeTierThrottler:
    """Enforces minimum interval (seconds) between live LLM invocations."""

    def __init__(self, min_interval_seconds: float = 4.2):
        self.min_interval = min_interval_seconds
        self.last_call_time = 0.0

    def wait_if_needed(self) -> None:
        elapsed = time.monotonic() - self.last_call_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_call_time = time.monotonic()


if __name__ == "__main__":
    c = load_eval_cache()
    print(f"Loaded cache from {CACHE_FILE}: {len(c)} entries.")
    throttler = FreeTierThrottler(min_interval_seconds=1.0)
    throttler.wait_if_needed()
    throttler.wait_if_needed()
    print("Throttler self-test passed.")
