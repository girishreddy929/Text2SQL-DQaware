# TrustSQL Architecture

```mermaid
graph TD
    %% External Interfaces
    User([Business User])
    UI[Streamlit UI]
    API[FastAPI Backend]
    LangSmith[LangSmith Tracing]

    %% LangGraph Engine
    subgraph LangGraph Engine
        Router[Router Node]
        Clarifier[Clarifier Node]
        Cache[Semantic Cache Node]
        Ontology[Ontology Resolver]
        Linker[Schema Linker]
        Domain[Domain Selector]
        Generator[SQL Generator]
        Validator[SQL Validator]
        Executor[SQL Executor]
        Corrector[Error Corrector]
        DQAdvisor[DQ Advisor]
    end

    %% Databases
    subgraph PostgreSQL 16
        DB_Raw[(Raw Data Schemas)]
        DB_Meta[(Meta Schema: KG & Ontology)]
        DB_Vector[(Vector Schema: pgvector)]
        DB_DQ[(DQ Schema: Rules & Results)]
        DB_App[(App Schema: Cache)]
    end

    %% Flow
    User <-->|Natural Language| UI
    UI <-->|REST JSON| API
    API --> Router
    API -.->|Traces| LangSmith

    Router --> Clarifier
    Clarifier --> Cache
    Cache -- Hit --> Executor
    Cache -- Miss --> Ontology
    
    Ontology --> Linker
    Linker --> Domain
    Domain --> Generator
    Generator --> Validator
    Validator -- Valid --> Executor
    Validator -- Invalid --> Corrector
    Corrector --> Generator
    
    Executor --> DQAdvisor
    
    %% DB Connections
    Cache <--> DB_App
    Ontology <--> DB_Meta
    Linker <--> DB_Vector
    Domain <--> DB_Meta
    Executor <--> DB_Raw
    DQAdvisor <--> DB_DQ


### 2. Decisions Log
Save this as `docs/decisions.md`. This fulfills the requirement in your Master Prompt to record the BIRD license and architectural choices.

```markdown
# Architectural Decisions Log

## 1. Database Engine
**Decision:** Use PostgreSQL 16 + `pgvector` as the single unified database.
**Rationale:** Avoids the complexity of maintaining a separate vector database (like Milvus or Pinecone) and a separate graph database (like Neo4j). Postgres handles relational data, vector embeddings, and JSONB (for Knowledge Graph properties) natively.

## 2. Orchestration Framework
**Decision:** Use LangGraph instead of standard LangChain chains.
**Rationale:** Text2SQL requires cyclic, stateful workflows (e.g., "If SQL fails execution, send the error back to the LLM to fix it"). LangGraph's state machine architecture makes this self-healing loop trivial to implement and trace.

## 3. Evaluation Benchmark
**Decision:** Use the BIRD (A Big Bench for Large-Scale Database Grounded Text-to-SQLs) Mini-Dev dataset for evaluation.
**License Record:** The BIRD dataset is used under the **CC BY-SA 4.0** license.
**Rationale:** BIRD is the industry standard for enterprise Text2SQL, featuring complex cross-domain joins and dirty data, which perfectly tests our Knowledge Graph and DQ Engine.

## 4. Embedding Dimensionality
**Decision:** Truncate Gemini's 3072-dimension embeddings to 768 dimensions using Matryoshka Representation Learning (MRL) and L2 normalization.
**Rationale:** `pgvector` has a hard limit of 2,000 dimensions for HNSW indexes. MRL allows us to slice the vectors without losing significant semantic meaning, enabling fast, indexed vector search.

## 5. Data Quality (DQ) Engine
**Decision:** Build a transparent, SQL-based DQ engine rather than using black-box Python libraries (like Great Expectations).
**Rationale:** Every DQ rule compiles down to a readable SQL statement. This allows the LLM (and human auditors) to see exactly how a metric like "Completeness" was calculated.