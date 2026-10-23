# TrustSQL: DQ-Aware Agentic Text2SQL

Ask business questions in plain English and get correct SQL, results, a plain-English answer, and
**data quality warnings**. TrustSQL is also a transparent, Dataplex-style data quality engine and a
modular Text2SQL accelerator (a new LLM, database or vector store plugs in through an interface).

**Status:** Blocks 0-4 done (environment, Olist and BIRD data, profiler, rule engine).
Block 5 (rule recommender, scoring, DQ report) is next. 88 tests pass.

## 1. Architecture in one picture

```
Olist CSVs ──► raw ──► sales / customer / catalog / marketing          BIRD dump ──► bird_<db_id> (11 schemas)
                              │                                                       │
                              ▼                                                       ▼
        A. DQCA ENGINE:  profiler ──► dq.profiles      rules (YAML) ──► runner ──► dq.results
                              │                                                       │
                              └────────────► B. METADATA (descriptions, KG, ontology) ◄┘   (Blocks 7-11)
                                                          │
                                                          ▼
                              C. AGENTIC TEXT2SQL (LangGraph, Gemini)                      (Blocks 12-17)
                                                          │
                                                          ▼
                              D. FastAPI + Streamlit                                       (Blocks 17B-18)
```

One database engine: **PostgreSQL 16 + pgvector** in Docker. Two roles: `trustsql_admin` (setup, loading,
DQ writes) and `t2s_reader` (read-only, 30 s statement timeout; the only role agents and rule SQL use).

## 2. Setup (Windows PowerShell; Mac/Linux differences noted)

Prerequisites: Python 3.11+ (3.13 is in use), Docker Desktop, a Gemini API key (Google AI Studio).

```powershell
cd C:\Users\girish.reddy\vscode-projs\dqca-demo
python -m venv .venv
.venv\Scripts\Activate.ps1            # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                # Mac/Linux: cp .env.example .env   then edit the passwords and key
docker compose up -d                  # PostgreSQL 16 + pgvector on localhost:5433, container trustsql-db
python -m src.common.check_env        # sanity check of settings, database and Gemini
```

