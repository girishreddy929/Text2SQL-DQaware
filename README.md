# TrustSQL: DQ-Aware Agentic Text2SQL

Ask business questions in plain English and get **correct SQL, query results, a plain-English answer, and data-quality warnings**.

TrustSQL is a modular Text2SQL accelerator where new LLMs, databases, embedding models, or vector stores can be integrated through standardized interfaces.

**Status:** Blocks 0-5 and 7-11 completed (Foundation, Ingestion, DQCA Engine, and Metadata Intelligence Layers 1-4: Auto Metadata, Knowledge Graph, Business Ontology, and Vector Store). Block 6 (BigQuery/Dataplex parity) is deferred. Next milestone: **Phase 4 - Block 12: Baseline Text2SQL Chain & Golden Evaluation Set**.

---

## Modules

| Module | What it does | Status |
|----------|----------|----------|
| **A. DQCA Engine** | Transparent Dataplex-style profiling and automated data quality validation. Every rule exposes the SQL used for execution. | ✅ Blocks 3-5 Complete |
| **B. Metadata Intelligence** | Auto-generated descriptions, synonyms, Knowledge Graph join inference, Business Ontology, and pgvector semantic retrieval. | ✅ Blocks 7-11 Complete |
| **C. Agentic Text2SQL** | LangGraph multi-agent Text2SQL pipeline using Gemini, DQ Advisor, SQL validation, and self-correction agents. | 🚧 Planned (Blocks 12-17) |
| **D. API & Product Layer** | FastAPI async backend and Streamlit-based business UI with interactive dashboards. | 🚧 Planned (Blocks 17B-19) |

**Key Idea:** The DQCA engine generates trusted metadata. Metadata Intelligence organizes and enriches that metadata. Agentic Text2SQL consumes both to generate accurate SQL while warning users whenever underlying data contains quality issues.

---

## Tech Stack

- **Language & Runtime:** Python 3.13 (compatible with Python 3.11+), running inside a dedicated `.venv`.
- **Database:** PostgreSQL 16 + pgvector 0.8.7 (`trustsql-db` Docker container, host port `5433`).
- **ORM & Drivers:** SQLAlchemy 2.0 + psycopg3 (synchronous and asynchronous support).
- **LLM & Embeddings:** Google Gemini (`gemini-3.5-flash-lite`) and `gemini-embedding-001` using Matryoshka 768-dimensional embeddings via `langchain-google-genai`.
- **Graph & SQL Parsing:** NetworkX (`>=3.4`), `sqlglot` (planned).
- **Testing & Utilities:** pandas, pydantic, PyYAML, python-dotenv, pytest.

---

## Data Assets

### Olist Brazilian E-Commerce Dataset
- 11 raw source tables.
- Organized into four domain schemas:
  - `sales`
  - `customer`
  - `catalog`
  - `marketing`

### BIRD Mini-Dev (PostgreSQL Edition)
- 500 benchmark questions.
- 11 databases.
- 75 tables.
- 3,898,114 rows.
- Each benchmark database is loaded into an isolated schema:
  - `bird_<db_id>`

**License:** CC BY-SA 4.0

### Profile Switching

Switch datasets without code changes:

```env
PROFILE=olist
```

or

```env
PROFILE=bird
```

---

## Environment Setup

### Windows

```cmd
python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt

copy .env.example .env
REM Fill database passwords and GOOGLE_API_KEY

docker compose up -d

pytest -q
REM Expected: ~160 tests passed
```

### Linux / macOS

```bash
python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env

docker compose up -d

pytest -q
```

---

## Initial Data Ingestion (Run Once)

```cmd
python -m src.ingestion.download
python -m src.ingestion.load_raw
python -m src.ingestion.build_domains
python -m src.ingestion.setup_roles

python -m src.ingestion.bird_fetch
python -m src.ingestion.bird_dump_scan
python -m src.ingestion.bird_loader
python -m src.ingestion.bird_gold_check
```

> Re-run `setup_roles` whenever `build_domains` is executed again.

---

# Running Implemented Modules

## 1. DQCA Engine
### Profiling, Rule Evaluation, Scoring & Reports

```cmd
python -m src.dq.init_schema
REM Apply dq schema migrations

python -m src.dq.profiler --source olist
REM Generate profiling snapshot

python -m src.dq.profile_verify --source olist
REM Independently validate profiling statistics

python -m src.dq.runner --source olist
REM Execute YAML-defined DQ rules as t2s_reader

python -m src.dq.rule_verify --source olist
REM Independently validate rule outcomes

python -m src.dq.recommend_run --source olist --verify
REM Generate rule recommendations from profile analysis

python -m src.dq.score_run --source olist
REM Compute dimension-level and table-level DQ scores

python -m src.dq.report --source olist
REM Generates reports/dq_report_olist.md
```

