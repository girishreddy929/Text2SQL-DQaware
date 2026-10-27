# TrustSQL: DQ-Aware Agentic Text2SQL

TrustSQL is an enterprise-grade, modular Text2SQL accelerator. It allows business users to ask questions in plain English and receive syntactically correct SQL, the resulting data, and, crucially, **Data Quality (DQ) advisories** warning them if the underlying data is flawed.

Unlike standard Text2SQL wrappers, TrustSQL uses a multi-agent architecture (LangGraph) backed by a Knowledge Graph and Vector Search to eliminate hallucinations, self-heal SQL errors, and guarantee accurate cross-domain joins.

---

## 🏗️ Core Architecture

TrustSQL is divided into four main modules:

### 1. Module A: DQCA Engine (Data Quality)
- Transparent, Dataplex-style data profiling and rule execution.
- Supports 8 rule types:
  - Non-Null
  - Uniqueness
  - Range
  - Set
  - Regex
  - Row Conditions
  - Table Conditions
  - SQL Assertions
- Auto-recommends rules based on data profiles.

### 2. Module B: Metadata Intelligence

#### Layer 1: Descriptions
- LLM-generated table and column descriptions.
- Automatic PII tagging.

#### Layer 2: Knowledge Graph
- NetworkX-powered graph of tables, columns, and inferred/explicit foreign keys.
- Guarantees accurate SQL `JOIN` paths.

#### Layer 3: Business Ontology
- YAML-driven business metric definitions.
- Example: "Gross Revenue".
- Injected directly into LLM context.

#### Layer 4: Vector Search
- 768-dimensional Matryoshka embeddings.
- Stored in `pgvector`.
- Enables semantic schema linking.

### 3. Module C: Agentic Text2SQL (LangGraph)

A stateful, multi-agent pipeline featuring:

#### Router & Clarifier
- Classifies intent.
- Requests clarification for ambiguous questions.

#### Semantic Cache
- Bypasses LLM calls for previously answered questions.

#### Schema Linker & Domain Selector
- Uses Vector Search and Knowledge Graph.
- Retrieves only relevant tables.
- Provides exact join paths for cross-domain queries.

#### Self-Healing Loop
- Validates SQL AST using `sqlglot`.
- Detects execution failures.
- Automatically retries SQL correction up to 3 times.

#### DQ Advisor
- Attaches dimension-aware data quality warnings.
- Alerts users when queried tables fail recent DQ checks.

### 4. Module D: API & Product
- FastAPI backend exposing REST endpoints.
- Streamlit UI for:
  - Conversational analytics
  - Data visualization
  - Semantic Cache feedback

---

## 🚀 Tech Stack

- **Language:** Python 3.11+
- **Database:** PostgreSQL 16 + `pgvector` (0.8.7)
- **LLM:**
  - `gemini-3.5-flash-lite` (chat)
  - `gemini-embedding-001` (embeddings)
- **Frameworks:**
  - LangGraph
  - LangChain
  - FastAPI
  - Streamlit
  - SQLAlchemy
  - NetworkX
  - sqlglot

---

## 🛠️ Setup Instructions

### 1. Prerequisites

- Docker Desktop running
- Python 3.11+ installed
- Windows Command Prompt (`cmd`) as the primary shell

### 2. Environment Setup

Clone the repository and create a virtual environment:

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Database Initialization

Start the PostgreSQL container:

```cmd
docker compose up -d
```

### 4. Configuration

Copy the example environment file:

```cmd
copy .env.example .env
```

Update `.env`:

```env
GOOGLE_API_KEY=your_gemini_api_key_here
GEMINI_CHAT_MODEL=gemini-3.5-flash-lite
TRUSTSQL_API_KEY=trustsql-secret-key

# Optional: Enable LangSmith Tracing
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_key
```

---

## 🏃‍♂️ Running the Application

You need two terminal windows to run the full stack.

### Terminal 1: Start the FastAPI Server

```cmd
uvicorn src.api.main:app --reload --port 8000
```

### Terminal 2: Start the Streamlit UI

```cmd
streamlit run app/streamlit_app.py
```

---

## 🔌 Bring Your Own Database (Extensibility)

TrustSQL is database-agnostic and can be adapted to virtually any SQL platform.

### Step 1: Write an Adapter

Create a new file under:

```text
src/adapters/db/
```

Implement the `DBConnector` interface including:

- `run_query`
- `list_columns`
- `list_tables`

See:

```text
src/adapters/db/sqlite.py
```

for a reference implementation.

### Step 2: Update Settings

Modify your `.env` file:

```env
DB_BACKEND=your_custom_adapter
```

### Step 3: Run the Ingestion Pipeline

Execute:

- DQ Profiler (`src.dq.profiler`)
- Metadata Generator (`src.metadata.generator`)
- Vector Indexer (`src.metadata.indexer`)

This populates:

- Knowledge Graph
- Metadata Catalog
- Vector Store

### Step 4: Query

Launch the Streamlit UI and begin asking business questions.

TrustSQL agents automatically leverage:

- Business ontology
- Schema metadata
- Knowledge Graph relationships
- Vector search context

for accurate SQL generation.

---

## 📊 Evaluation & Future Testing

### Olist Golden Set Results

On a benchmark of **50 complex analytical queries**, the Agentic Pipeline achieved:

| Approach | Execution Accuracy |
|-----------|------------------|
| Standard LangChain Baseline | ~80.0% |
| TrustSQL Agentic Pipeline | ~92.0% |

### Future Validation: BIRD Benchmark

To further demonstrate robustness, TrustSQL will be evaluated on the **BIRD Benchmark (Big Bench for Large-Scale Database Grounded Text-to-SQLs)**.

#### Current Status

- BIRD Mini-Dev dataset loaded.
- 11 databases available under `bird_*` PostgreSQL schemas.
- 500 benchmark questions ready for evaluation.

#### Next Steps

1. Run the DQ Profiler across all BIRD databases.
2. Generate metadata and knowledge graphs.
3. Build vector indexes.
4. Execute:

```text
src.eval.bird_runner
```

5. Measure execution accuracy across:
   - Cross-domain databases
   - Noisy enterprise-style datasets
   - Complex multi-hop analytical questions

> Note: The BIRD dataset is used under the CC BY-SA 4.0 License.

---

## 🎯 Key Differentiators

- ✅ Data Quality-aware query responses
- ✅ Multi-agent LangGraph architecture
- ✅ Knowledge Graph-based join path resolution
- ✅ Semantic schema linking with vector search
- ✅ Self-healing SQL generation loop
- ✅ Business ontology injection
- ✅ Cross-domain query routing
- ✅ Semantic caching for lower latency and cost
- ✅ Database-agnostic architecture
- ✅ Enterprise-ready deployment model

TrustSQL bridges the gap between conversational analytics and trustworthy enterprise data access by combining Data Quality governance, metadata intelligence, knowledge graphs, vector retrieval, and agentic SQL generation into a single platform.