Load the data (each command is re-runnable; see each module's docstring for flags):

```powershell
python -m src.ingestion.download          # Olist CSVs via the Kaggle API (needs Kaggle credentials in .env)
python -m src.ingestion.load_raw          # CSVs -> raw schema (all TEXT)
python -m src.ingestion.build_domains     # raw -> typed schemas sales / customer / catalog / marketing
python -m src.ingestion.setup_roles       # read-only role t2s_reader + grants. RE-RUN after build_domains
python -m src.ingestion.bird_fetch        # BIRD Mini-Dev download (~764 MB)
python -m src.ingestion.bird_dump_scan    # read-only scan of the PostgreSQL dump
python -m src.ingestion.bird_loader       # 11 bird_<db_id> schemas (--reload to redo)
python -m src.ingestion.bird_gold_check   # runs the 500 gold queries as t2s_reader
python -m src.dq.init_schema              # dq schema: profiling + rule tables
```

Run the data quality engine and the tests:

```powershell
python -m src.dq.profiler                 # profile every Olist column -> dq.profiles
python -m src.dq.runner                   # run all DQ rules -> dq.results
python -m pytest -q                       # expected: 88 passed
```

## 3. Project layout

```
config/       settings.py (get_settings), domains.yaml, profiler.yaml, dq_rules/*.yaml
sql/          00_init_extensions.sql, 01_domain_schemas.sql (generated), 02_dq_schema.sql, 03_dq_rules_schema.sql
src/common/   db.py (engines, connector factory), logging.py, llm.py, check_env.py, list_models.py
src/adapters/ db/ (base, postgres), llm/, vectordb/        # interfaces for new LLMs, DBs, vector stores
src/ingestion/ download, load_raw, build_domains, setup_roles, bird_*.py
src/dq/       profiler_sql, profiler, profile_verify, profile_inspect, init_schema,
              rules_models, rule_compiler, runner, rule_verify
src/metadata/ src/text2sql/ src/api/ src/eval/          # later blocks (placeholders)
tests/        test_block0 ... test_block4.py
data/         raw/ (Olist CSVs), bird/ (BIRD files)       # git-ignored
```

## 4. Data quality: the profiler

The profiler measures every column (null %, distinct count, min/max/mean, lengths, top values) and
stores a dated snapshot with the **exact SQL** it used.

| Table | Content |
|---|---|
| `dq.profile_runs` | one row per profiler run |
| `dq.profile_tables` | per table: row count and the stats SQL |
| `dq.profiles` | per column: all statistics, top values and their SQL |
| `dq.latest_profiles` (view) | newest completed profile per column |

Verify independently with `python -m src.dq.profile_verify` (expects `ALL 370 CHECKS MATCH`).
Tunables are in `config/profiler.yaml`.

## 5. Data quality: rules

### 5.1 What a rule is
A profile says "2.98% of delivery dates are null". A **rule** states what the data must satisfy
("at least 99.9% of delivered orders have a delivery date") and the engine **judges** the data.
Rules are written in YAML, validated, compiled to **visible SQL**, executed, and the verdict plus the
evidence (counts, the SQL, sample failing rows) is stored. Nothing is a black box.

### 5.2 The eight rule types

| Type | A row passes when | Verdict |
|---|---|---|
| `NON_NULL` | the column has a value | pass % >= threshold |
| `UNIQUENESS` | its key (one or more columns) is not duplicated; rows with a null key are ignored | pass % >= threshold |
| `RANGE` | value within `min_value` / `max_value` (`strict_min` / `strict_max` for > and <) | pass % >= threshold |
| `SET` | value is one of `values` (compared as text) | pass % >= threshold |
| `REGEX` | value matches the PostgreSQL regex `pattern` | pass % >= threshold |
| `ROW_CONDITION` | your SQL boolean `expression` is true for the row (NULL counts as a fail) | pass % >= threshold |
| `TABLE_CONDITION` | the aggregate `expression` (for example `count(*) >= 90000`) is true; counted as 1 row | true or fail |
| `SQL_ASSERTION` | your `sql` query returns the VIOLATING rows; passes only when it returns zero | zero rows or fail |

`threshold` is the minimum % of rows that must pass (default 100). For `RANGE`,`SET` and `REGEX`, nulls pass unless the rule sets `ignore_null: false`.

**Dimensions** (the kind of quality): Completeness, Uniqueness, Validity, Consistency, Timeliness,
Accuracy. `NON_NULL`, `UNIQUENESS`, `RANGE`, `SET` and `REGEX` have a default dimension; the other
three types must state one.

### 5.3 How a rule travels through the code

```
config/dq_rules/*.yaml
   │  load_rules()        validates every rule with Pydantic            (rules_models.py)
   ▼
compile_rule()            builds count_sql + failing_sql, no DB needed  (rule_compiler.py)
   │  execute_rule()      runs as the read-only t2s_reader, one short
   ▼                      connection per rule, explicit timeout          (runner.py)
judge()                   pass % vs threshold -> passed / failed / error (rule_compiler.py)
   ▼
dq.rules (synced) + dq.scan_runs + dq.results   ->   view dq.latest_results
```

Every result stores the counts, the exact SQL (`sql_used`), the SQL that lists failures
(`failing_sql`) and up to 10 failing rows (`sample_failures`). A rule whose SQL fails is stored as
`status = 'error'` and the scan continues. Writes happen only through the admin engine; rule SQL can
never write because it runs as `t2s_reader`.

### 5.4 When do rules actually run?

Rules run **only when you run the runner**. Nothing triggers them automatically yet.

| What you do | Do rules run? |
|---|---|
| `docker compose up` | No |
| `load_raw`, `build_domains`, `bird_loader` | No. The data changed, so stored results are stale: re-run the profiler and the runner |
| `python -m src.dq.profiler` | No. It only measures |
| **`python -m src.dq.runner`** | **Yes. This is the only thing that executes rules today** |
| `rules_models`, `rule_compiler` | No. They validate rules / print the SQL (`--check-db` only reads `information_schema`) |
| `rule_verify`, `profile_verify` | No. They recompute a sample and compare with stored results |
| `pytest` | Mostly no. One test runs a tiny 3-rule scan under `source_id = test_block4` and deletes it |
| A user asks a question (Blocks 13-15) | Rules do **not** run per question. The DQ Advisor reads the stored verdicts from `dq.latest_results` |
| API / dashboard (Blocks 17B-18) | They read stored results; a "run scan" action will call the runner |

Results are **snapshots**: they describe the data at scan time. Re-run the runner after reloading data,
or schedule it (Windows Task Scheduler or cron) to call `python -m src.dq.runner`.

### 5.5 How to add a rule (6 steps)

1. **Write it.** Add an item to any `config/dq_rules/*.yaml` (a file needs `source_id:` and `rules:`).
2. **Validate:** `python -m src.dq.rules_models --check-db` (YAML mistakes, wrong table or column names).
3. **Preview the SQL:** `python -m src.dq.rule_compiler --rule <rule_id>`.
4. **Run only that rule:** `python -m src.dq.runner --rules <rule_id>`.
5. **Read the evidence** (queries in 5.6).
6. **Optional:** add an independent check to `INDEPENDENT` in `src/dq/rule_verify.py` and a test.

Cookbook, one example per type:

```yaml
source_id: olist
rules:
  - {id: orders_customer_present, table: sales.orders, column: customer_id, type: NON_NULL, threshold: 100}
  - {id: items_key_unique, table: sales.order_items, columns: [order_id, order_item_id], type: UNIQUENESS}
  - {id: freight_not_negative, table: sales.order_items, column: freight_value, type: RANGE, min_value: 0}
  - {id: payment_type_valid, table: sales.order_payments, column: payment_type, type: SET,
     values: [credit_card, boleto, voucher, debit_card, not_defined]}
  - {id: state_two_letters, table: customer.customers, column: customer_state, type: REGEX, pattern: '^[A-Z]{2}$'}
  - id: approved_after_purchase
    table: sales.orders
    type: ROW_CONDITION
    dimension: Consistency
    expression: "order_approved_at IS NULL OR order_approved_at >= order_purchase_timestamp"
    threshold: 99.9
  - {id: enough_orders, table: sales.orders, type: TABLE_CONDITION, dimension: Completeness,
     expression: "count(*) >= 90000"}
  - id: items_have_product
    table: sales.order_items
    type: SQL_ASSERTION
    dimension: Consistency
    sql: "SELECT i.order_id FROM sales.order_items i LEFT JOIN catalog.products p ON p.product_id = i.product_id WHERE p.product_id IS NULL"
```

Rules of the road:
- `id`: lowercase snake_case, unique across **all** files. `table`: `schema.table`.
- `dimension` is required for `ROW_CONDITION`, `TABLE_CONDITION` and `SQL_ASSERTION`.
- `ROW_CONDITION` / `TABLE_CONDITION` expressions use the table's own column names; `SQL_ASSERTION` SQL must use
  schema-qualified names, start with `SELECT` or `WITH`, and return the **violating** rows.
- No `;`, `--` or `/* */` inside SQL. Quote odd identifiers by hand inside expressions (`"Academic Year"`).
- YAML traps: unquoted `NO`, `ON`, `Y` become booleans (quote them); quote any expression containing `: `.
- Unknown keys are errors on purpose (`treshold` is rejected, not ignored).
- Turn a rule off with `enabled: false` (it stays in `dq.rules`, but is not executed). If you **delete** a rule
  from YAML, its row in `dq.rules` and its old results remain as history; remove them with
  `DELETE FROM dq.rules WHERE source_id = 'olist' AND rule_id = '<id>';`.

### 5.6 Reading the results

```sql
-- newest verdict per rule
SELECT rule_id, status, total_rows, failed_rows, pass_pct, threshold
FROM dq.latest_results WHERE source_id = 'olist' ORDER BY status DESC, rule_id;

-- the exact SQL behind a verdict, and the evidence
SELECT sql_used, failing_sql, jsonb_pretty(sample_failures) FROM dq.latest_results
WHERE rule_id = 'products_category_translated';

-- scan history
SELECT started_at, status, rules_total, rules_passed, rules_failed, rules_errored
FROM dq.scan_runs ORDER BY started_at DESC LIMIT 5;
```

Run them with: `docker exec -i trustsql-db psql -U trustsql_admin -d trustsql` (pipe the SQL in).

## 6. Tests

```powershell
python -m pytest -q                      # everything (88 tests)
python -m pytest -m "not db and not llm" # fast tests only, no database, no Gemini
```
Markers: `db` needs the Postgres container; `llm` calls the real Gemini API (uses free-tier quota).

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `relation "dq.profiles" does not exist` | `python -m src.dq.init_schema` |
| `permission denied for schema ...` after rebuilding domains | `python -m src.ingestion.setup_roles` |
| Rule file errors listed by the runner | Fix the named key; run `rules_models --check-db` |
| A rule shows `ERROR` | Read the message under the report; for timeouts use `runner --timeout 300` |
| DB tests skip or fail on "latest scan" | `python -m src.dq.runner` (a full scan), then re-run the tests |
| Gemini warning "temperature will be ignored" | Harmless; the configured model uses fixed sampling |

## 8. Roadmap

| Block | Topic | Status |
|---|---|---|
| 0-2B | Environment, Olist, domains, roles, BIRD Mini-Dev | Done |
| 3 | Profiler | Done |
| 4 | Rule engine | Done |
| 5 | Rule recommender, dimension scoring, DQ report, profile a BIRD DB | Next |
| 6 | BigQuery + Dataplex parity | Todo |
| 7-11 | LangChain/Gemini, metadata, knowledge graph, ontology, embeddings | Todo |
| 12-17 | Baseline and agentic Text2SQL, evaluation (Olist golden set, BIRD sample) | Todo |
| 17B-19 | FastAPI, Streamlit, extensibility proof, documentation | Todo |

## 9. Data and licences

- **Olist** Brazilian E-Commerce and Marketing Funnel datasets (Kaggle).
- **BIRD Mini-Dev** (PostgreSQL version): 500 questions, 11 databases, difficulty simple 148 / moderate 250 / challenging 102. Licence **CC BY-SA 4.0**
  (recorded in `docs/decisions.md`). Used for benchmarking only.
- Secrets live only in `.env` (git-ignored); `.env.example` is kept in sync.
- Key decisions: one database engine (PostgreSQL + pgvector), no SQLite as a primary database, read-only
  role for all agent and rule SQL, SELECT-only guardrails, simple bearer API key (OAuth2 documented as future).