### BIRD Example

```cmd
python -m src.dq.runner ^
    --source bird:california_schools ^
    --rules-dir config\dq_rules_bird
```

---

## 2. Metadata Intelligence (Layers 1-4)

### Schema Migrations

```cmd
docker exec -i trustsql-db psql -U trustsql_admin -d trustsql < sql\04_meta_schema.sql
docker exec -i trustsql-db psql -U trustsql_admin -d trustsql < sql\05_kg_schema.sql
docker exec -i trustsql-db psql -U trustsql_admin -d trustsql < sql\06_ontology_schema.sql
docker exec -i trustsql-db psql -U trustsql_admin -d trustsql < sql\07_embeddings_schema.sql
```

---

### Layer 1: Auto Metadata Generation & Description Scoring

```cmd
python -m src.metadata.generator --source olist

python -m src.metadata.generator ^
    --source bird:california_schools

python -m src.metadata.ref_loader

python -m src.metadata.desc_score ^
    --source bird:california_schools
```

Features:

- LLM-generated table descriptions
- LLM-generated column descriptions
- Human reference loading
- Automated metadata quality scoring

---

### Layer 2: Knowledge Graph & Multi-Hop Join Discovery

```cmd
python -m src.metadata.kg_infer --source olist

python -m src.metadata.bird_fk ^
    --db-id california_schools

python -m src.metadata.kg_loader --source olist

python -m src.metadata.kg_loader ^
    --source bird:california_schools

python -m src.metadata.kg_graph ^
    --source olist ^
    --from-table customer.customers ^
    --to-table catalog.products
```

Features:

- Join inference via value overlap
- Foreign key extraction
- KG node & edge persistence
- Multi-hop path discovery

---

### Layer 3: Business Ontology

```cmd
python -m src.metadata.ontology_loader --source olist

python -m src.metadata.ontology_loader ^
    --source bird:california_schools

python -m src.metadata.ontology_kg_sync --source olist

python -m src.metadata.ontology_kg_sync ^
    --source bird:california_schools
```

Features:

- Business terms
- Synonyms
- Metrics catalog
- Ontology-to-Knowledge-Graph linking

---

### Layer 4: Vector Embeddings & Hybrid Semantic Search

```cmd
python -m src.metadata.indexer --source olist

python -m src.metadata.indexer ^
    --source bird:california_schools

python -m src.metadata.retriever ^
    --source olist ^
    --query "Which customers had late deliveries and high payments?"
```

Features:

- Gemini Matryoshka embeddings
- 768-dimensional pgvector storage
- Semantic schema search
- Metadata retrieval for Text2SQL grounding

---

## Architecture Flow

```text
          ┌────────────────────┐
          │  Source Databases  │
          └─────────┬──────────┘
                    │
                    ▼
          ┌────────────────────┐
          │   DQCA Engine      │
          │ Profiling & Rules  │
          └─────────┬──────────┘
                    │
                    ▼
          ┌────────────────────┐
          │ Metadata Layer 1   │
          │ Auto Descriptions  │
          └─────────┬──────────┘
                    ▼
          ┌────────────────────┐
          │ Metadata Layer 2   │
          │ Knowledge Graph    │
          └─────────┬──────────┘
                    ▼
          ┌────────────────────┐
          │ Metadata Layer 3   │
          │ Business Ontology  │
          └─────────┬──────────┘
                    ▼
          ┌────────────────────┐
          │ Metadata Layer 4   │
          │ Vector Retrieval   │
          └─────────┬──────────┘
                    ▼
          ┌────────────────────┐
          │ Agentic Text2SQL   │
          │ (Planned)          │
          └─────────┬──────────┘
                    ▼
          SQL + Results + DQ Warnings
```

**Vision:** Build a fully transparent, metadata-driven, DQ-aware Text2SQL system where every generated answer is grounded in trusted schema knowledge, validated joins, semantic context, and data-quality evidence.

## How to Edit or Configure What’s Implemented So Far

### A. Adding or Editing Data Quality Rules

Data quality rules are defined declaratively in YAML:

- Olist rules: `config/dq_rules/`
- BIRD rules: `config/dq_rules_bird/`

Example:

```yaml
source_id: olist

rules:
  - id: orders_status_valid
    table: sales.orders
    type: SET
    column: order_status
    values:
      - delivered
      - shipped
      - canceled
      - invoiced
      - processing
    threshold: 99.0
    description: Order status belongs to the valid domain lifecycle
```

**Supported Rule Types**

