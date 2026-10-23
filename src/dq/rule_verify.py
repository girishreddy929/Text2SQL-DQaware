"""Run:  python -m src.dq.rule_verify [--source olist]
Independent check of the newest COMPLETED rule scan. For a hand-picked set of rules it
recomputes (total_rows, failed_rows) with DIFFERENT SQL than the compiler used, recomputes the
verdict from the threshold, and compares both with dq.results. Read-only. Exit 0 only if all match.
kind 'row'  = judged by the threshold; kind 'zero' = TABLE_CONDITION / SQL_ASSERTION (pass only at 0)."""

import argparse
import sys
from decimal import Decimal

from sqlalchemy import text

from src.common.db import get_admin_engine

ORDER_STATUSES = "'delivered','shipped','canceled','unavailable','invoiced','processing','created','approved'"

INDEPENDENT: dict[str, tuple[str, str]] = {
    "orders_order_id_not_null": (
        "row",
        "SELECT count(*), count(*) FILTER (WHERE order_id IS NULL) FROM sales.orders",
    ),
    "orders_order_id_unique": (
        "row",
        "SELECT (SELECT count(*) FROM sales.orders), (SELECT COALESCE(sum(c), 0) FROM "
        "(SELECT count(*) AS c FROM sales.orders GROUP BY order_id HAVING count(*) > 1) d)",
    ),
    "order_items_key_unique": (
        "row",
        "SELECT (SELECT count(*) FROM sales.order_items), (SELECT COALESCE(sum(c), 0) FROM "
        "(SELECT count(*) AS c FROM sales.order_items GROUP BY order_id, order_item_id HAVING count(*) > 1) d)",
    ),
    "orders_status_valid": (
        "row",
        "SELECT count(*), count(*) FILTER (WHERE order_status NOT IN ("
        + ORDER_STATUSES
        + ")) FROM sales.orders",
    ),
    "orders_delivered_has_date": (
        "row",
        "SELECT count(*), count(*) FILTER (WHERE order_status = 'delivered' "
        "AND order_delivered_customer_date IS NULL) FROM sales.orders",
    ),
    "orders_order_id_format": (
        "row",
        "SELECT count(*), count(*) FILTER (WHERE order_id !~ '^[0-9a-f]{32}$') FROM sales.orders",
    ),
    "products_category_present": (
        "row",
        "SELECT count(*), count(*) FILTER (WHERE product_category_name IS NULL) FROM catalog.products",
    ),
    "products_weight_positive": (
        "row",
        "SELECT count(*), count(*) FILTER (WHERE product_weight_g <= 0) FROM catalog.products",
    ),
    "products_category_translated": (
        "zero",
        "SELECT (SELECT count(*) FROM catalog.products), (SELECT count(*) FROM "
        "(SELECT DISTINCT product_category_name FROM catalog.products p "
        "WHERE product_category_name IS NOT NULL AND NOT EXISTS "
        "(SELECT 1 FROM catalog.category_translation t "
        "WHERE t.product_category_name = p.product_category_name)) x)",
    ),
    "geolocation_lat_in_brazil": (
        "row",
        "SELECT count(*), count(*) FILTER (WHERE geolocation_lat < -34 OR geolocation_lat > 6) "
        "FROM customer.geolocation",
    ),
    "geolocation_lng_in_brazil": (
        "row",
        "SELECT count(*), count(*) FILTER (WHERE geolocation_lng < -74 OR geolocation_lng > -34) "
        "FROM customer.geolocation",
    ),
    "reviews_comment_message_present": (
        "row",
        "SELECT count(*), count(*) FILTER (WHERE review_comment_message IS NULL) "
        "FROM customer.order_reviews",
    ),
    "reviews_have_order": (
        "zero",
        "SELECT count(*), count(*) FILTER (WHERE NOT EXISTS "
        "(SELECT 1 FROM sales.orders o WHERE o.order_id = r.order_id)) "
        "FROM customer.order_reviews r",
    ),
    "closed_deals_company_known": (
        "row",
        "SELECT count(*), count(*) FILTER (WHERE has_company IS NULL) FROM marketing.closed_deals",
    ),
    "payments_installments_positive": (
        "row",
        "SELECT count(*), count(*) FILTER (WHERE payment_installments < 1) FROM sales.order_payments",
    ),
    "order_items_have_seller": (
        "zero",
        "SELECT count(*), count(*) FILTER (WHERE NOT EXISTS "
        "(SELECT 1 FROM catalog.sellers s WHERE s.seller_id = i.seller_id)) "
        "FROM sales.order_items i",
    ),
    "orders_data_is_recent": (
        "zero",
        "SELECT 1, CASE WHEN max(order_purchase_timestamp) > now() - interval '30 days' "
        "THEN 0 ELSE 1 END FROM sales.orders",
    ),
    "leads_origin_present": (
        "row",
        "SELECT count(*), count(*) FILTER (WHERE origin IS NULL) FROM marketing.qualified_leads",
    ),
}


