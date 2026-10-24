# TrustSQL: DQ-Aware Agentic Text2SQL Accelerator

TrustSQL is an enterprise-grade, modular Text2SQL accelerator. It combines transparent Data Quality Profiling & Auditing (DQCA), Metadata Intelligence, Business Ontology, Knowledge Graphs, and Multi-Agent Orchestration (LangGraph + Google Gemini) to convert natural language into validated, read-only SQL paired with actionable data quality advisories.

---

## 1. Current State (Blocks 0–5, 7–14 Completed)

### Database Engine & Security (Blocks 0–2, 2B)
- PostgreSQL 16 + pgvector containerized on port 5433.
- Strict least-privilege role separation:
  - `trustsql_admin` for schema and data management.
  - `t2s_reader` for read-only access with:
    - 30-second statement timeout
    - Restricted access to internal schemas

### Dual Datasets
- **Olist**
  - Brazilian e-commerce dataset
  - 11 tables across:
    - Sales
    - Customer
    - Catalog
    - Marketing

- **BIRD**
  - Full BIRD Mini-Dev benchmark
  - 11 schemas (`bird_<db_id>`)
  - 75 tables
  - 3.89M rows

### Transparent DQCA Engine (Blocks 3–5)
- Full SQL rule compiler
- Table profiler
- Rule recommender
- Dimension-based scoring
- Markdown report generation
- Coverage:
  - 41 Olist rules
  - 92 BIRD `california_schools` rules

### Metadata Intelligence & Knowledge Graph (Blocks 8–10)
- Generated table and column descriptions
- PII tagging evaluated against BIRD human baselines
- Inferred and FK join graphs persisted in:
  - `meta.kg_nodes`
  - `meta.kg_edges`
- NetworkX Dijkstra multi-hop shortest-join discovery
- Business Ontology:
  - Stored in `config/ontology/`
  - Synced to `meta.ontology_terms`
  - Defines approved SQL formulas for business metrics
  - Connected through `measures` edges

### Vector Search (Block 11)
- Tables, columns, and ontology terms embedded using:
  - `gemini-embedding-001`
- Reduced to 768 dimensions using:
  - Matryoshka Representation Learning (MRL)
- Stored in:
  - `meta.schema_embeddings`
- Indexed with:
  - HNSW cosine similarity index

### Evaluation Harnesses (Blocks 12, 12B)
- sqlglot AST guardrails:
  - SELECT-only validation
  - Data-modifying CTE protection
  - Automatic LIMIT injection
- Tolerant execution comparison:
  - Numeric tolerance
  - String trimming
  - Multiset comparison
- Stratified 100-question BIRD sampler:
  - `data/bird/mini_dev_sample_100.json`
  - Persistent disk caching
  - Gemini Free Tier throttling (4.2s)

### Agentic Multi-Agent System (Blocks 13–14)

#### Intent Router
Classifies requests into:
- `data_question`
- `dq_question`
- `metadata_question`
- `out_of_scope`

#### Query Rewriter
- Resolves conversational context from chat history
- Includes single-turn fast-path bypass

#### Clarifier
- Detects critical ambiguities before SQL generation

#### Ontology Resolver
- Dynamically injects approved metric formulas
- Example: Gross Revenue

#### Self-Healing Loop
- Corrects AST and runtime failures
- Maximum of 3 retries

#### Specialist Paths
Dedicated handlers for:
- DQ scan lookups
- Ontology definitions
- Corporate-safe refusals

#### Dynamic DQ Advisor
- Queries:
  - `dq.latest_results`
  - `dq.latest_profiles`
- Executes using `t2s_reader`
- Attaches dimension-driven quality advisories to responses

---

## 2. Tech Stack

### Runtime & Environment
- Python 3.13.5 (venv)
- Windows Command Prompt

### Database
- PostgreSQL 16
- pgvector 0.8.7
- Docker Compose

### Data Access
- SQLAlchemy 2.0
- psycopg 3 (synchronous)
- pandas

### LLM & Embeddings
- Google Gemini
  - `gemini-3.5-flash-lite`
  - `gemini-embedding-001`
- `langchain-google-genai`

### Agent Orchestration
- LangGraph (>= 0.2.0)
- LangChain Core

### SQL & Graph Analytics
- sqlglot (>= 25.0.0)
- NetworkX (>= 3.4)

### Validation & Testing
- Pydantic v2
- PyYAML
- pytest

---

## 3. Directory Layout

```text
config/                     # Database settings, domain definitions,
                            # DQ rules, and ontology YAMLs

data/                       # Raw CSVs, BIRD Mini-Dev databases,
                            # samples, and evaluation cache

prompts/                    # Metadata generation and Text2SQL prompts

reports/                    # Generated DQ markdown reports

sql/                        # Idempotent DDL migrations (00–07 schemas)

src/
├── adapters/               # Abstract & concrete interfaces
│                           # (DB, LLM, VectorDB)
├── common/                 # Connectors, logging, resilient LLM invocation
├── dq/                     # Profiler, compiler, runner, recommender, scoring
├── eval/                   # Comparison engine, golden runner,
│                           # BIRD evaluation harness
├── ingestion/              # Olist loader, BIRD loader,
│                           # domain builder, role manager
├── metadata/               # Metadata generation, KG builder,
│                           # ontology sync, vector indexing
├── text2sql/
│   ├── baseline/           # Single-shot baseline chain
│   │                       # and schema context builder
│   └── agents/             # Router, rewriter, clarifier,
│                           # ontology, generator, validator,
│                           # executor, corrector, dq_advisor,
│                           # specialists, graph
└── tests/                  # Comprehensive test suite

193 tests passed across Blocks 0–14
```

---

## 4. Setup & Quickstart

### 1. Prerequisites & Environment

Ensure Docker Desktop is running, then activate your virtual environment:

```cmd
.venv\Scripts\activate
```

Create a `.env` file from `.env.example`:

```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_DB=trustsql

POSTGRES_ADMIN_USER=trustsql_admin
POSTGRES_ADMIN_PASSWORD=your_admin_password

T2S_READER_PASSWORD=your_reader_password

GOOGLE_API_KEY=your_gemini_api_key
```

### 2. Start PostgreSQL Container

```cmd
docker compose up -d
```

### 3. Initialize Roles & Privileges

Apply read-only role grants and DQ access views:

```cmd
python -m src.ingestion.setup_roles
```

---

## 5. Usage & Agent Execution

### Run End-to-End Multi-Agent Pipeline

Execute the complete LangGraph workflow:

```cmd
python -m src.text2sql.agents.graph
```

### Test Individual Agents

#### Intent Router

```cmd
python -m src.text2sql.agents.router
```

#### Query Rewriter

```cmd
python -m src.text2sql.agents.rewriter
```

#### Ambiguity Clarifier

```cmd
python -m src.text2sql.agents.clarifier
```

#### Ontology Resolver

```cmd
python -m src.text2sql.agents.ontology_resolver
```

#### DQ Advisor (Dynamic Advisories)

```cmd
python -m src.text2sql.agents.dq_advisor
```

#### Specialist Handlers (DQ, Metadata, Refusal)

```cmd
python -m src.text2sql.agents.specialists
```

---

## 6. Evaluations & Testing

### Run Olist Golden Evaluation

Evaluates the baseline against golden queries:

```cmd
python -m src.eval.runner --limit 10
```

### Run BIRD Benchmark Sample

Runs a stratified BIRD evaluation using cached responses:

```cmd
python -m src.eval.bird_runner --limit 5
```

### Run Full Test Suite

```cmd
pytest -q
```

Example output:

```text
193 passed in ~21s
```