- `NON_NULL`
- `UNIQUENESS`
- `RANGE`
- `SET`
- `REGEX`
- `ROW_CONDITION`
- `TABLE_CONDITION`
- `SQL_ASSERTION`

**Supported DQ Dimensions**

- Completeness
- Uniqueness
- Validity
- Consistency
- Timeliness
- Accuracy

**Apply Changes**

```cmd
python -m src.dq.runner --source olist
```

Rules are validated, compiled into SQL, and upserted within a single transaction.

---

### B. Tuning Profiler Settings

Edit:

```text
config/profiler.yaml
```

Example:

```yaml
top_n: 10
value_max_chars: 100

top_values_categories:
  - text
  - numeric
  - boolean

max_columns_per_query: 50
statement_timeout_seconds: 300
```

Parameter descriptions:

- `top_n` - Most frequent values captured per column
- `value_max_chars` - Max stored sample value length
- `top_values_categories` - Data types eligible for top-value profiling
- `max_columns_per_query` - Single-scan aggregation batch size
- `statement_timeout_seconds` - PostgreSQL execution timeout

---

### C. Configuring LLM Retries & Free-Tier Throttling

To handle Gemini free-tier rate limits (`429 RESOURCE_EXHAUSTED`), create or edit:

```text
config/llm.yaml
```

```yaml
max_attempts: 4
base_delay_seconds: 2.0
max_delay_seconds: 30.0
min_interval_seconds: 1.0
```

Parameter descriptions:

- `max_attempts` - Retry count for transient failures
- `base_delay_seconds` - Exponential backoff starting interval
- `max_delay_seconds` - Maximum backoff ceiling
- `min_interval_seconds` - Proactive throttling between requests

---

### D. Adding or Customizing Business Ontology Concepts

Edit:

```text
config/ontology/olist.yaml
```

or

```text
config/ontology/bird_california_schools.yaml
```

Example:

```yaml
source_id: olist

terms:
  - term_name: Gross Revenue
    term_type: metric
    definition: Total value paid by customers across all payment methods.
    sql_expression: SUM(payment_value)
    base_table: sales.order_payments

    mapped_columns:
      - payment_value

    synonyms:
      - total revenue
      - sales volume

    status: approved
```

Supported term types:

- `metric`
- `concept`
- `dimension`

Only **approved** terms are indexed into:

- Knowledge Graph
- Ontology Layer
- Vector Search

**Sync Changes**

```cmd
python -m src.metadata.ontology_loader --source olist

python -m src.metadata.ontology_kg_sync --source olist

python -m src.metadata.indexer --source olist
```

---

### E. Adjusting Join-Inference Sensitivity

Knowledge Graph relationships are inferred using value-overlap scoring.

Increase overlap threshold to reduce false positives:

```cmd
python -m src.metadata.kg_infer --source olist --min-overlap 0.85
```

Default threshold:

```text
0.75 (75%)
```

Higher thresholds increase precision while reducing discovered joins.

---

### F. Switching Database Profiles

Edit `.env`:

```env
PROFILE=olist
```

or

```env
PROFILE=bird
```

**Olist Profile**

Schemas:

```text
sales
customer
catalog
marketing
```

**BIRD Profile**

Schemas:

```text
bird_<db_id>
```

Each benchmark database remains isolated.

---

## Results Achieved So Far

### Data Quality Engine

#### Olist

- 41 production rules
- 35 passed
- 6 failed
- 0 errors
- Overall DQ score: **93.81**
- Profile verification:
  - 370 checks
  - 0 mismatches

#### BIRD (California Schools)

- 89 columns profiled
- 467 verification checks matched
- 92 rules promoted
- 100% overall score
- All promoted rules pass

---

### Knowledge Graph

#### Olist

- 126 structural nodes
- 7 ontology nodes
- **133 total nodes**
- **157 edges**
- Resolves multi-domain 3-hop paths:

```text
customers
   ↓
orders
   ↓
order_items
   ↓
products
```

#### BIRD California Schools

- 185 structural nodes
- 5 ontology nodes
- **190 total nodes**
- **193 edges**

Supports 2-hop relationship resolution through schools.

---

### Vector Search

#### Olist

```text
88 entities indexed
```

#### California Schools

```text
97 entities indexed
```

Storage:

```text
pgvector
768-dimensional Matryoshka embeddings
```

---

### Automated Testing

```text
160 tests passed
```

Executed through:

```cmd
pytest -v
```

---

## Security & Governance Guardrails

### Read-Only Enforcement

All execution occurs under:

```text
t2s_reader
```

Controls:

- Read-only transactions
- Statement timeout
- No DML permissions
- No schema modification access

---

### Schema Isolation

`t2s_reader` is explicitly restricted from:

