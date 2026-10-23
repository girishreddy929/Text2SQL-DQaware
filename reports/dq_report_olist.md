# Data Quality Report: olist

- Rules scanned: 2026-10-23 11:10:28.870310+00:00 | Data profiled: 2026-10-23 10:20:21.134355+00:00
- **Overall score 93.81 (Poor)**; 35 of 41 rules passed
- Errored rules (not scored): none

## Scores by dimension

| Name | Score | Band | Rules passed |
|---|---|---|---|
| Completeness | 78.03 | Poor | 4/7 |
| Uniqueness | 100.00 | Good | 7/7 |
| Validity | 100.00 | Good | 13/14 |
| Consistency | 100.00 | Good | 10/11 |
| Timeliness | 50.00 | Poor | 1/2 |

## Scores by table (worst first)

| Name | Score | Band | Rules passed |
|---|---|---|---|
| marketing.closed_deals | 76.87 | Poor | 3/4 |
| customer.order_reviews | 85.32 | Poor | 3/4 |
| sales.orders | 90.00 | Poor | 9/10 |
| catalog.products | 99.63 | Good | 3/5 |
| marketing.qualified_leads | 99.63 | Good | 2/2 |
| catalog.sellers | 100.00 | Good | 2/2 |
| customer.customers | 100.00 | Good | 3/3 |
| customer.geolocation | 100.00 | Good | 2/2 |
| sales.order_items | 100.00 | Good | 5/5 |
| sales.order_payments | 100.00 | Good | 3/4 |

_Scores are plain averages of rule pass %, rounded to 2 decimals, so a rule that fails at 99.998% can still show 100.00 inside a group. Exact numbers are in Findings._

## Findings (6 failing rules)

### 1. `orders_data_is_recent`: sales.orders (Timeliness)
- Pass rate **0.0000%** (threshold 100%); 1 failing rows of 1
- Rule type TABLE_CONDITION; columns: (table level)
- What it checks: Fresh data should have orders from the last 30 days (expected to FAIL- this public dataset ends in 2018).

### 2. `closed_deals_company_known`: marketing.closed_deals (Completeness)
- Pass rate **7.4822%** (threshold 90%); 779 failing rows of 842
- Rule type NON_NULL; columns: has_company
- What it checks: At least 90% of closed deals should say whether the seller has a company (expected to FAIL; about 92% are null).
- Example failing rows: `[{"sr_id": "4ef15afb4b2723d8f3d81e51ec7afefe", "mql_id": "5420aad7fec3549a85876ba1c529bd84", "sdr_id": "a8387c01a09e99ce014107505b92388c", "has_gtin": null, "won_date": "2018-02-26 19:58:54", "lead_type": "online_medium", "seller_id": "2c43fb513632d29b3b58df74816f1b06", "has_company": null, "average`

<details><summary>SQL that lists the failing rows</summary>

```sql
SELECT * FROM (
  SELECT t.*, "has_company" IS NOT NULL AS _dq_ok
  FROM "marketing"."closed_deals" AS t
) AS judged
WHERE NOT _dq_ok
LIMIT 10
```

</details>

### 3. `reviews_comment_message_present`: customer.order_reviews (Completeness)
- Pass rate **41.2975%** (threshold 80%); 58,247 failing rows of 99,224
- Rule type NON_NULL; columns: review_comment_message
- What it checks: At least 80% of reviews should carry a comment (expected to FAIL; about 41% do).
- Example failing rows: `[{"order_id": "73fc7af87114b39712e6da79b0a377eb", "review_id": "7bc2406110b926393aa56f80a40eba40", "review_score": 4, "review_comment_title": null, "review_creation_date": "2018-01-18 00:00:00", "review_comment_message": null, "review_answer_timestamp": "2018-01-18 21:46:59"}, {"order_id": "a548910a`

<details><summary>SQL that lists the failing rows</summary>

```sql
SELECT * FROM (
  SELECT t.*, "review_comment_message" IS NOT NULL AS _dq_ok
  FROM "customer"."order_reviews" AS t
) AS judged
WHERE NOT _dq_ok
LIMIT 10
```

</details>