def expected_status(kind: str, total: int, failed: int, threshold) -> str:
    """Verdict recomputed from the counts (exact Decimal maths for the threshold test)."""
    if kind == "zero":
        return "passed" if failed == 0 else "failed"
    ok = Decimal(total - failed) * 100 >= Decimal(str(threshold)) * Decimal(total)
    return "passed" if ok else "failed"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Independently verify the newest rule scan."
    )
    parser.add_argument("--source", default="olist")
    args = parser.parse_args()

    problems: list[str] = []
    with get_admin_engine().connect() as conn:
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        conn.exec_driver_sql("SET LOCAL statement_timeout = '300s'")
        run = conn.execute(
            text(
                "SELECT run_id, started_at FROM dq.scan_runs WHERE source_id = :s "
                "AND status = 'completed' ORDER BY started_at DESC LIMIT 1"
            ),
            {"s": args.source},
        ).one_or_none()
        if run is None:
            print(
                f"No completed scan for source {args.source!r}. Run: python -m src.dq.runner"
            )
            return 1
        print(f"Verifying scan {run[0]} (started {run[1]:%Y-%m-%d %H:%M:%S} UTC)\n")
        stored = {
            r[0]: r
            for r in conn.execute(
                text(
                    "SELECT rule_id, total_rows, failed_rows, status, threshold "
                    "FROM dq.results WHERE run_id = CAST(:r AS uuid)"
                ),
                {"r": str(run[0])},
            ).all()
        }
        n_enabled = conn.execute(
            text("SELECT count(*) FROM dq.rules WHERE source_id = :s AND enabled"),
            {"s": args.source},
        ).scalar_one()
        print(
            f"Coverage: {len(stored)} stored results, {n_enabled} enabled rules in dq.rules"
        )
        if len(stored) != n_enabled:
            problems.append(f"result count {len(stored)} != enabled rules {n_enabled}")

        print(
            f"\n{'rule id':<36}{'stored rows':>12}{'failed':>8} | {'indep. rows':>12}{'failed':>8} | verdict"
        )
        print("-" * 100)
        for rule_id, (kind, sql) in INDEPENDENT.items():
            if rule_id not in stored:
                problems.append(f"{rule_id}: no stored result in this scan")
                continue
            _, s_total, s_failed, s_status, threshold = stored[rule_id]
            total, failed = (int(x) for x in conn.execute(text(sql)).one())
            want = expected_status(kind, total, failed, threshold)
            ok = (s_total, s_failed, s_status) == (total, failed, want)
            print(
                f"{rule_id:<36}{s_total:>12,}{s_failed:>8,} | {total:>12,}{failed:>8,} | "
                f"{s_status}/{want} {'OK' if ok else 'MISMATCH'}"
            )
            if not ok:
                problems.append(
                    f"{rule_id}: stored ({s_total}, {s_failed}, {s_status}) "
                    f"vs independent ({total}, {failed}, {want})"
                )

    print("-" * 100)
    if problems:
        print(f"{len(problems)} PROBLEMS:")
        for p in problems:
            print("  -", p)
        return 1
    print(f"ALL {len(INDEPENDENT)} CHECKED RULES MATCH (counts and verdicts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