```text
raw
dq
meta
app
```

Only approved business schemas are queryable.

---

### Deterministic Numeric Processing

All financial and scoring calculations use:

- Integer arithmetic
- Decimal arithmetic

to eliminate floating-point drift.

---

### Input Sanitization

Dynamic profiler SQL:

- Escapes identifiers safely
- Avoids bind-injection patterns
- Restricts generated SQL shapes

---

## Project Layout

```text
config/
│
├── settings.py
├── domains.yaml
├── profiler.yaml
├── llm.yaml
│
├── dq_rules/
├── dq_rules_bird/
├── dq_suggestions/
│
└── ontology/
    ├── olist.yaml
    └── bird_california_schools.yaml

sql/
│
├── 00_init_extensions.sql
├── 01_domain_schemas.sql
├── 02_dq_schema.sql
├── 03_dq_rules_schema.sql
├── 04_meta_schema.sql
├── 05_kg_schema.sql
├── 06_ontology_schema.sql
└── 07_embeddings_schema.sql

src/
│
├── common/
│   ├── db.py
│   ├── logging.py
│   ├── llm.py
│   ├── llm_guard.py
│   └── check_env.py
│
├── adapters/
│   ├── db/
│   │   ├── base.py
│   │   └── postgres.py
│   │
│   ├── llm/
│   │   ├── base.py
│   │   └── gemini.py
│   │
│   └── vectordb/
│       ├── base.py
│       └── pgvector.py
│
├── ingestion/
│   ├── download.py
│   ├── load_raw.py
│   ├── build_domains.py
│   ├── setup_roles.py
│   └── bird_* loaders
│
├── dq/
│   ├── profiler_sql.py
│   ├── profiler.py
│   ├── profile_verify.py
│   ├── rules_models.py
│   ├── rule_compiler.py
│   ├── runner.py
│   ├── recommender.py
│   ├── scoring.py
│   ├── report_md.py
│   └── report.py
│
└── metadata/
    ├── models.py
    ├── generator.py
    ├── ref_loader.py
    ├── desc_score.py
    ├── desc_rank.py
    │
    ├── kg_models.py
    ├── kg_infer.py
    ├── kg_builder.py
    ├── kg_loader.py
    ├── kg_graph.py
    ├── bird_fk.py
    │
    ├── ontology_models.py
    ├── ontology_loader.py
    ├── ontology_kg_sync.py
    │
    ├── indexer_prep.py
    ├── indexer.py
    └── retriever.py

tests/
│
├── test_block0
├── test_block1
├── ...
├── test_block11
│
└── 160 automated tests
    (markers: db, llm)

reports/
│
└── Generated DQ reports (Markdown)
```

---

## Roadmap

### Phase 1 — Foundation ✅

- Block 0
- Block 1
- Block 2
- Block 2B

---

### Phase 2 — DQCA Engine ✅

- Block 3
- Block 4
- Block 5

Deferred:

- Block 6 (BigQuery / Dataplex parity)

---

### Phase 3 — Metadata Intelligence ✅

- Block 7
- Block 8
- Block 9
- Block 10
- Block 11

---

### Phase 4 — Agentic Text2SQL 🚧

#### Block 12

Baseline Text2SQL Chain + Olist Golden Evaluation Set (~50 questions)

#### Block 12B

BIRD Evaluation Harness (~100 stratified questions)

#### Block 13

LangGraph Core StateGraph Pipeline

#### Block 14

Specialized Agents:

- Rewriter Agent
- Clarifier Agent
- Ontology Resolver Agent
- DQ Advisor Agent

#### Block 15

Semantic Cache + User Feedback Loop

#### Block 16

Cross-Domain Query Routing + Multi-Hop KG Integration

#### Block 17

Baseline vs Agentic Evaluation + Ablation Studies

---

### Phase 5 — Product & Documentation 🚧

Blocks 17B-19

- FastAPI Backend
- Streamlit UI
- Extensibility Demonstration
- Production Documentation
- Final Architecture & Evaluation Report

---

## Current Completion Status

```text
✅ Foundation                 (Blocks 0–2B)
✅ DQCA Engine                (Blocks 3–5)
⏸️ Dataplex Parity           (Block 6 Deferred)
✅ Metadata Intelligence      (Blocks 7–11)
🚧 Agentic Text2SQL          (Blocks 12–17)
🚧 Productization            (Blocks 17B–19)
```

**TrustSQL currently delivers a fully operational DQ-aware metadata intelligence platform with profiling, rule execution, scoring, knowledge graph generation, ontology management, and semantic retrieval. The next major milestone is transforming these metadata assets into an end-to-end Agentic Text2SQL system powered by LangGraph and Gemini.**