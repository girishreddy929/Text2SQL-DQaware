# TrustSQL: DQ-Aware Agentic Text2SQL

Ask business questions in plain English and get **correct SQL, results, a plain-English answer and data-quality warnings**.
TrustSQL is also a modular Text2SQL accelerator: a new LLM, database or vector store plugs in through an interface.

**Status:** Blocks 0 to 5 done (foundation, data, profiler, rule engine, scoring and report). Next: Block 6 (BigQuery/Dataplex parity).

## Modules
| Module | What it does | Status |
|---|---|---|
| A. DQCA engine | Transparent rebuild of Dataplex profiling and auto data quality. Every rule shows the exact SQL it runs. | Blocks 3 to 5 done |
| B. Metadata intelligence | Auto descriptions, synonyms, Knowledge Graph, Ontology (human reviewed) | planned (Blocks 7 to 11) |
| C. Agentic Text2SQL | LangGraph multi-agent pipeline on Gemini, with DQ warnings | planned (Blocks 12 to 17) |
| D. API and product | FastAPI backend and Streamlit UI | planned (Blocks 17B to 19) |

Key idea: DQCA feeds metadata, metadata feeds the agents, and the agents warn users when the data they used has quality issues.

## Tech stack
Python 3.13 (3.11+ works), PostgreSQL 16 + pgvector (Docker), SQLAlchemy 2.0 + psycopg 3, pandas, pydantic, PyYAML,
Google Gemini via LangChain (later LangGraph), sqlglot, NetworkX, FastAPI, Streamlit, pytest.

## Data
- **Olist** Brazilian e-commerce (9 CSVs) and Olist marketing funnel (2 CSVs) from Kaggle: 11 raw tables, loaded into 4 domain schemas
  (`sales`, `customer`, `catalog`, `marketing`).
- **BIRD Mini-Dev (PostgreSQL version)**: 500 questions, 11 databases, 75 tables, 3,898,114 rows. Each database is its own schema `bird_<db_id>`.
  Licence CC BY-SA 4.0.
- Two profiles on one codebase (`PROFILE=olist|bird` in `.env`).

## Setup (Windows cmd; Mac/Linux: same commands, `source .venv/bin/activate`)
```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          (then fill in passwords and GOOGLE_API_KEY)
docker compose up -d            (PostgreSQL 16 + pgvector, host port 5433)
pytest -q                       (expect: all passed)
```

Load the data once, in this order:
```cmd
python -m src.ingestion.download
python -m src.ingestion.load_raw
python -m src.ingestion.build_domains
python -m src.ingestion.setup_roles          (re-run after every build_domains)
python -m src.ingestion.bird_fetch
python -m src.ingestion.bird_dump_scan
python -m src.ingestion.bird_loader
python -m src.ingestion.bird_gold_check
```

## DQCA engine: how to use it
```cmd
python -m src.dq.init_schema                                   create dq tables
python -m src.dq.profiler --source olist                       profile every column (dated snapshot)
python -m src.dq.profile_verify --source olist                 independent recheck of the profile
python -m src.dq.runner --source olist                         run the YAML rules as the read-only role
python -m src.dq.rule_verify --source olist                    independent recheck of 18 rules
python -m src.dq.recommend_run --source olist --verify         suggest new rules from the profile
python -m src.dq.score_run --source olist                      scores by dimension and table (+ SQL cross-check)
python -m src.dq.report --source olist                         writes reports/dq_report_olist.md
```
Other sources: `--source bird:california_schools` (BIRD rules: `--rules-dir config\dq_rules_bird` on the runner).

**Rule types:** NON_NULL, UNIQUENESS, RANGE, SET, REGEX, ROW_CONDITION, TABLE_CONDITION, SQL_ASSERTION.
**Dimensions:** Completeness, Uniqueness, Validity, Consistency, Timeliness, Accuracy.
A rule passes when the share of passing rows is at least its `threshold`.

Add a rule by editing a YAML file in `config/dq_rules/`:
```yaml
source_id: olist
rules:
  - id: orders_status_valid
    table: sales.orders
    type: SET
    column: order_status
    values: [delivered, shipped, canceled]
    threshold: 99
    description: Order status is one of the known values
```
**Workflow:** profile, scan, read the report. The recommender writes proposals to `config/dq_suggestions/`; nothing runs until you
copy the rules you accept into a rules folder (human approval).

**Scoring:** rule score = pass %; dimension, table and overall scores = plain average of rule scores; errored rules are listed, not scored.
Bands: Good >= 99, Fair >= 95, otherwise Poor. Group scores are rounded to 2 decimals, so the report also shows exact pass rates for failing rules.

## Results so far
- Olist: 41 rules, 35 passed / 6 failed / 0 errors; overall score 93.81. Profile verifier 370 checks, 0 mismatches.
- BIRD `california_schools`: 89 columns profiled (467 checks match), 92 suggested rules, all pass.
- Gold queries: 498 of 500 BIRD gold queries return rows (2 empty by design of the data).
- Tests: 108 passed.

## Guardrails
SELECT only; queries run as the read-only role `t2s_reader` with timeouts; the role cannot read the `raw`, `dq`, `meta` or `app` schemas;
secrets only in `.env`. Auto-LIMIT, PII masking and AST-level SQL validation arrive with the agents.

## Project layout
```
config/        settings.py, domains.yaml, profiler.yaml, dq_rules/ (Olist), dq_rules_bird/, dq_suggestions/ (generated)
sql/           00_init_extensions, 01_domain_schemas (generated), 02_dq_schema, 03_dq_rules_schema
src/common/    db, logging, llm, list_models, check_env
src/adapters/  db/ (base, postgres), llm/, vectordb/
src/ingestion/ download, load_raw, build_domains, setup_roles, bird_* loaders
src/dq/        profiler, rules, runner, recommender, scoring, report (see commands above)
src/metadata/, src/text2sql/, src/api/, src/eval/   (planned)
tests/         test_block0 ... test_block5 (108 tests; markers: db, llm)
reports/       generated DQ reports (Markdown)
```

## Roadmap
6 BigQuery/Dataplex parity | 7 to 11 metadata, knowledge graph, ontology, embeddings | 12 to 17 Text2SQL (baseline, BIRD eval, LangGraph, cache,
cross-domain, evaluation) | 17B API | 18 Streamlit | 18B extensibility proof | 19 final docs.

## Notes
- Run all modules from the project root: `python -m src.<package>.
- Run all modules from the project root: `python -m src.<package>.<module>`.
- Timestamps in `dq.*` tables are `timestamptz`: logs print local time, some queries print UTC.
- Generated files: `sql/01_domain_schemas.sql` (from `config/domains.yaml`) and `reports/*.md`. Everything under `data/` is git-ignored.
- Licences: BIRD Mini-Dev is CC BY-SA 4.0. Check the licence on the Olist Kaggle dataset page before redistributing any data.
- Final documentation (diagrams, decisions, demo script, Dataplex comparison) is planned for Block 19 in `docs/`.