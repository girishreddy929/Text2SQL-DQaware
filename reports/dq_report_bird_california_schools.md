# Data Quality Report: bird:california_schools

- Rules scanned: 2026-10-23 13:19:35.996040+00:00 | Data profiled: 2026-10-23 13:07:47.676416+00:00
- **Overall score 99.09 (Good)**; 92 of 92 rules passed
- Errored rules (not scored): none

## Scores by dimension

| Name | Score | Band | Rules passed |
|---|---|---|---|
| Completeness | 98.53 | Fair | 57/57 |
| Uniqueness | 100.00 | Good | 2/2 |
| Validity | 100.00 | Good | 33/33 |

## Scores by table (worst first)

| Name | Score | Band | Rules passed |
|---|---|---|---|
| bird_california_schools.schools | 97.81 | Fair | 35/35 |
| bird_california_schools.frpm | 99.84 | Good | 44/44 |
| bird_california_schools.satscores | 100.00 | Good | 13/13 |

_Scores are plain averages of rule pass %, rounded to 2 decimals, so a rule that fails at 99.998% can still show 100.00 inside a group. Exact numbers are in Findings._

## Findings (0 failing rules)

No failing rules.

## Columns with the most missing values

| Table | Column | Null % | Nulls | Rows |
|---|---|---|---|---|
| bird_california_schools.schools | admemail3 | 99.76 | 17,644 | 17,686 |
| bird_california_schools.schools | admfname3 | 99.76 | 17,644 | 17,686 |
| bird_california_schools.schools | admlname3 | 99.76 | 17,644 | 17,686 |
| bird_california_schools.schools | admemail2 | 97.60 | 17,262 | 17,686 |
| bird_california_schools.schools | admfname2 | 97.56 | 17,255 | 17,686 |
| bird_california_schools.schools | admlname2 | 97.56 | 17,255 | 17,686 |
| bird_california_schools.schools | ext | 96.95 | 17,146 | 17,686 |
| bird_california_schools.schools | fundingtype | 90.72 | 16,044 | 17,686 |
| bird_california_schools.schools | charternum | 89.82 | 15,885 | 17,686 |
| bird_california_schools.frpm | Charter Funding Type | 88.31 | 8,819 | 9,986 |

## Rule coverage

- Tables profiled: 3 (with at least one rule: 3)
- Columns profiled: 89; with at least one rule: 67 (75.3%)

## How scores are calculated

- Rule score = % of rows that pass the rule (`pass_pct`).
- Group score (dimension, table, overall) = plain average of its rule scores.
- Errored rules are not scored. Bands: Good >= 99, Fair >= 95, otherwise Poor.
