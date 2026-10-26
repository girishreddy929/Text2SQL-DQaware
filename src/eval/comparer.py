# src/eval/comparer.py
from decimal import Decimal


def normalize_value(val):
    """Normalizes values for comparison (handles floats, decimals, strings)."""
    if val is None:
        return None
    if isinstance(val, (float, Decimal)):
        return round(float(val), 3)
    if isinstance(val, str):
        return val.strip().lower()
    return val


def rows_match(row1: dict, row2: dict) -> bool:
    """Compares two rows, ignoring column names by comparing their values in order."""
    vals1 = [normalize_value(v) for v in row1.values()]
    vals2 = [normalize_value(v) for v in row2.values()]

    if len(vals1) != len(vals2):
        return False

    # Compare values positionally
    for v1, v2 in zip(vals1, vals2):
        if v1 != v2:
            return False
    return True


def compare_results(
    gold_rows: list[dict], pred_rows: list[dict], order_sensitive: bool = False
) -> bool:
    """
    Compares two result sets.
    If order_sensitive is False, treats them as multisets (order doesn't matter).
    """
    if len(gold_rows) != len(pred_rows):
        return False

    if order_sensitive:
        for g_row, p_row in zip(gold_rows, pred_rows):
            if not rows_match(g_row, p_row):
                return False
        return True

    # Multiset comparison (order insensitive)
    # We create a copy of pred_rows and remove matches as we find them
    matched_indices = set()

    for g_row in gold_rows:
        match_found = False
        for i, p_row in enumerate(pred_rows):
            if i not in matched_indices and rows_match(g_row, p_row):
                matched_indices.add(i)
                match_found = True
                break
        if not match_found:
            return False

    return True
