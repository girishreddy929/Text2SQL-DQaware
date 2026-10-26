# TrustSQL: DQ-Aware Agentic Text2SQL

TrustSQL is an enterprise-grade Agentic Text2SQL platform that enables business users to query data using natural language while delivering accurate SQL, trustworthy results, and real-time Data Quality (DQ) advisories.

Unlike traditional Text2SQL systems that rely solely on LLM prompting, TrustSQL combines Knowledge Graphs, Vector Search, Data Quality Intelligence, and a LangGraph-powered multi-agent architecture to reduce hallucinations, improve schema understanding, and ensure reliable cross-domain querying.

---

## 🚀 Key Capabilities

✅ Natural Language → SQL Generation

✅ Data Quality-Aware Query Responses

✅ Knowledge Graph-Based Join Intelligence

✅ Semantic Schema Linking with Vector Search

✅ Multi-Agent LangGraph Orchestration

✅ Self-Healing SQL Generation & Validation

✅ Business Ontology-Driven Metrics

✅ Cross-Domain Query Routing

✅ Production-Ready FastAPI Backend

---

## 🏗️ Architecture Overview

TrustSQL is organized into four core modules:

### Module A: Data Quality Intelligence (DQCA Engine)

Provides automated data profiling, validation, and quality monitoring.

#### Features

- Automated data profiling
- Dataplex-style rule evaluation
- Data quality scoring
- Dynamic DQ advisory generation

#### Supported Rule Types

- Non-Null
- Uniqueness
- Range Validation
- Set Membership
- Regex Validation
- Row Conditions
- Table Conditions
- SQL Assertions

---

### Module B: Metadata Intelligence Layer

#### Layer 1: Metadata Enrichment

- LLM-generated table descriptions
- LLM-generated column descriptions
- Automated PII detection and tagging

#### Layer 2: Knowledge Graph

NetworkX-powered metadata graph containing:

- Tables
- Columns
- Relationships
- Explicit Foreign Keys
- Inferred Foreign Keys

Benefits:

- Accurate JOIN generation
- Relationship discovery
- Cross-domain navigation
- Reduced hallucinations

#### Layer 3: Business Ontology

Business definitions stored as YAML and injected directly into agent context.

Example:

```yaml
gross_revenue:
  definition: Total revenue before deductions
  formula: order_value + shipping_charges
```

Benefits:

- Consistent business logic
- Metric standardization
- Improved SQL accuracy

#### Layer 4: Vector Search

Semantic schema retrieval powered by:

- Gemini Embeddings
- pgvector
- Matryoshka Embeddings

Capabilities:

- Schema linking
- Semantic search
- Context reduction
- Domain selection

---

### Module C: Agentic Text2SQL Engine

Built using LangGraph to orchestrate specialized agents.

#### Agent Pipeline

```text
User Question
       │
       ▼
Router Agent
       │
       ▼
Clarifier Agent
       │
       ▼
Semantic Cache
       │
       ▼
Schema Linker
       │
       ▼
Domain Selector
       │
       ▼
SQL Generator
       │
       ▼
SQL Validator
       │
       ▼
Self-Healing Loop
       │
       ▼
Query Execution
       │
       ▼
DQ Advisor
       │
       ▼
Final Response
```

#### Core Capabilities

- Intent Classification
- Ambiguity Resolution
- Semantic Query Caching
- Graph-Aware JOIN Generation
- SQL Validation
- Self-Healing Error Recovery
- SQL Injection Protection
- DQ-Aware Responses

---

### Module D: API & Product Layer

#### Current

- FastAPI backend
- REST APIs
- Authentication support

#### Upcoming

- Streamlit Chat Interface
- DQ Dashboards
- Metadata Review Console
- Ontology Management UI

---

## 🛠️ Technology Stack

### Application

- Python 3.11+
- FastAPI
- LangGraph
- LangChain
- SQLAlchemy

### Database

- PostgreSQL 16
- pgvector 0.8.7

### AI Stack

- Gemini Flash
- Gemini Embeddings

### Metadata & Validation

- NetworkX
- sqlglot

---

## ⚙️ Setup

### 1. Clone Repository

```cmd
git clone <repository_url>
cd trustsql
```

### 2. Create Virtual Environment

```cmd
python -m venv .venv

.venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Start PostgreSQL

```cmd
docker compose up -d
```

### 4. Configure Environment

```cmd
copy .env.example .env
```

Update `.env`:

```env
GOOGLE_API_KEY=your_api_key

GEMINI_CHAT_MODEL=gemini-3.5-flash-lite

TRUSTSQL_API_KEY=trustsql-secret-key
```

---

## 🏃 Running TrustSQL

### Start API Server

```cmd
uvicorn src.api.main:app --reload --port 8000
```

### Test API

```cmd
python -m src.api.test_client
```

---

## 📊 Evaluation Results

TrustSQL includes an evaluation framework comparing a traditional LangChain baseline against the full Agentic Pipeline using a curated Olist Golden Dataset.

### Execution Accuracy

| System | Accuracy |
|----------|----------|
| LangChain Baseline | 80% |
| TrustSQL Agentic Pipeline | 92% |

### Improvements

- Accurate Cross-Domain Joins
- Better Business Metric Understanding
- Reduced Hallucinations
- Self-Healing SQL Correction
- Stronger SQL Validation
- DQ-Enriched Business Responses

### Run Agentic Evaluation

```cmd
python -m src.eval.eval_agentic
```

### Run Baseline Evaluation

```cmd
python -m src.eval.runner
```

---

## 📌 Sample Response

### User Question

```text
What was the gross revenue generated by customers from São Paulo in Q1?
```

### Generated SQL

```sql
SELECT ...
```

### Query Result

```json
{
  "gross_revenue": 1284937.22
}
```

### Data Quality Advisory

```text
Warning:
Customer table failed Completeness checks during the latest DQ scan.

Revenue figures may contain missing customer records.
```

---

## 🗺️ Project Roadmap

### Phase 1
Foundation & Benchmark Loading

### Phase 2
DQCA Engine

### Phase 3
Metadata Intelligence Platform

### Phase 4
Agentic Text2SQL Engine

### Phase 5
FastAPI Productization

### Phase 6
Streamlit Experience Layer

### Phase 7
Enterprise Readiness & Extensibility

---

## 🎯 Why TrustSQL?

Most Text2SQL solutions focus solely on generating SQL.

TrustSQL goes further by combining:

- Data Quality Intelligence
- Knowledge Graph Reasoning
- Semantic Search
- Business Ontology Awareness
- Agentic AI Workflows

The result is a platform that not only answers business questions but also helps users understand whether the underlying data can be trusted.