"""Tests for Block 12B: BIRD Benchmark Evaluation Harness, Sampler, and Cache."""

from pathlib import Path
import pytest

from config.settings import PROJECT_ROOT
from src.eval.bird_cache import (
    FreeTierThrottler,
    load_eval_cache,
    make_cache_key,
    save_eval_cache,
)
from src.eval.bird_sampler import find_bird_json, sample_stratified


def test_find_bird_json():
    path = find_bird_json()
    assert path.exists()
    assert path.name == "mini_dev_postgresql.json"


def test_stratified_sampler_distribution():
    # Synthetic test data: 2 databases, 2 difficulties (4 strata of 10 items = 40 total)
    mock_questions = (
        [{"question_id": i, "db_id": "db1", "difficulty": "simple"} for i in range(10)]
        + [
            {"question_id": 10 + i, "db_id": "db1", "difficulty": "challenging"}
            for i in range(10)
        ]
        + [
            {"question_id": 20 + i, "db_id": "db2", "difficulty": "simple"}
            for i in range(10)
        ]
        + [
            {"question_id": 30 + i, "db_id": "db2", "difficulty": "challenging"}
            for i in range(10)
        ]
    )
    # Target 12 allows exact division: 12 / 4 strata = 3 items per stratum
    sampled = sample_stratified(mock_questions, target_count=12, seed=42)
    assert len(sampled) == 12
    db1_count = sum(1 for q in sampled if q["db_id"] == "db1")
    db2_count = sum(1 for q in sampled if q["db_id"] == "db2")
    assert db1_count == 6
    assert db2_count == 6
    simple_count = sum(1 for q in sampled if q["difficulty"] == "simple")
    assert simple_count == 6


def test_cache_key_generation():
    key1 = make_cache_key(10, True, "gemini-3.5-flash-lite")
    key2 = make_cache_key(10, False, "gemini-3.5-flash-lite")
    assert key1 == "10:ev1:gemini-3.5-flash-lite"
    assert key2 == "10:ev0:gemini-3.5-flash-lite"
    assert key1 != key2


def test_cache_save_and_load(tmp_path: Path):
    cache_file = tmp_path / "test_cache.json"
    data = {"1:ev1:model": "SELECT 1;"}
    save_eval_cache(data, path=cache_file)
    loaded = load_eval_cache(path=cache_file)
    assert loaded == data


def test_free_tier_throttler_timing():
    throttler = FreeTierThrottler(min_interval_seconds=0.05)
    throttler.wait_if_needed()
    throttler.wait_if_needed()
    assert throttler.last_call_time > 0
