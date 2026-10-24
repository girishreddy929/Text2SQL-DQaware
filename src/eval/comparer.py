"""Independent result comparer for Text2SQL evaluation."""

from __future__ import annotations
from decimal import Decimal
import math
from typing import Any


def normalize_value(val: Any) -> Any:
    """Normalize floats, Decimals, None, and strings for tolerant matching."""
    if val is None:
        return None
    if isinstance(val, (float, Decimal)):
        fval = float(val)
        return round(fval, 3)
    if isinstance(val, str):
        return val.strip().lower()
    return val


def normalize_row(row: tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(normalize_value(v) for v in row)


def values_match(v1: Any, v2: Any, tol: float = 1e-3) -> bool:
    """Check equality with float tolerance."""
    if v1 is None and v2 is None:
        return True
    if v1 is None or v2 is None:
        return False
    if isinstance(v1, (float, int)) and isinstance(v2, (float, int)):
        return math.isclose(float(v1), float(v2), abs_tol=tol, rel_tol=1e-4)
    return v1 == v2


def rows_match(r1: tuple[Any, ...], r2: tuple[Any, ...]) -> bool:
    if len(r1) != len(r2):
        return False
    return all(values_match(a, b) for a, b in zip(r1, r2))


def compare_results(
    gold_rows: list[tuple[Any, ...]],
    pred_rows: list[tuple[Any, ...]],
    order_sensitive: bool = False,
) -> bool:
    """Compare ground truth and predicted query outputs."""
    if len(gold_rows) != len(pred_rows):
        return False
    if not gold_rows and not pred_rows:
        return True

    norm_gold = [normalize_row(r) for r in gold_rows]
    norm_pred = [normalize_row(r) for r in pred_rows]

    if order_sensitive:
        return all(rows_match(g, p) for g, p in zip(norm_gold, norm_pred))

    # Order-insensitive multiset comparison
    unmatched_pred = list(norm_pred)
    for g_row in norm_gold:
        found_idx = -1
        for idx, p_row in enumerate(unmatched_pred):
            if rows_match(g_row, p_row):
                found_idx = idx
                break
        if found_idx >= 0:
            unmatched_pred.pop(found_idx)
        else:
            return False
    return len(unmatched_pred) == 0


if __name__ == "__main__":
    t1 = [(1, "SP", 15.201)]
    t2 = [(1, "sp ", Decimal("15.2014"))]
    print(f"Self-test tolerant match: {compare_results(t1, t2)}")
    print(
        f"Self-test order match: {compare_results([(1,), (2,)], [(2,), (1,)], order_sensitive=False)}"
    )
    print(
        f"Self-test order sensitive: {compare_results([(1,), (2,)], [(2,), (1,)], order_sensitive=True)}"
    )