### 4. `products_category_present`: catalog.products (Completeness)
- Pass rate **98.1488%** (threshold 99%); 610 failing rows of 32,951
- Rule type NON_NULL; columns: product_category_name
- What it checks: Products should have a category (expected to FAIL; about 1.85% are null).
- Example failing rows: `[{"product_id": "a41e356c76fab66334f36de622ecbd3a", "product_weight_g": 650, "product_width_cm": 12, "product_height_cm": 14, "product_length_cm": 17, "product_photos_qty": null, "product_name_lenght": null, "product_category_name": null, "product_description_lenght": null}, {"product_id": "d8dee61c`

<details><summary>SQL that lists the failing rows</summary>

```sql
SELECT * FROM (
  SELECT t.*, "product_category_name" IS NOT NULL AS _dq_ok
  FROM "catalog"."products" AS t
) AS judged
WHERE NOT _dq_ok
LIMIT 10
```

</details>

### 5. `products_category_translated`: catalog.products (Consistency)
- Pass rate **99.9939%** (threshold 100%); 2 failing rows of 32,951
- Rule type SQL_ASSERTION; columns: (table level)
- What it checks: Every product category needs an English translation (expected to FAIL - 2 categories are missing).
- Example failing rows: `[{"product_category_name": "portateis_cozinha_e_preparadores_de_alimentos"}, {"product_category_name": "pc_gamer"}]`

<details><summary>SQL that lists the failing rows</summary>

```sql
SELECT * FROM (SELECT DISTINCT p.product_category_name FROM catalog.products p LEFT JOIN catalog.category_translation t ON t.product_category_name = p.product_category_name WHERE p.product_category_name IS NOT NULL AND t.product_category_name IS NULL) AS violations LIMIT 10
```

</details>

### 6. `payments_installments_positive`: sales.order_payments (Validity)
- Pass rate **99.9981%** (threshold 100%); 2 failing rows of 103,886
- Rule type RANGE; columns: payment_installments
- What it checks: A payment has at least one installment (expected to FAIL- a few rows have 0).
- Example failing rows: `[{"order_id": "744bade1fcf9ff3f31d860ace076d422", "payment_type": "credit_card", "payment_value": "58.69", "payment_sequential": 2, "payment_installments": 0}, {"order_id": "1a57108394169c0b47d8f876acc9ba2d", "payment_type": "credit_card", "payment_value": "129.94", "payment_sequential": 2, "payment`

<details><summary>SQL that lists the failing rows</summary>

```sql
SELECT * FROM (
  SELECT t.*, ("payment_installments" IS NULL OR ("payment_installments" >= 1)) AS _dq_ok
  FROM "sales"."order_payments" AS t
) AS judged
WHERE NOT _dq_ok
LIMIT 10
```

</details>

## Columns with the most missing values

| Table | Column | Null % | Nulls | Rows |
|---|---|---|---|---|
| marketing.closed_deals | has_company | 92.52 | 779 | 842 |
| marketing.closed_deals | has_gtin | 92.40 | 778 | 842 |
| marketing.closed_deals | average_stock | 92.16 | 776 | 842 |
| marketing.closed_deals | declared_product_catalog_size | 91.81 | 773 | 842 |
| customer.order_reviews | review_comment_title | 88.34 | 87,656 | 99,224 |
| customer.order_reviews | review_comment_message | 58.70 | 58,247 | 99,224 |
| marketing.closed_deals | lead_behaviour_profile | 21.02 | 177 | 842 |
| sales.orders | order_delivered_customer_date | 2.98 | 2,965 | 99,441 |
| catalog.products | product_category_name | 1.85 | 610 | 32,951 |
| catalog.products | product_description_lenght | 1.85 | 610 | 32,951 |

## Rule coverage

- Tables profiled: 11 (with at least one rule: 10)
- Columns profiled: 70; with at least one rule: 26 (37.1%)

## How scores are calculated

- Rule score = % of rows that pass the rule (`pass_pct`).
- Group score (dimension, table, overall) = plain average of its rule scores.
- Errored rules are not scored. Bands: Good >= 99, Fair >= 95, otherwise Poor.
