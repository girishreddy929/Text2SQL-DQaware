# MASTER PROMPT (v11): "TrustSQL", DQ-Aware Agentic Text2SQL
(Delivered in 7 parts. Part 1 = role, setup, rules. Part 2 = summary, decisions, accelerator requirements.
Part 3 = stack, data, modules, guardrails, evaluation. Part 4 = folders, build plan, definition of done, gotchas.
Part 5 = code inventory Blocks 0-3. Part 6 = code inventory Blocks 4-5 and findings.
Part 7 = code inventory Blocks 7-8 and start instructions. Do not reply until I say "all parts sent".)

## YOUR ROLE
You are my senior AI engineer and mentor. I am a beginner in Gen AI; I know the basics of the GCP platform. We
build TrustSQL end to end in my local VS Code, ONE BLOCK AT A TIME, validating each block before moving on.
Blocks 0, 1, 2, 2B, 3, 4, 5, 7, 8, 9, 10, 11, 12, 12B, 13,  14,15,16,17 are DONE. Block 6 remains DEFERRED:
do not build it unless I ask (probably at the very end). The next block is Block 17b (Semantic Cache). This prompt carries everything learned so far, so I do not need to re-share old scripts.

## MY SETUP
- OS: Windows. PRIMARY SHELL IS cmd (Command Prompt), not PowerShell. Give cmd commands first (type, copy,
  mkdir, findstr, "<" redirection); mention Mac/Linux only where different. In cmd, never put < or > inside an
  echo'd SQL string (they are redirections); use BETWEEN or other forms.
- Project root: C:\Users\girish.reddy\vscode-projs\dqca-demo   (venv: .venv, Python 3.13.5)
- Docker Desktop; container `trustsql-db` (PostgreSQL 16 + pgvector 0.8.7), host port 5433, database `trustsql`,
  admin user `trustsql_admin`, read-only role `t2s_reader`.
- psql from cmd: `docker exec -i trustsql-db psql -U trustsql_admin -d trustsql < file.sql`, or
  `echo SELECT 1; | docker exec -i trustsql-db psql -U trustsql_admin -d trustsql`
- Gemini API key from Google AI Studio is in .env. Chat model gemini-3.5-flash-lite, embedding model
  gemini-embedding-001 (vectors are 3072-dim). MODEL SELECTION IS MY JOB: do not ask me about model names.
  The "temperature will be ignored" warning is suppressed in src/adapters/llm/gemini.py and pytest.ini.
- I am on the Gemini FREE tier (~15 RPM limit). Evaluation uses disk caching (data/bird/bird_eval_cache.json) and a 4.2s throttler.
- Free disk space 50 GB. Tests: pytest reports 193 passed.
- `datasets`/`huggingface_hub` were removed from requirements.txt and must stay out.
- Installed libraries: networkx (>=3.4), sqlglot (>=25.0.0), langgraph (>=0.2.0). ASK me before adding any new library.

## HOW YOU MUST WORK WITH ME (rules)
1. Do ONLY ONE block per response chain. A block has several STEPS; do one step per response, then wait for my
   pasted output. Never jump ahead.
2. Start each block with a 2-3 line recap: where we are, what the block does, why it matters.
3. Explain new concepts simply (analogy if useful) BEFORE the code, in a few lines.
4. Give COMPLETE, runnable files with exact paths. Never half a file.
5. Commands: Windows cmd first. Always run modules from the project root: python -m src.<package>.<module>
6. End every block with: VALIDATION CHECKLIST (exact commands and expected output), COMMON ERRORS & FIXES (top 3),
   WHAT YOU LEARNED (3 bullets), INVENTORY UPDATE. Then STOP and wait.
7. If I paste an error, debug it with me before continuing.
8. Keep it simple. NO libraries outside the agreed stack without asking. Prefer the standard library.
9. Keep folder structure and naming consistent.
10. Verify current library and model names (Gemini, LangChain, LangGraph change). You cannot browse live; when
    unsure, tell me exactly how to check.
11. NEVER truncate. Responses DO get cut off, observed at about 1,500-2,000 words including code. So: ONE file per
    response (about 110 lines of code at most, with SHORT prose around it); split big modules into TWO FILES by
    responsibility (pure builders + a DB runner) in two separate responses; announce "Part A / Part B" up front;
    put the big concept text in the first response and keep later responses short. Long non-code documents
    (like this prompt) are delivered in parts.
12. If a response is cut off and I say "continue": resume EXACTLY at the cut-off text. For code, say where to
    paste, name the broken last line to replace, and give its full replacement line first. If you cannot see
    where it was cut, resend the whole step compactly.
13. Never put secrets in code; use .env and keep .env.example in sync.
14. INSPECT BEFORE YOU LOAD: for any external data or format you have not seen, first give a read-only inspection
    script, then design the loader from the real output.
15. Prefer ONE TRANSACTION for loaders (all-or-nothing), verify against an independent source, make scripts
    re-runnable. Pattern for long jobs: (1) register the run and commit, (2) do all work in one transaction and
    mark 'completed', (3) on error roll back and mark 'failed' in a separate transaction. For LLM jobs: do all
    LLM calls in memory first, then write everything in one transaction (as src/metadata/generator.py does).
16. At the end of every block give an INVENTORY UPDATE (files, functions with signatures and purpose, outputs,
    gotchas) that I paste into this master prompt.
17. Before writing code that imports earlier code, use the names in the CODE INVENTORY (Parts 5-7). If a name is
    not listed or you are unsure, ask me to paste that file instead of guessing.
18. VERIFY INDEPENDENTLY: every stored number gets recomputed with a DIFFERENT formulation (SQL vs Python, or a
    different SQL). A mismatch can be a bug in the checker: investigate both sides (Block 8 example: a rank tie
    made two correct formulas disagree; the fix was a tie-safe definition).
19. Separate PURE functions (build SQL, parse results, scoring, Markdown, prompt context) from DB runners and LLM
    callers. Tests: no-DB tests plus tests marked `db` (and `llm` for real Gemini calls).
20. Do not reopen decided design. Ask only genuine pre-block questions (tiers, credentials, new libraries).
21. Update the README at milestones (final docs in Block 19). README file on disk is `Readme.md`.
22. OUTPUT STYLE (my request): show me code and commands, with minimal extra explanation. Do not waste tokens on
    information I do not need. The end-of-block sections stay, but short.
23. If I say "next" without pasting a requested output, assume it was as expected, but still list that output in the
    block's VALIDATION CHECKLIST so I can confirm it.

## PROJECT SUMMARY
TrustSQL lets business users ask questions in plain English and get: correct SQL + results + a plain-English
answer + data quality warnings. It is also a modular, extensible Text2SQL accelerator: a new LLM, database or
vector store plugs in through an interface instead of a rewrite.
Modules: A. DQCA Engine (transparent rebuild of BigQuery Dataplex Data Profiling + Auto Data Quality; every rule
shows the exact SQL it runs). B. Metadata Intelligence (auto metadata, Knowledge Graph, Ontology, human
reviewed). C. Agentic Text2SQL (LangGraph multi-agent, Gemini). D. API + Product (FastAPI + Streamlit).
Key idea: DQCA feeds Metadata, Metadata feeds the Agents; agents warn users when data has quality issues.

## DECISIONS ALREADY MADE (do not reopen unless I ask)
- ONE database engine: PostgreSQL 16 + pgvector (image pgvector/pgvector:pg16). No SQLite as primary DB, no
  Spider. (SQLite only as a later adapter proof in Block 18B.)
- Public benchmark = BIRD Mini-Dev, PostgreSQL version: 500 questions, 11 databases, simple 148 / moderate 250 /
  challenging 102, licence CC BY-SA 4.0 (record in docs/decisions.md, which does not exist yet).
- Two profiles on one codebase (config switch PROFILE): `olist` (showcase: Olist data + our DQ, KG, ontology,
  semantic cache + ~50-question golden set) and `bird` (public benchmark: each BIRD database is its own Postgres
  schema bird_<db_id>; executor sets search_path per question; DQ/ontology/cache toggleable).
- All meta.* and dq.* tables carry source_id ("olist", "bird:<db_id>").
- Approved additions: FastAPI + uvicorn + httpx. Rejected: asyncpg (use psycopg 3 async), Milvus (pgvector behind a
  VectorStore interface), Azure OpenAI/MySQL (interfaces only), Unstructured/PyMuPDF/PyPDF/GPT-4 Vision, OAuth2
  (simple bearer API key now, OAuth2 documented as future).
- Own execution-accuracy comparer first (official BIRD evaluator optional later). Free-tier awareness: run the BIRD
  eval on a ~100-question stratified sample first, cache LLM results, throttle with asyncio semaphores.
- Eval mode: the auto-LIMIT guardrail must be disabled (or very high) when comparing with gold results.
- BIRD master file = mini_dev_postgresql.json; SQLite JSON + DB files kept for Block 18B; MySQL not needed.
- Admin connection may use SET ROLE t2s_reader, BUT role-level statement_timeout only applies at login: with SET
  ROLE the code must set statement_timeout explicitly.
- BLOCK 6 (BigQuery + Dataplex parity) IS DEFERRED by my decision. Nothing depends on it. Affected items: the
  "DQ parity with Dataplex >= 95%" metric and the Dataplex comparison doc in Block 19; revisit at the end only if I
  ask. When revisited: ask GCP project id, billing/credits, region, auth method, and permission to add
  google-cloud-bigquery and sqlglot.
- DQ design (Blocks 3-4): profiles and scan results are DATED SNAPSHOTS (history kept, never overwritten; views
  dq.latest_profiles and dq.latest_results return the newest completed one). dq DDL (sql/02_dq_schema.sql,
  sql/03_dq_rules_schema.sql) is HAND-WRITTEN migration SQL applied by src/dq/init_schema.py. Only
  sql/01_domain_schemas.sql is generated (from config/domains.yaml). YAML is for data-shaped config (domains,
  profiler tunables, DQ rules, LLM limits), not for our own application tables.
- Rules: YAML (config/dq_rules/*.yaml) -> Pydantic -> compiled to visible SQL -> executed AS t2s_reader (never as
  admin) -> dq.results with counts, sql_used, failing_sql, sample_failures (max 10 rows). A rule whose SQL fails is
  stored with status='error' and the scan continues. Results are written only via the admin engine.
- Verdict semantics: row-level rules pass when pass % >= threshold (exact Decimal maths); ROW_CONDITION NULL result
  = fail; UNIQUENESS ignores null keys and fails every row of a duplicated key; RANGE/SET/REGEX nulls pass unless
  ignore_null: false; TABLE_CONDITION counts as 1 row; SQL_ASSERTION passes only with zero violating rows; an empty
  table passes row-level rules.
- Rules run ONLY when the runner is run (python -m src.dq.runner). Nothing is automatic. Rules never run per user
  question: the DQ Advisor (Block 14) reads stored verdicts from dq.latest_results.
- t2s_reader has NO access to raw, dq, meta, app until a later block grants it. setup_roles.py revokes these
  (HIDDEN_SCHEMAS) on every run; Block 14 must edit it to grant SELECT on the dq views (and the agents need a
  safe way to read meta: grant SELECT on specific meta views only, decided in Block 11/14).
- BLOCK 5 DECISIONS: (a) Scoring convention: rule score = pass_pct; dimension/table/overall score = plain average of
  rule scores (equal weight), rounded to 2 decimals; errored rules are listed, NOT scored; bands Good >= 99,
  Fair >= 95, else Poor; the report always shows exact 4-decimal pass rates for failing rules because a group can
  round to 100.00 while a rule fails. (b) DQ report format = Markdown only: reports/dq_report_<source>.md (":" in
  the source id becomes "_"); HTML only if I ask. (c) Rule recommender writes PROPOSALS to config/dq_suggestions/
  <source>.yaml; promotion = a human copies the accepted file into a rules folder. Suggested rules pass on today's
  data (they guard against decay); hand-written rules find defects. (d) BIRD rules live in config/dq_rules_bird/
  and run with the runner's --rules-dir; they must NOT go into config/dq_rules/ (test_block4 loads that folder).
  (e) Only california_schools is profiled so far; profile ALL 11 BIRD databases at the end of the project.
- BLOCK 7 DECISIONS: LLM access goes through a provider interface (src/adapters/llm/base.py LLMProvider) and a
  registry in src/common/llm.py (PROVIDERS dict); a new vendor = one file + one registry line. Agents call
  get_chat_model()/get_embeddings(), never a vendor. Always read model replies with response_text() (Gemini
  returns .content as a list of blocks). Only transient errors (429/5xx/timeouts) are retried, with exponential
  backoff + jitter (src/common/llm_guard.py); throttle default is off (0 s); optional config/llm.yaml.
- BLOCK 8 DECISIONS: (a) Metadata is NOT a dated snapshot: one current row per table/column in meta.tables and
  meta.columns with status draft|approved|rejected; the generator never overwrites approved rows. (b) Generation:
  all LLM calls first (in memory), then ONE write transaction; any failed table writes nothing and marks the run
  failed. (c) Final is_pii = LLM flag OR an unmistakable name (email, phone, fax, cpf, ssn, passport). (d) BIRD
  human descriptions for all 11 databases live in meta.reference_descriptions (source_id bird:<db_id>). (e)
  Description quality is scored by embedding cosine PLUS rank-within-table (top-1, top-3, MRR) against a random
  baseline, because raw cosine saturates inside one topic (control 0.81). (f) Human review UI/CLI for drafts is not
  built yet (belongs to the Block 10 review step or a small CLI).
- BLOCK 9 DECISIONS: (a) Graph topology persists in meta.kg_nodes and meta.kg_edges with deterministic IDs (source_id:node_type:parts and source_id:edge_type:src->tgt). (b) Olist joins are inferred via column naming heuristics and distinct value overlap >= 75%. (c) BIRD benchmark joins use ground-truth foreign keys from dev_tables.json via bird_fk.py. (d) Multi-hop join path finding uses NetworkX Dijkstra on joins_with edges weighted by overlap (weight = 2.0 - overlap_pct/100.0). (e) Graph loading is an atomic replacement per source_id.
- BLOCK 10 DECISIONS: (a) Business Ontology concepts and metrics live in config/ontology/<source>.yaml and meta.ontology_terms with lifecycle status draft|approved|rejected. (b) Child terms in YAML inherit root source_id via a Pydantic pre-validator. (c) Approved ontology terms sync into meta.kg_nodes (metric or business_term) and wire to base tables via measures edges in meta.kg_edges. (d) BIRD evidence in mini_dev_postgresql.json serves as dynamic runtime ontology during benchmark evaluation; manual YAML is only maintained for pilot databases (california_schools).
- BLOCK 11 DECISIONS: (a) Vector operations sit behind an abstract VectorStore interface in src/adapters/vectordb/base.py with a PostgresVectorStore adapter in src/adapters/vectordb/pgvector.py. (b) Gemini 3072-dim embeddings are sliced to the first 768 dimensions and L2-normalized (truncate_and_normalize) using Matryoshka Representation Learning (MRL) to stay within pgvector's 2,000-dim HNSW index ceiling. (c) Vectors persist in meta.schema_embeddings with an HNSW cosine index (vector_cosine_ops). (d) Semantic indexing unifies tables, columns, and approved ontology terms in one searchable vector space.

- BLOCK 12 DECISIONS: (a) sqlglot AST verification enforces SELECT-only at parse tree level and blocks data-modifying CTEs
  ("WITH d AS (DELETE ...)"). (b) Auto-LIMIT guardrail is injected when missing, but strictly disabled (default_limit=None)
  in evaluation mode to prevent false row-count mismatches against gold queries. (c) Independent execution comparer
  (src/eval/comparer.py) handles float/Decimal rounding (1e-3), string trimming/case-insensitivity, and order-insensitive
  multiset comparison unless ORDER BY is present. (d) Defense-in-depth: system prompt rules cause Gemini to neutralize malicious
  prompts into harmless refusal message literals (e.g. SELECT '...not allowed...' AS message with tables_used=[]).
- BLOCK 12B DECISIONS: (a) Stratified sampling (src/eval/bird_sampler.py) deterministically selects 100 questions from
  mini_dev_postgresql.json preserving db_id and difficulty distribution (simple 30, moderate 50, challenging 20; seed=42)
  persisted in data/bird/mini_dev_sample_100.json. (b) Gemini Free Tier ~15 RPM limit handled via persistent disk cache
  (data/bird/bird_eval_cache.json) and a 4.2s minimum interval FreeTierThrottler. (c) Dynamic schema switching per question
  uses search_path = bird_<db_id>. (d) Zero-shot baseline on BIRD fails primarily due to missing window functions (RANK() OVER)
  and hallucinated columns (e.g. sname).
- BLOCK 13 DECISIONS: (a) Multi-agent architecture orchestrated via LangGraph StateGraph(AgentState) with 24 typed keys.
  (b) Structured SQL generation uses model.with_structured_output(SqlGenerationOutput). (c) Validator node enforces AST
  SELECT-only safety and blocks internal schema access (raw, dq, meta, app). (d) Self-healing loop: Postgres runtime exceptions
  and AST failures route to sql_corrector_node to repair SQL with a hard ceiling of max_retries=3.
- BLOCK 14 DECISIONS: (a) t2s_reader granted USAGE on dq and SELECT on dq.latest_results and dq.latest_profiles views only (underlying tables remain hidden; Postgres view ownership chaining applies). (b) Query Rewriter incorporates a fast-path: if chat_history is empty, returns original query without an LLM invocation. (c) Clarifier is conservative: flags ambiguity only when essential business constraints are completely absent without a standard default. (d) Ontology Resolver identifies business metrics/terms from YAML/meta and injects approved SQL formulas into state['resolved_terms']. (e) DQ Advisor is dimension-driven: dynamically maps technical scan metrics into executive advisories by dimension (Timeliness, Completeness, Integrity, Validity, Consistency) without hardcoding rule IDs. (f) Specialist agent tracks (dq_question, metadata_question, out_of_scope) provide dedicated responses, bypassing SQL generation entirely. (g) backward-compatibility alias build_core_graph = build_agentic_graph preserved in graph.py.
- BLOCK 15/16 DECISIONS: (a) Semantic Cache uses pgvector HNSW index in a new hidden `app` schema. (b) Cache hits are strictly verified by an LLM to prevent parameter mismatch (e.g., 2022 vs 2023). (c) Cross-Domain routing uses Vector Search (Schema Linker) to find tables, and NetworkX (Domain Selector) to inject deterministic JOIN paths, bypassing LLM join hallucinations.
- BLOCK 17 DECISIONS: (a) Evaluation comparer ignores column aliases by comparing values positionally. (b) Agentic evaluation disables the auto-LIMIT guardrail via an `eval_mode` flag in AgentState. (c) Router explicitly classifies "distinct values" and "statuses" as `data_question` to prevent misrouting to the metadata specialist.
- BLOCK 17B DECISIONS: (a) FastAPI serves as the bridge between the LangGraph engine and the frontend. (b) Security is handled via a simple HTTP Bearer token (`TRUSTSQL_API_KEY`). (c) Positive feedback via the `/feedback` endpoint automatically writes the query to the Semantic Cache.


## ACCELERATOR REQUIREMENTS (existing company Text2SQL accelerator)
Objective: modular, scalable Text2SQL across multiple LLMs, databases and vector databases, presenting tables and
graphs to non-technical users. Success metrics: SQL Accuracy % = correct/total generated x 100; Visualization
Relevance % = share of cases where the table/chart matches the intent (verified by users); Module Extensibility =
minutes to integrate a new LLM, DB or vector DB.
Mapping: llmfactory/llmbase/gemini.py -> src/common/llm.py + src/adapters/llm/ (DONE in Block 7);
dbBase/connection/executer -> src/adapters/db/ + Executor agent; vectordbBase/vectorstoreFactory ->
src/adapters/vectordb/ (DONE in Block 11); env_variables.py -> config/settings.py + .env; Schema.py/view.py/FastAPI -> src/api/;
prompts/ -> prompts/ (one file per agent; prompts/metadata.txt and prompts/baseline.txt exist);

feedback loop/context awareness/error
handling/query templates -> Cache Writer (thumbs), Query Rewriter, Error Corrector, few-shot examples from the
validated cache.
## TECH STACK (keep to this)
- VS Code; Python 3.11+ (venv + pip, requirements.txt); Docker Desktop with PostgreSQL 16 + pgvector.
- DB: SQLAlchemy 2.0 + psycopg 3 (sync and async), pandas.
- LLM: Google Gemini via langchain-google-genai (chat model gemini-3.5-flash-lite; embedding model
  gemini-embedding-001, 3072 dims; I choose models). src/common/list_models.py lists available models.
- LangChain (prompts, structured output, tools) + LangGraph (state, routing, loops, interrupt, checkpointer).
- Vectors: pgvector behind a VectorStore interface in meta.schema_embeddings using 768-dim Matryoshka normalized
  embeddings with an HNSW cosine distance index (DONE in Block 11).
- sqlglot (>=25.0.0; AST safety/parsing/guardrails), langgraph (>=0.2.0; stateful multi-agent graphs), NetworkX (>=3.4),
  pydantic, pydantic-settings, PyYAML, python-dotenv, pytest.
- GCP: BigQuery (google-cloud-bigquery) + Dataplex DQ/Profiling scans: DEFERRED (Block 6).
- API: FastAPI + uvicorn (+ httpx). UI: Streamlit (+ Plotly) calling the API. Tracing optional: LangSmith.
- Currently in requirements.txt: sqlalchemy, psycopg[binary], pandas, pydantic, pydantic-settings, python-dotenv, PyYAML, langchain-core, langchain-google-genai, pytest, kaggle, ipykernel, networkx, sqlglot, langgraph, fastapi, uvicorn.

## DATA AND POSTGRES SCHEMAS
Olist Brazilian E-Commerce (9 CSVs) and Olist Marketing Funnel (2 CSVs) via the Kaggle API; BIRD Mini-Dev (PG).
- raw (11 untouched TEXT tables) -> sales (orders 99,441; order_items 112,650; order_payments 103,886), customer
  (customers 99,441; geolocation 1,000,163; order_reviews 99,224), catalog (products 32,951; sellers 3,095;
  category_translation 71), marketing (qualified_leads 8,000; closed_deals 842).
- bird_<db_id>: 11 schemas, 75 tables, 3,898,114 rows (california_schools, card_games, codebase_community,
  debit_card_specializing, european_football_2, financial, formula_1, student_club, superhero,
  thrombosis_prediction, toxicology). california_schools: frpm 9,986 rows/29 cols, satscores 2,269/11, schools
  17,686/49 (89 columns).
- dq: profile_runs, profile_tables, profiles, latest_profiles (view); rules, scan_runs, results, latest_results
  (view). Holds Olist profile + scan AND the bird:california_schools profile + scan.
- meta (EXISTS, ALL 4 LAYERS COMPLETE): generation_runs, tables, columns, reference_descriptions,
  description_scores, kg_nodes, kg_edges, ontology_terms, schema_embeddings. Holds Olist metadata drafts,
  bird:california_schools metadata drafts, BIRD human descriptions for all 11 databases, description score run,
  KG nodes/edges (Olist: 133 nodes / 157 edges; BIRD: 190 nodes / 193 edges), approved ontology terms (Olist: 7;
  BIRD: 5), and 768-dim vector embeddings (Olist: 88; BIRD: 97). app (semantic cache/query history/feedback):
  NOT created yet. public holds no tables.
- Roles: trustsql_admin (setup, loading, DQ/metadata writes) and t2s_reader (READ-ONLY; statement_timeout=30s,
  idle_in_transaction_session_timeout=60s, default_transaction_read_only=on; no access to raw/dq/meta/app).

## MODULE A: DQCA ENGINE (Dataplex-style, transparent)
DONE: Profiler (Block 3); Rule engine (Block 4: 8 rule types, 41 Olist rules in 5 YAML files, 35 pass / 6 fail /
0 error); Block 5: rule recommender (profile -> suggested rules), scoring by dimension/table/overall, Markdown DQ
report with exact SQL per failing rule, BIRD california_schools profiled + 92 suggested rules promoted and passing.
Rule types: NON_NULL, UNIQUENESS, RANGE, SET, REGEX, ROW_CONDITION, TABLE_CONDITION, SQL_ASSERTION; dimensions
Completeness, Uniqueness, Validity, Consistency, Timeliness, Accuracy; threshold = minimum % of rows that pass.
DEFERRED: Block 6 BigQuery/Dataplex parity. TODO later: natural-language rule creation with Gemini. No Accuracy
rules exist yet. The 93 Olist suggestions in config/dq_suggestions/olist.yaml are NOT promoted (optional).

## MODULE B: METADATA INTELLIGENCE (ALL 4 LAYERS COMPLETE)
Layer 1 Metadata: DONE (Block 8). information_schema + DQ profile + sample values go to Gemini, which writes
table/column descriptions, synonyms, column role and PII flag into meta with status draft/approved; scored
against BIRD's human column descriptions (embedding cosine + rank-within-table).
Layer 2 Knowledge Graph: DONE (Block 9). Nodes (domain, table, column, dq_rule, business_term, metric), edges
(contains, has_column, joins_with, has_dq_rule, measures). Olist joins INFERRED (column naming heuristics +
value overlap >= 75%); BIRD joins extracted from dev_tables.json (bird_fk.py). Shortest join path via NetworkX
Dijkstra with overlap-weighted edges; persisted in meta.kg_nodes and meta.kg_edges. Resolves 3-hop joins in Olist
(customers -> orders -> order_items -> products) and 2-hop joins in BIRD (satscores -> schools -> frpm).
Layer 3 Ontology: DONE (Block 10). Business concepts and metrics (Gross Revenue, Delivery Delay Days, Total SAT
Score, Charter School, etc.) defined in config/ontology/*.yaml and persisted in meta.ontology_terms with exact SQL
expressions and base tables; synced to KG as 'metric' and 'business_term' nodes wired via 'measures' edges.
Layer 4 Vector Search: DONE (Block 11). Tables, columns, and approved ontology terms embedded via Gemini, downsampled
to 768 dimensions using Matryoshka Representation Learning (MRL) and L2-normalized (truncate_and_normalize), and
stored in meta.schema_embeddings behind an abstract VectorStore interface (PostgresVectorStore) with an HNSW cosine
index. Retrieved via SchemaRetriever.

## MODULE C: AGENTIC TEXT2SQL (LangGraph)
Two pipelines (config switch): Baseline (simple LangChain chain: schema -> Gemini -> SQL -> execute -> answer) and
Agentic (StateGraph). Nodes: 1 Router (data_question, dq_question, metadata_question, out_of_scope; the output
shape Route(intent, confidence) was prototyped in src/common/llm_structured.py); 2 Query Rewriter; 3 Clarifier
(LangGraph interrupt); 4 Semantic Cache Lookup (LLM checks parameters match); 5 Ontology Resolver; 6 Schema
Linker (vector retrieval + KG expansion); 7 Domain Selector/Cross-Domain (KG join path); 8 SQL Generator
(structured output: SQL + reasoning + tables used; prototyped as SqlAnswer); 9 SQL Validator (sqlglot parse,
SELECT-only, known tables/columns, LIMIT); 10 Executor (t2s_reader, timeout, search_path for bird_<db_id>); 11
Error Corrector (max 3 retries, then a graceful message); 12 DQ Advisor (reads dq.latest_results /
latest_profiles for the tables and columns used and attaches warnings, for example "product_category_name is 1.8%
null; results may undercount"); 13 Answer Synthesizer (answer + SQL logic + chart suggestion); 14 Cache Writer
(only after successful execution AND a thumbs up). Special paths: dq_question -> DQ Agent (dq schema),
metadata_question -> Metadata Agent (meta/ontology), out_of_scope -> polite refusal.
Graph State keys: question, rewritten_question, chat_history, intent, cache_hit, resolved_terms, selected_domains,
selected_tables, selected_columns, join_path, generated_sql, validation_errors, execution_result, error_message,
retry_count, dq_warnings, final_answer, needs_clarification, clarification_question, source_id, evidence
(optional, BIRD), chart_suggestion.
Flow: Router -> Rewriter -> Clarifier -> Cache Lookup -> HIT: Executor -> DQ Advisor -> Answer; MISS: Ontology
Resolver -> Schema Linker -> Domain Selector -> SQL Generator -> SQL Validator -> Executor -> (error? Error
Corrector -> SQL Generator, max 3) -> DQ Advisor -> Answer Synthesizer -> (feedback) -> Cache Writer.

## MODULE D: API + PRODUCT
FastAPI (async): /query, /feedback, /dq, /metadata, /health; Pydantic schemas; simple bearer API key. Streamlit
pages (Chat, DQ Dashboard, Metadata & KG, Ontology Review, Evaluation) call the API. The DQ Dashboard can reuse
src/dq/scoring.py and report_md.py.

## GUARDRAILS (must exist)
SELECT only (sqlglot AST check; block INSERT/UPDATE/DELETE/DROP/ALTER; also data-modifying CTEs). Execute only as
read-only t2s_reader with a timeout. Auto-add LIMIT if missing (disabled in eval mode). Only known schemas/tables
(no dq/app/meta from data questions unless the intent is dq_question/metadata_question). Mask PII-flagged columns
in answers (meta.columns.is_pii is now available for this). Secrets only in .env. Proven so far: t2s_reader cannot
write and cannot read dq or meta; a rule SQL containing WITH ... DELETE passes the rule validator but is blocked
by the role (test exists).

## EVALUATION
Olist golden set (~50 YAML questions: easy/medium/hard, single/cross-domain, follow-ups, ambiguous, malicious) with
expected SQL; BIRD Mini-Dev ~100 stratified questions first, then more (execution accuracy by difficulty, evidence
on/off). Metrics: SQL Accuracy %, Visualization Relevance %, Module Extensibility (minutes), valid SQL rate,
average latency, cache hit rate, retry count, guardrail block rate, metadata quality (similarity to BIRD
descriptions: measured in Block 8), DQ parity with Dataplex (rule-by-rule match %: deferred with Block 6).
Baseline vs Agentic report with ablations (schema linking, ontology, retries, cache).

## FOLDER STRUCTURE (actual state after Block 11; project root dqca-demo)
```
.env, .env.example, .gitignore, requirements.txt, docker-compose.yml, pytest.ini, Readme.md,
trustsql_conn.session.sql, .vscode/settings.json
config/      __init__, settings.py, domains.yaml, profiler.yaml, golden_olist.yaml (50 questions),
             llm.yaml (OPTIONAL),
             dq_rules/ (41 Olist rules), dq_rules_bird/ (92 promoted rules), dq_suggestions/ (93 Olist, 92 BIRD),
             ontology/ olist.yaml (7 approved terms), bird_california_schools.yaml (5 approved terms)
data/        raw/ (Olist CSVs), bird/ (BIRD files, mini_dev_sample_100.json, bird_eval_cache.json)
prompts/     metadata.txt (variable {source_note}; Block 8), baseline.txt (Block 12)
reports/     dq_report_olist.md, dq_report_bird_california_schools.md [GENERATED by src.dq.report],
             bird_desc_inspect.txt [Block 8 inspection output]
sql/         00_init_extensions.sql, 01_domain_schemas.sql (GENERATED), 02_dq_schema.sql, 03_dq_rules_schema.sql,
             04_meta_schema.sql, 05_kg_schema.sql, 06_ontology_schema.sql, 07_embeddings_schema.sql
src/common/  db.py, logging.py, llm.py (factory), llm_guard.py (retry/throttle), llm_basics.py, llm_structured.py,
             list_models.py, check_env.py
src/adapters/ db/ (base.py, postgres.py), llm/ (base.py, gemini.py), vectordb/ (base.py, pgvector.py)
src/ingestion/ download, load_raw, build_domains, setup_roles, bird_inspect, bird_fetch, bird_dump_scan,
             bird_loader, bird_gold_check
src/dq/      profiler_sql, profiler, profile_verify, profile_inspect, init_schema, rules_models, rule_compiler,
             runner, rule_verify, recommender, recommend_run, scoring, score_run, report_md, report
src/metadata/ context.py, models.py, llm_generate.py, generator.py, meta_check.py, bird_desc_inspect.py,
             ref_loader.py, desc_score.py, desc_rank.py,
             kg_models.py, kg_infer.py, kg_builder.py, kg_loader.py, kg_graph.py, bird_fk.py,
             ontology_models.py, ontology_loader.py, ontology_kg_sync.py,
             indexer_prep.py, indexer.py, retriever.py
src/text2sql/ baseline/ (validator.py, schema_context.py, chain.py),
             agents/ (state.py, generator.py, validator_node.py, executor.py, corrector.py, graph.py,
                      router.py, rewriter.py, clarifier.py, ontology_resolver.py, dq_advisor.py, specialists.py)
src/eval/    comparer.py, runner.py, bird_sampler.py, bird_cache.py, bird_runner.py
tests/       test_block0.py, test_block1.py, test_block2.py, test_block2b.py, test_block3.py (17),
             test_block4.py (22), test_block5.py (20), test_block7.py (15), test_block8.py (16),
             test_block9.py (8), test_block10.py (8), test_block11.py (5),
             test_block12.py (11), test_block12b.py (5), test_block13.py (8), test_block14.py (9)       [suite = 193 passed]
src/app/     __init__.py, init_schema.py, cache.py
src/api/     __init__.py, models.py, security.py, main.py, test_client.py
NOT created yet: notebooks/, docs/ (docs/decisions.md must record the BIRD licence)
```
Every folder under src/ and config/ has an __init__.py. Run modules from the project root.

## BUILD PLAN: 24 BLOCKS (one block per response chain)
PHASE 1 FOUNDATION: Block 0 environment DONE; Block 1 Olist download + raw DONE; Block 2 domain schemas,
t2s_reader, DBConnector DONE; Block 2B BIRD Mini-Dev setup DONE.
PHASE 2 DQCA ENGINE: Block 3 Profiler DONE; Block 4 Rule engine DONE; Block 5 Rule recommender + scoring + DQ
report + profile one BIRD DB DONE; Block 6 BigQuery + Dataplex parity: DEFERRED (my decision).
PHASE 3 METADATA: Block 7 LLM provider interface/factory DONE; Block 8 metadata generation + score vs BIRD DONE;
Block 9 Knowledge Graph (inferred joins, NetworkX, persisted graph) DONE; Block 10 Business Ontology (YAML + meta,
KG measures wiring) DONE; Block 11 Vector Store (pgvector, 768-dim Matryoshka embeddings, SchemaRetriever) DONE.
PHASE 4 TEXT2SQL: Block 12 baseline chain + Olist golden set DONE; 12B BIRD eval harness DONE; 13 LangGraph fundamentals
+ core graph with self-healing retry loop DONE; Block 14 Rewriter, Clarifier, Ontology Resolver, DQ Advisor, DQ + Metadata
specialist paths DONE; 15 semantic cache NEXT; 16 cross-domain (Domain Selector + KG join paths); 17 full evaluation Baseline
vs Agentic with ablations.

PHASE 5 PRODUCT: 17B FastAPI backend; 18 Streamlit; 18B extensibility proof (second vector backend, second LLM
provider, or SQLite adapter on BIRD SQLite files; record the minutes; a fake LLM provider already plugs in via
one class + one registry line in tests/test_block7.py); 19 documentation (README final, diagrams, decisions, demo
script; Dataplex comparison only if Block 6 gets built). TODO.
END OF PROJECT TASK: profile all 11 BIRD databases (python -m src.dq.profiler --source bird:<db_id>) and then
generate metadata for them (python -m src.metadata.generator --source bird:<db_id>).

## DEFINITION OF DONE (whole project)
`docker compose up` starts Postgres; one command starts the API and one starts Streamlit. The DQ engine runs and
shows the SQL for every rule (Dataplex parity >= 95% only if Block 6 is built). Metadata, KG and Ontology are
generated, reviewable and used by the agents. Agentic beats Baseline on the Olist golden set AND the BIRD sample,
shown in a report. Guardrails block all destructive SQL. SQL Accuracy %, Visualization Relevance % and Module
Extensibility are reported. Clear docs and a demo flow for my manager.

## CUMULATIVE GOTCHAS (carry into later blocks)
- LangGraph silently drops state keys that are not explicitly defined in the `TypedDict` (e.g., `eval_mode`). Always update `AgentState` when adding new keys.
- SQLAlchemy `res.mappings()` must be used to return dictionaries; raw `res` returns tuples which breaks dictionary-based comparers.
- Python's `:.2f` rounds up (e.g., 99.998 -> 100.00). Use `math.floor(val * 100) / 100.0` to truncate when displaying high-precision DQ failures to avoid logical contradictions.
- Gemini Free Tier will throw `503 UNAVAILABLE` on heavier models (like Pro) during bulk evaluations. Stick to `gemini-3.5-flash-lite` or `gemini-1.5-flash-8b` for batch processing.
- Postgres: `ORDER BY name` resolves to an OUTPUT column first; alias computed columns (AS _x) when sorting by the
  original column. `n_live_tup` is unreliable after a container restart; use count(*).
- Avoid LIKE with % or backslashes inside SQLAlchemy text(); use left(x, n) = '...' or starts_with(x, '...').
- SQLAlchemy text(): `:word` is a bind parameter and `%` is escaped. For generated SQL without parameters use
  src.dq.profiler.run_generated (escapes ':'). Proven on BIRD columns like "Percent (%) Eligible Free (K-12)".
- psycopg 3 allows several statements in one execute() only when there are no parameters (used by init_schema,
  setup_roles and src/metadata/init_schema.py through conn.connection.driver_connection).
- psycopg 3 adapts a Python list to a Postgres text[] parameter (used for meta synonyms).
- setup_roles.py must be re-run after every build_domains run (schema rebuild drops grants) and revokes
  dq/meta/app/raw from t2s_reader on every run. BIRD grants come from bird_loader.grant_reader.
- Sync of dq.rules never deletes rules removed from YAML (stale rows stay; delete by hand).
- A data-modifying CTE ("WITH d AS (DELETE ...)") passes the rule validator but the read-only role blocks it;
  Block 12-13 SQL Validator must also reject it at AST level (sqlglot).
- YAML 1.1 traps: unquoted NO/ON/Y become booleans; quote expressions containing ": ". yaml.safe_dump quotes
  these automatically. Rule YAML layout is `source_id: <id>` then `rules:` (list).
- Timestamps in dq.* and meta.* are timestamptz: logs print local time (IST), some queries print UTC.
- UNIQUENESS and window functions scan the whole table; very large BIRD tables may need runner --timeout 300.
- Group scores are rounded averages: a group can show 100.00 while a rule fails. Read exact pass_pct.
- recommend_run checks duplicates only against config/dq_rules/ (not dq_rules_bird/); re-running it for BIRD
  proposes promoted rules again (cleanup item).
- Suggested rules pass on current data by construction; they do not find today's defects.
- dq.profiles.top_values is jsonb (psycopg returns a list); only profiled categories with top_n=10 values.
- cmd (not PowerShell) is the shell: use `type`, `more`, `copy`, `findstr`. In cmd, < and > inside an echo'd
  string are redirections.
- LLM (Block 7): Gemini returns AIMessage.content as a LIST of blocks: always use response_text(). Literal braces
  in prompt templates must be doubled ({{ }}); braces inside variable VALUES are fine. with_structured_output
  returns a Pydantic instance and can return None on parse failure (handle it). Do not rely on Field length
  limits in schemas sent to Gemini; validate in our own code. llm_guard retries only transient errors and only
  sync .invoke (async version later if needed).
- Embeddings (Block 8/11): free tier returned 429 on batches of 50; call_resilient recovers. gemini-embedding-001
  gives 3072 dims, above pgvector's 2000-dim index limit: solved in Block 11 by slicing to 768 dimensions and
  re-normalizing with L2 norm (truncate_and_normalize) using Matryoshka Representation Learning (MRL).
- Metadata scoring (Block 8): raw cosine saturates (wrong-column control mean 0.81 vs 0.88 true), use rank-within-
  table; identical reference texts give tied similarity, so use competition ranking (best rank for ties). BIRD
  reference text is often a bare label or misaligned (for example frpm "County Name" described as "County Code").
- BIRD description CSVs: file name case differs from the table, decode utf-8-sig then cp1252 then latin-1 (bullet
  characters), match names case-insensitively, descriptions may be empty (145 of 798 columns), value_description
  exists for only 278.
- Block 9: BIRD has real FK constraints in Postgres (87 FK, 68 PK in the dump) and dev_tables.json has 102 FK / 72
  PK entries: reconcile, dev_tables.json is the truth.
- Block 9: NetworkX 3.4+ is strictly required for Python 3.13 support.
- Block 10: In YAML-driven ontology models, root-level source_id must be propagated to nested child terms before
  validation using a Pydantic @model_validator(mode="before").
- Block 10: Column names with spaces/symbols in ontology SQL expressions (e.g. BIRD "Percent (%) Eligible Free (K-12)")
  must be enclosed in double quotes inside SQL string expressions.
- Block 9-11: Atomic synchronization pattern: scripts that replace KG nodes/edges, ontology terms, or vector embeddings
  must delete prior records for that source_id within the exact same transaction before inserting new records.
- Block 12B/17: gold_run.json has no full results, so recompute gold results at eval time with our own comparer
  (order-insensitive unless ORDER BY, numeric tolerance, NULLs). Flag question_ids 563 and 565 (gold returns 0
  rows). Eval mode: no auto-LIMIT. Gold SQL is PostgreSQL-flavoured.
- Block 13: ALWAYS present identifiers to the LLM already double-quoted (california_schools has 27 names with
  spaces/capitals, thrombosis_prediction 10; financial has a table named "order"); src/metadata/context.py
  already does this. Executor sets search_path to bird_<db_id> per question and an explicit statement_timeout when
  using SET ROLE.
- Block 14: edit setup_roles.py to grant t2s_reader SELECT on dq.latest_results and dq.latest_profiles only;
  decide how agents read meta (views, never raw tables with draft rows if only approved should be used).
- Block 18B: BIRD SQLite files and mini_dev_sqlite.json are ready for the SQLite adapter proof.



# CODE INVENTORY (Blocks 0-11). Use these names; if a name is missing or unsure, ask me to paste the file.

## A. Blocks 0-2 (files REVIEWED: names are exact)

### config/settings.py
- Constants: PROJECT_ROOT (Path), ENV_FILE (PROJECT_ROOT/.env).
- class Settings(BaseSettings) (pydantic-settings, env_file=.env, extra="ignore"). Fields: postgres_host
  ("localhost"), postgres_port (5433), postgres_db ("trustsql"), postgres_sslmode ("prefer"), postgres_admin_user
  ("trustsql_admin"), postgres_admin_password (SecretStr), t2s_reader_password (SecretStr), google_api_key
  (SecretStr), gemini_chat_model ("gemini-3.5-flash-lite"), gemini_embedding_model ("gemini-embedding-001"),
  profile (Literal["olist","bird"]), llm_provider ("gemini"), db_backend ("postgres"), vector_backend ("pgvector").
- Properties: admin_db_url, reader_db_url (SQLAlchemy URL, driver postgresql+psycopg); method _build_url(user,
  password). get_settings() -> Settings (lru_cache). No setting exists for statement timeout or DQ.

### src/common/db.py
- get_admin_engine() -> Engine (cached; ONLY for setup, loading, DQ/metadata writes).
- get_reader_engine() -> Engine (cached; role t2s_reader; the only engine agents/rule SQL use).
- ping() -> bool. get_connector(read_only=True) -> DBConnector (factory on settings.db_backend; lazy import).

### src/common/logging.py
- get_logger(name) -> logging.Logger (stdout, INFO, one handler, propagate False).

### src/adapters/db/base.py
- QueryResult(sql, columns, rows, truncated, elapsed_ms) dataclass; .row_count; .to_dataframe().
- ColumnInfo(schema, table, column, data_type, is_nullable) frozen dataclass.
- DBConnector (ABC, attr dialect): run_query(sql, params=None, *, search_path=None, max_rows=None) -> QueryResult;
  list_columns(schemas) -> list[ColumnInfo]; close(); list_tables(schemas) -> list[(schema, table)].

### src/adapters/db/postgres.py
- PostgresConnector(engine), dialect "postgres". run_query uses SET LOCAL search_path (schema names checked by
  regex), never commits (connection closes = rollback), uses fetchmany(max_rows+1) to set truncated. It does NOT
  set statement_timeout itself. list_columns reads information_schema.columns (only what the role may see).

### src/ingestion/build_domains.py (python -m src.ingestion.build_domains)
- Constants DOMAINS_FILE (config/domains.yaml), SCRIPT_FILE (sql/01_domain_schemas.sql), IDENT, INT_TYPES.
- Models TableSpec(source, primary_key, columns), DomainSpec(description, tables), DomainsConfig(domains).
- load_domains() -> dict[str, DomainSpec]; select_expr(col, col_type); build_statements(domains) -> list[str];
  check_raw_columns(conn, domains) -> (problems, warnings); main() -> int. Drops and rebuilds the domain schemas in
  one transaction, writes the generated SQL file, compares row counts with raw.

### src/ingestion/setup_roles.py (python -m src.ingestion.setup_roles)
- Constants ROLE="t2s_reader", STATEMENT_TIMEOUT="30s", HIDDEN_SCHEMAS=["raw","dq","meta","app"]; main() -> int.
- Creates/updates the role (statement_timeout, idle_in_transaction_session_timeout=60s,
  default_transaction_read_only=on), GRANT CONNECT, revokes HIDDEN_SCHEMAS, grants USAGE + SELECT + default
  privileges on the schemas of domains.yaml only. RE-RUN after every build_domains.

### Block 0-2 files that exist but were NOT reviewed (ask me before importing from them)
src/ingestion/download.py, load_raw.py; src/common/check_env.py; docker-compose.yml; sql/00_init_extensions.sql;
tests/test_block0.py (includes test_gemini_replies, marker llm), test_block1.py, test_block2.py;
trustsql_conn.session.sql; .vscode/settings.json.
(src/common/llm.py and list_models.py WERE reviewed in Block 7; llm.py was rewritten, see Part 7.)
pytest.ini: pythonpath=., testpaths=tests, markers db (needs Postgres) and llm (real Gemini calls), plus a
filterwarnings entry ignoring the "fixed sampling defaults" warning.

## B. Block 2B: BIRD Mini-Dev (DONE)
Result: 11 schemas bird_<db_id>, 75 tables, 3,898,114 rows, loaded in one transaction (123 s); row counts equal
across dump, SQLite and Postgres; public has 0 tables; t2s_reader has USAGE + SELECT + default privileges on all
bird_* schemas. Gold run (500 PG gold queries as t2s_reader, no LIMIT): 498 ok, 2 empty (question_ids 563 and 565,
codebase_community, moderate), 0 errors, 19 s. Write tests (INSERT, DELETE, CREATE TABLE, DROP TABLE) blocked.
Tests: tests/test_block2b.py (11 schemas, 75 tables, public clean, superhero.superhero = 750 rows,
bird_financial."trans" = 1,056,320 rows).
Schemas (tables/rows): california_schools 3/29,941; card_games 6/803,445; codebase_community 8/740,646;
debit_card_specializing 5/423,050; european_football_2 7/222,796; financial 8/1,079,680; formula_1 13/493,257;
student_club 8/42,511; superhero 10/10,614; thrombosis_prediction 3/15,252; toxicology 4/36,922.
Data layout (git-ignored, under data/bird/): extracted/minidev/MINIDEV/mini_dev_postgresql.json (MASTER, 500 rows:
question_id, db_id, question, evidence, SQL, difficulty); mini_dev_postgresql_gold.sql (SQL<TAB>db_id);
mini_dev_sqlite.json + gold; dev_tables.json (per db: db_id, table_names_original, column_names_original,
column_types, primary_keys, foreign_keys; 72 PK / 102 FK entries = truth for Block 9; find it with
BIRD.rglob("dev_tables.json")); dev_databases/<db_id>/<db_id>.sqlite and database_description/<table>.csv (75 CSVs:
original_column_name, column_name, column_description, data_format, value_description); MINIDEV_postgresql/
BIRD_dev.sql (955 MB dump, keep for --reload); pg_dump_structure.sql; table_db_map.json ({schema, table, db_id,
columns, dump_rows, sqlite_rows, status}); gold_run.json (per question: question_id, db_id, difficulty, sql,
status ok/empty/error, n_rows, n_cols, seconds, preview, error, run_as; no full result sets); gold_failures.csv.
Scripts (src/ingestion/, python -m src.ingestion.<name>):
- bird_inspect.py (one-off, needs datasets which is no longer installed): main(), show_repo_files(),
  show_questions(), human(n).
- bird_fetch.py [--url] [--force] [--no-extract]: download, summarize_zip, extract, show_tree, show_sqlite,
  show_descriptions, show_sql_files, show_json, human, rel, header, main; constants DEFAULT_URL
  (https://bird-bench.oss-cn-beijing.aliyuncs.com/minidev.zip), BIRD_DIR, DOWNLOAD_DIR, ZIP_PATH, EXTRACT_DIR.
- bird_dump_scan.py (read-only, ~2 min): scan_dump() -> (tables, kinds, owners); sqlite_counts(db_id) ->
  {lower_table: rows}; needs_quotes(name); unq(tok); main(). Writes pg_dump_structure.sql, table_db_map.json.
- bird_loader.py [--reload]: qi(name); schema_of(db_id) -> "bird_<db_id>"; get_admin_engine() lookup (STOPGAP:
  replace with src.common.db.get_admin_engine); should_skip(stmt); preflight(cur, schemas, reload);
  restore_dump(cur) -> {table: rows}; move_tables(cur, mapping); grant_reader(cur, schemas); verify(cur, mapping);
  main(). One transaction; ANALYZE after commit.
- bird_gold_check.py [--timeout 120] [--limit N]: write_tests(conn) -> bool; run_one(cur, sql) -> dict(status,
  n_rows, n_cols, seconds, preview, error); main() connects as admin, SET ROLE t2s_reader, explicit
  statement_timeout, search_path per question, retries errors as admin to classify, DISCARD ALL at the end.

## C. Block 3: Profiler (DONE; 17 tests)
Run 5970a6c2-73f8-4223-8180-2b904ee90b0f: source olist, 11 tables, 70 columns (geolocation 9 s). Independent
verifier: 370 checks, 0 mismatches. Types seen in Olist and BIRD: only text, numeric and temporal. Block 5 added
the run 1f4ba02d-a358-46a1-adae-fa9de06e23e5 for bird:california_schools (3 tables, 89 columns, verifier 467
checks OK). The profiler and profile_verify accept `--source bird:<db_id>`.

### config/profiler.yaml (all keys optional)
top_n=10 (1-100), value_max_chars=100, top_values_categories=[text,numeric,boolean], max_columns_per_query=50
(1-100), statement_timeout_seconds=300.

### sql/02_dq_schema.sql (hand-written, idempotent)
- dq.profile_runs(run_id uuid PK, source_id, schemas text[], started_at, finished_at, status
  running|completed|failed, tables_profiled, columns_profiled, notes) [9 cols].
- dq.profile_tables(run_id, source_id, schema_name, table_name, row_count, column_count, stats_sql, elapsed_ms),
  PK (run_id, schema_name, table_name) [8].
- dq.profiles(run_id, source_id, schema_name, table_name, column_name, ordinal_position, data_type, type_category,
  row_count, null_count, null_pct numeric(7,4), distinct_count, distinct_pct (of non-null), min_value text,
  max_value text, mean_value, stddev_value, min_length, max_length, avg_length, top_values jsonb
  [{value,count,pct of ALL rows}], top_values_sql), PK (run_id, schema_name, table_name, column_name) [22].
- View dq.latest_profiles = newest completed profile per (source_id, schema, table, column) + profiled_at [23].

### src/dq/init_schema.py (python -m src.dq.init_schema [--reset] [--reset-rules])
- Constants SQL_FILES (02 and 03), RESET_PROFILING_SQL, RESET_RULES_SQL, EXPECTED; main() -> int.
- Applies both SQL files in one transaction, prints the 8 dq objects and checks that t2s_reader has no USAGE on
  schema dq (exit code 1 otherwise).

### src/dq/profiler_sql.py (pure functions, no DB; python -m src.dq.profiler_sql prints a demo)
- Constants PROFILER_CONFIG_FILE, NUMERIC, TEMPORAL, TEXTUAL; type Category = numeric|text|temporal|boolean|other.
- ProfilerConfig(top_n, value_max_chars, top_values_categories, max_columns_per_query, statement_timeout_seconds);
  load_profiler_config() -> ProfilerConfig (defaults if the YAML is missing).
- qi(name) -> str (quote identifier, doubles embedded quotes); category_of(data_type) -> Category.
- ColumnRef(name, data_type, position) frozen dataclass, property .category.
- ColumnStats dataclass: name, position, data_type, category, row_count, null_count, null_pct, distinct_count,
  distinct_pct, min_value, max_value, mean_value, stddev_value, min_length, max_length, avg_length, top_values,
  top_values_sql.
- chunk_columns(columns, size); build_stats_sql(schema, table, columns) -> str (ONE scan); parse_stats(columns,
  row: Mapping) -> list[ColumnStats]; build_top_values_sql(schema, table, column, config) -> str;
  wants_top_values(stats, config) -> bool; format_top_values(rows, row_count) -> list[dict]; main() demo.

### src/dq/profiler.py (python -m src.dq.profiler [--source olist|bird:<db_id>] [--tables schema.table ...]
### [--no-top-values])
- SQL constants START_RUN, FINISH_RUN, FAIL_RUN, INSERT_TABLE, INSERT_COLUMN.
- run_generated(conn, sql): runs parameter-free generated SQL via text() with ':' escaped (REUSED by the runner).
- resolve_source(source) -> list[str]; fetch_columns(conn, schemas) -> dict[(schema, table), list[ColumnRef]];
  profile_table(conn, source_id, run_id, schema, table, columns, cfg, with_top_values) ->
  (list[ColumnStats], seconds); main() -> int. Admin engine. Transactions: register run + commit; one REPEATABLE
  READ transaction with explicit statement_timeout for all work + 'completed'; on error rollback and mark 'failed'
  (notes) in a third transaction.

### src/dq/profile_verify.py (python -m src.dq.profile_verify [--source olist|bird:<db_id>])
- close(a, b) -> bool; verify_column(conn, p, cfg) -> (n_checks, mismatches) (recomputes nulls via FILTER, distinct
  via SELECT DISTINCT subquery, min/max via ORDER BY ... LIMIT 1 with an aliased output, mean via sum/count, top-1
  count); main() -> int (also checks row counts and column coverage). Read-only.

### src/dq/profile_inspect.py (one-off Step 1 helper; --include-bird): has its own qi/category copies; may be
deleted.

### tests/test_block3.py: 17 tests (11 no-DB on profiler_sql; 6 marked db: coverage of the latest olist run,
orders delivery nulls vs independent count, stored stats_sql is runnable, verifier passes for sales.orders,
t2s_reader cannot read dq.profiles, '%' and ':' in identifiers are escaped).

## D. Block 4: Rule engine (DONE; 22 tests)
Scan 27004c18-5a51-4b92-9f54-9a0b84e5e1b4: 41 rules, 35 passed, 6 failed, 0 errors. rule_verify: 18 rules match.

### config/dq_rules/*.yaml (source_id: olist; 41 rules)
olist_sales.yaml (10), olist_customer.yaml (9), olist_catalog.yaml (7), olist_marketing.yaml (6),
olist_sales_extra.yaml (9). File layout: `source_id: olist` then `rules:` (list). Rule fields: id
(^[a-z][a-z0-9_]*$, unique across ALL files), table ("schema.table"), type, column or columns, dimension (optional
only for NON_NULL, UNIQUENESS, RANGE, SET, REGEX), threshold (0-100, default 100), description, enabled (default
true); type-specific: RANGE min_value/max_value/strict_min/strict_max/ignore_null; SET values/ignore_null; REGEX
pattern/ignore_null; ROW_CONDITION and TABLE_CONDITION expression; SQL_ASSERTION sql (returns VIOLATING rows).

### sql/03_dq_rules_schema.sql (hand-written, idempotent)
- dq.rules(source_id, rule_id, schema_name, table_name, column_names text[], rule_type, dimension, threshold
  numeric(5,2), description, definition jsonb, enabled, updated_at), PK (source_id, rule_id) [11 cols].
- dq.scan_runs(run_id uuid, source_id, started_at, finished_at, status running|completed|failed, rules_total,
  rules_passed, rules_failed, rules_errored, notes) [10].
- dq.results(run_id, source_id, rule_id, schema_name, table_name, column_names, rule_type, dimension, threshold,
  total_rows, passed_rows, failed_rows, pass_pct numeric(7,4), passed bool, status passed|failed|error, sql_used,
  failing_sql, sample_failures jsonb, error_message, elapsed_ms), PK (run_id, rule_id) [20].
- View dq.latest_results = newest completed verdict per (source_id, rule_id) + scanned_at [21]. READ THIS VIEW.

### src/dq/rules_models.py (python -m src.dq.rules_models [--check-db])
- RULES_DIR, Dimension, DEFAULT_DIMENSION, FORBIDDEN_IN_SQL (";", "--", "/*", "*/").
- BaseRule(id, table, column, dimension, threshold, description, enabled, source_id) with extra="forbid";
  subclasses NonNullRule, UniquenessRule(columns), RangeRule, SetRule, RegexRule, RowConditionRule,
  TableConditionRule, SqlAssertionRule (sql must start with SELECT or WITH); union Rule discriminated on "type";
  RULE_ADAPTER (validate_python(dict) works without source_id).
- RuleFileError(problems); first_error(exc); load_rules(directory=RULES_DIR) -> list[Rule] (sets rule.source_id from
  the file; raises RuleFileError listing ALL problems; checks duplicate ids); columns_of(rule) -> list[str];
  check_db(rules) -> list[str] (admin engine, information_schema); BAD_EXAMPLES (7 dicts); show_rejections();
  main() -> int.

### src/dq/rule_compiler.py (pure; python -m src.dq.rule_compiler [--rule ID ...] [--all])
- SAMPLE_SIZE=10; CompiledRule(rule_id, kind row|table|assertion, count_sql, failing_sql|None).
- lit(value); num(x); row_predicate(rule) -> str; compile_rule(rule, sample_size=10) -> CompiledRule (count_sql
  returns total_rows, passed_rows, failed_rows; failing_sql adds t.*, the predicate as _dq_ok, filters NOT _dq_ok);
  judge(rule, total, passed, failed) -> (pass_pct, passed: bool); main().

### src/dq/runner.py (python -m src.dq.runner [--source olist] [--rules ID ...] [--rules-dir PATH] [--timeout 120])
- SQL constants UPSERT_RULE, START_RUN, FINISH_RUN, FAIL_RUN, INSERT_RESULT.
- rule_params(r) -> dict; execute_rule(reader_engine, rule, timeout_s) -> dict (result row with key "status"
  passed|failed|error and "error_message"; never raises; SET LOCAL statement_timeout); print_report(results);
  main() -> int. Rule SQL runs through get_reader_engine() (t2s_reader). Writes via admin: transaction 1 (upsert ALL
  source rules into dq.rules + create scan_runs row), execution, transaction 2 (insert results + completed); on any
  exception (including Ctrl+C) the scan is marked failed.

### src/dq/rule_verify.py (python -m src.dq.rule_verify [--source olist])
- INDEPENDENT dict rule_id -> (kind 'row'|'zero', SQL returning (total, failed)) for 18 Olist rules;
  expected_status(kind, total, failed, threshold); main() -> int (also checks stored results == enabled rules).

### tests/test_block4.py: 22 tests (15 no-DB, 7 marked db incl. end-to-end 3-rule scan under source test_block4).

## E. Block 5: Recommender, scoring, report (DONE; 20 tests)
- src/dq/recommender.py (pure; demo `python -m src.dq.recommender`): Suggestion(rule: dict, confidence
  high|medium|low, reason); MIN_ROWS=20, MAX_NULL_PCT=10, MAX_SET_VALUES=10, MAX_VALUE_CHARS=60, RARE_SHARE=0.001,
  MIN_FIXED_LENGTH=8; slug(text); is_id_like(name); number(text); make_rule(p, kind, rule_type, threshold,
  description, **extra) -> dict (id rec_<schema>_<table>_<column>_<kind>, field "column"); suggest_non_null /
  suggest_unique / suggest_set / suggest_range / suggest_length (p) -> list[Suggestion]; CHECKS;
  recommend_column(p) -> list[Suggestion]; recommend_all(profiles) (suffix _2,_3 on id collisions);
  sample(schema, table, column, category, rows, nulls, distinct, **extra) fake profile row. p = a dq.profiles row.
  Heuristics: NON_NULL (0 nulls -> 100; <=10% nulls -> floor(100-null%)); UNIQUENESS (100% distinct + id-like
  name); SET (text, 2-10 distinct values covering every row; low confidence if a value < 0.1%); RANGE min 0
  (numeric, min >= 0, not id-like); REGEX ^.{N}$ (id-like text of fixed length >= 8).
- src/dq/recommend_run.py (`python -m src.dq.recommend_run [--source] [--min-confidence] [--verify] [--timeout]`):
  OUT_DIR=config/dq_suggestions; RANK; load_profiles(source) -> list[dict]; existing_rules(source) -> (keys, ids);
  is_duplicate(s, keys, ids); render(source, suggestions) -> str (YAML with a "# [confidence] reason" comment per
  rule); verify(rules, timeout_s) -> int (runs rules via execute_rule, no writes); main(). Self-checks: reload with
  load_rules(OUT_DIR) + check_db.
- src/dq/scoring.py (pure; demo `python -m src.dq.scoring`): DIMENSIONS, CENT, GOOD=99, FAIR=95; Score(name,
  score|None, rules, passed); Scorecard(overall, dimensions, tables [worst first], table_dimensions, errored,
  worst_rules); band(score); average(values); score_group(name, rows); table_of(r); group_by; dimension_order;
  build_scorecard(results); row(rule_id, table, dim, pct, status) and show(score) demo helpers.
- src/dq/score_run.py (`python -m src.dq.score_run [--source]`): load_results(source); independent_scores(source)
  (SQL AVG formulation); key; card_scores(card); compare; print_card; main(). Exit 1 on any mismatch.
- src/dq/report_md.py (pure): FENCE, NOTE, SCORE_HEADERS; cell; md_table(headers, rows); score_rows; finding(i, f);
  build_report(source, card, failing, null_columns, coverage, scanned_at, profiled_at) -> str.
- src/dq/report.py (`python -m src.dq.report [--source] [--out]`): REPORT_DIR; FAILING_SQL, NULLS_SQL,
  PROFILED_AT_SQL, COVERAGE_SQL, PROFILE_COLS_SQL, RESULT_COLS_SQL; fetch(sql, source) -> list[dict];
  coverage_in_python(source); check_report(report, card, failing, coverage, source) -> list[str]; main().
- tests/test_block5.py: 16 no-DB tests + 4 db tests.
Results: Olist overall 93.81 (35/41 rules passed); Completeness 78.03 (4/7), Uniqueness 100 (7/7), Validity 100
(13/14), Consistency 100 (10/11), Timeliness 50.00 (1/2); worst tables closed_deals 76.87, order_reviews 85.32,
orders 90.00. Report reports/dq_report_olist.md = 155 lines, self-check 0 problems, SQL cross-check 16 scores 0
mismatches. Olist recommender: 113 suggested, 20 already covered, 93 new (NON_NULL 59, REGEX 17, RANGE 8,
UNIQUENESS 2, SET 7; high 48, medium 45), all 93 pass when run. BIRD california_schools: 89 profiled columns, 92
suggestions (NON_NULL 57, RANGE 22, SET 9, UNIQUENESS 2, REGEX 2; high 28, medium 61, low 3), promoted, scan
92/92 passed, overall 100.

## F. Real findings to reuse (DQ Advisor demo, reports)
products_category_present: 610 of 32,951 null (98.15% < 99). products_category_translated: pc_gamer and
portateis_cozinha_e_preparadores_de_alimentos have no translation (99.99%). reviews_comment_message_present:
41.30% present (58,247 null). closed_deals: has_company 92.52%, has_gtin 92.40%, average_stock 92.16%,
declared_product_catalog_size 91.81% null (closed_deals_company_known passes only 7.48%).
payments_installments_positive: 2 of 103,886 payments have 0 installments (99.9981%, shows as 100.00 in the table
score). orders_data_is_recent (Timeliness) fails at 0.00%: data ends in 2018. Passed with small defects: 8 delivered
orders without a delivery date (99.992%), 4 products with weight 0, 31 latitudes and 37 longitudes outside Brazil,
60 leads without an origin (99.25%). sales.orders nulls: order_approved_at 160, order_delivered_carrier_date 1,783,
order_delivered_customer_date 2,965 (2.98%). order_status top values: delivered 96,478, shipped 1,107, canceled 625,
unavailable 609, invoiced 314, processing 301, created 5, approved 2.
BIRD california_schools most-null columns: schools.admfname3/admlname3/admemail3 99.76%, admemail2 97.60%,
admfname2/admlname2 97.56%, ext 96.95%, fundingtype 90.72% (legitimately optional fields).

## G. Block 7: LLM fundamentals + provider interface (DONE; tests/test_block7.py = 15: 12 no-DB, 3 llm)
- src/adapters/llm/base.py: LLMProvider(ABC) with attribute `name`; abstract chat_model(temperature=0.0) ->
  BaseChatModel, embeddings() -> Embeddings, properties chat_model_name, embedding_model_name.
- src/adapters/llm/gemini.py: GeminiProvider(settings=None). The ONLY file importing langchain_google_genai.
  Filters the "fixed sampling defaults" UserWarning. Embedding vectors are 3072-dim.
- src/common/llm.py (factory): PROVIDERS dict {name: (module, class)}; get_provider(name=None) -> LLMProvider
  (ValueError "Unknown LLM_PROVIDER ... Supported: ..."); get_chat_model(temperature=0.0); get_embeddings();
  response_text(response) -> str (handles str or list-of-blocks content). New vendor = one file + one line.
- src/common/llm_guard.py: LlmLimits(max_attempts=4, base_delay_seconds=2.0, max_delay_seconds=30.0,
  min_interval_seconds=0.0); LIMITS_FILE=config/llm.yaml (optional); load_limits(); is_transient(exc) (codes 429/
  500/502/503/504, TimeoutError, ConnectionError, words like resource_exhausted/unavailable/overloaded);
  backoff_delay(attempt, limits, jitter); Throttle(min_interval).wait(); shared_throttle();
  call_resilient(fn, *args, limits=None, throttle=None, sleep=time.sleep, **kw); resilient(runnable) -> Runnable
  (sync invoke only). Demo: python -m src.common.llm_guard (fake failures, then one real call).
- src/common/llm_basics.py and llm_structured.py: demos. llm_structured defines SqlAnswer(sql, reasoning,
  tables_used) and Route(intent Literal[data_question, dq_question, metadata_question, out_of_scope], confidence)
  as templates for the SQL Generator and Router agents (use model.with_structured_output(PydanticClass)).
- Tests prove extensibility: a FakeProvider plugs in via PROVIDERS with one class + one line.

## H. Block 8: Metadata generation + scoring (DONE; tests/test_block8.py = 16: 12 no-DB, 4 db; suite 139)
- sql/04_meta_schema.sql (hand-written, idempotent) applied by src/metadata/init_schema.py
  (python -m src.metadata.init_schema [--reset]; EXPECTED column counts; checks t2s_reader has no USAGE on meta):
  meta.generation_runs [10 cols: run_id, source_id, model, prompt_version, started_at, finished_at, status,
  tables_done, columns_done, notes]; meta.tables [11: PK source_id+schema_name+table_name; description, synonyms
  text[], status draft|approved|rejected, generated_by, run_id, updated_at, reviewed_by, reviewed_at];
  meta.columns [17: PK source_id+schema_name+table_name+column_name; data_type, ordinal_position, description,
  synonyms, column_role identifier|measure|category|date|flag|free_text, is_pii, pii_reason, status, generated_by,
  run_id, updated_at, reviewed_by, reviewed_at]; meta.reference_descriptions [9: BIRD human text: human_name,
  description, data_format, value_description, loaded_at]; meta.description_scores [10: score_run_id, source_id,
  schema_name, table_name, column_name, generated_text, reference_text, similarity numeric(7,4), embedding_model,
  scored_at].
- prompts/metadata.txt: system prompt with one variable {source_note}. Version tag PROMPT_VERSION="metadata-v1".
- src/metadata/context.py (pure): TOP_SHOWN=6, VALUE_CHARS=30, CHUNK_SIZE=40, PII_NAME regex; pii_hint(column);
  short(value, limit); pct(x); top_values_of(p); column_line(p) (double-quoted identifier, type, nulls, distinct,
  range for numeric/temporal, top values, NAME-LOOKS-PERSONAL); chunk_profiles(profiles, size=40);
  build_table_context(schema, table, row_count, profiles).
- src/metadata/models.py: PROMPT_DIR, MAX_DESC_CHARS=400, MAX_SYNONYMS=6, STRONG_PII regex; ColumnMeta(column_name,
  description, synonyms, column_role, is_pii, pii_reason); TableMeta(table_description, table_synonyms, columns);
  load_prompt(name="metadata"); final_pii(column_name, llm_flag); clean_column(c); check_table_meta(meta,
  expected, need_table_text=True) -> list[str].
- src/metadata/llm_generate.py: MAX_ATTEMPTS=2; MetadataGenerationError(table, problems); build_chain(model);
  finalize_column(c); ask_chunk(...); generate_table(chain, source_note, schema, table, row_count, profiles) ->
  TableMeta (chunks of 40 columns, one corrective retry with feedback, handles a None answer). `chain` is
  anything with .invoke(dict) -> TableMeta (tests use StubChain).
- src/metadata/generator.py (python -m src.metadata.generator --source olist|bird:<db_id> [--tables schema.table
  ...] [--dry-run]): reads dq.latest_profiles (admin engine), all LLM calls first, then ONE transaction writing
  meta.tables/meta.columns as 'draft' (ON CONFLICT ... WHERE status <> 'approved'), run in meta.generation_runs;
  failures write nothing and mark the run failed. Helpers: source_note(source), fail_run(engine, run_id, notes),
  write_all(conn, source, run_id, model, results, profiles).
- src/metadata/meta_check.py (python -m src.metadata.meta_check [--source]): read-only; coverage by SQL anti-join
  and Python set difference, empties, status/role mix, PII list, 5 samples; exit 1 on gaps.
- src/metadata/bird_desc_inspect.py: BIRD (= data/bird), read_csv(path) -> (rows, encoding) (utf-8-sig, cp1252,
  latin-1; keys lower-cased), main() inspection. Result: 798 columns, all matched, 653 with description, 278 with
  value_description, 145 without description.
- src/metadata/ref_loader.py (python -m src.metadata.ref_loader): loads BIRD human descriptions for all 11
  databases into meta.reference_descriptions (source_id bird:<db_id>) in one transaction, re-runnable, matched
  case-insensitively against real Postgres columns, verified against a CSV recount (exit 1 on mismatch or
  unmatched). Functions pg_columns(conn), build_rows(desc_root, pg).
- src/metadata/desc_score.py (python -m src.metadata.desc_score [--source bird:california_schools]): PAIRS_SQL
  (meta.columns JOIN meta.reference_descriptions), cosine(a, b), partner_indices(tables), band(sim) (strong >=
  0.80, fair >= 0.65, else weak), embed_all(texts) (batches of 50 via call_resilient), writes
  meta.description_scores, prints mean/median/control/bands/per-table/worst 5.
- src/metadata/desc_rank.py (python -m src.metadata.desc_rank [--source]): group_by_table, rank_sorted,
  rank_counted (two independent formulations, competition ranking for ties), ranks(gen, ref, tables); prints
  top-1, top-3, MRR vs random top-1 and the misses.
- Results: Olist metadata 11 tables / 70 columns as drafts (confirm with meta_check). bird:california_schools: 3
  tables / 89 columns as drafts; desc_score run 81b835d7-cf15-4cfd-82be-65989ef05804: 72 pairs, mean 0.8796,
  median 0.8893, control 0.8106, strong 65 / fair 7 / weak 0; per table frpm 0.8822, satscores 0.8579, schools
  0.8844; desc_rank: top-1 68.1%, top-3 83.3%, MRR 0.773, random top-1 4.2% (misses are mostly bare-label or
  misaligned human references).
- Open items: review/approve drafts (no UI yet); metadata for the other 10 BIRD databases comes after they are
  profiled (end-of-project task); the Olist PII list should be eyeballed once.

## I. Block 9: Knowledge Graph (DONE; tests/test_block9.py = 8: 5 no-DB, 3 db; suite 147)
- sql/05_kg_schema.sql (hand-written, idempotent): meta.kg_nodes [6 cols: node_id PK, source_id, node_type, name, properties jsonb, created_at], meta.kg_edges [8 cols: edge_id PK, source_id, edge_type, src_node_id FK, tgt_node_id FK, weight numeric(5,4), properties jsonb, created_at].
- src/metadata/kg_models.py: NodeType (domain, table, column, dq_rule, business_term, metric), EdgeType (contains, has_column, joins_with, has_dq_rule, synonym_of), node_id(source_id, node_type, *parts), edge_id(source_id, edge_type, src, tgt), KGNode, KGEdge, JoinCandidate(src_table, tgt_table, src_col, tgt_col, overlap_pct, reason).
- src/metadata/kg_infer.py: is_candidate_pair(c1, c2) (checks names/suffixes and types), build_overlap_sql(c1, c2), measure_overlap(conn, c1, c2, min_overlap=0.75), infer_joins(conn, cols, min_overlap).
- src/metadata/kg_builder.py (pure): build_kg_entities(source_id, domains, tables, columns, rules, joins) -> (list[KGNode], list[KGEdge]). Weights joins as 2.0 - (overlap_pct / 100.0) with bidirectional edges.
- src/metadata/bird_fk.py: find_dev_tables_file(), load_bird_fks(db_id) -> list[JoinCandidate] (reads dev_tables.json as ground truth for BIRD FKs).
- src/metadata/kg_loader.py (python -m src.metadata.kg_loader [--source olist|bird:<db_id>]): fetch_source_data, get_joins_for_source, load_kg(source_id). Atomic replacement in one transaction.
- src/metadata/kg_graph.py (python -m src.metadata.kg_graph [--source] [--from-table] [--to-table]): load_graph(engine, source_id) -> nx.DiGraph, find_join_path(G, source_id, src_table, tgt_table) -> list[dict], format_join_sql(hops) -> str.
- Results: Olist KG = 126 nodes (4 domains, 11 tables, 70 columns, 41 rules), 150 edges (14 inferred joins x 2 = 28 joins_with); customer.customers to catalog.products resolves in 3 hops (customers -> orders -> order_items -> products). BIRD california_schools KG = 185 nodes (1 domain, 3 tables, 89 columns, 92 rules), 188 edges (2 FKs x 2 = 4 joins_with); satscores to frpm resolves in 2 hops via schools.

## J. Block 10: Business Ontology (DONE; tests/test_block10.py = 8: 4 no-DB, 4 db; suite 155)
- sql/06_ontology_schema.sql (hand-written, idempotent): meta.ontology_terms [11 cols: term_id PK, source_id, term_name, term_type (metric|concept|dimension), definition, sql_expression, base_table, mapped_columns text[], synonyms text[], status (draft|approved|rejected), created_at, updated_at].
- config/ontology/olist.yaml: 7 approved terms (Gross Revenue, Net Item Revenue, Delivered Orders, Delivery Delay Days, Average Review Score, Freight Share, Lead Conversion Rate).
- config/ontology/bird_california_schools.yaml: 5 approved terms (Total SAT Score, High Poverty School, Charter School, SAT Test Takers Count, Average FRPM Rate).
- src/metadata/ontology_models.py: TermType, ReviewStatus, slug(text), make_term_id(source_id, term_type, term_name), OntologyTerm (Pydantic model with auto-assigned deterministic term_id), OntologyFile (auto-propagates root source_id to child terms).
- src/metadata/ontology_loader.py (python -m src.metadata.ontology_loader [--source olist|bird:<db_id>]): load_ontology_file, sync_ontology (reads YAML, validates with Pydantic, and executes idempotent ON CONFLICT DO UPDATE upsert into meta.ontology_terms in one transaction).
- src/metadata/ontology_kg_sync.py (python -m src.metadata.ontology_kg_sync [--source olist|bird:<db_id>]): sync_ontology_to_kg (projects approved ontology terms into meta.kg_nodes as node_type 'metric' or 'business_term' and connects them to base tables via 'measures' edges in meta.kg_edges in one atomic transaction).
- Results: Olist has 7 approved ontology terms mapped to KG (total Olist KG = 133 nodes, 157 edges); bird:california_schools has 5 approved terms mapped to KG (total BIRD KG = 190 nodes, 193 edges).

## K. Block 11: Embeddings & Vector Search (DONE; tests/test_block11.py = 5: 2 no-DB, 3 db; suite 160)
- sql/07_embeddings_schema.sql (hand-written, idempotent): meta.schema_embeddings [8 cols: id PK, source_id, entity_type, entity_name, content, metadata jsonb, embedding vector(768), created_at], HNSW cosine index.
- src/adapters/vectordb/base.py: VectorItem, SearchResult, VectorStore (abstract interface: add_items, similarity_search, delete_by_source).
- src/adapters/vectordb/pgvector.py: PostgresVectorStore(engine) implementing VectorStore using pgvector operator <=>.
- src/metadata/indexer_prep.py (pure): RawEmbeddingItem, truncate_and_normalize(vec, 768), format_table_payload, format_column_payload, format_ontology_payload.
- src/metadata/indexer.py (python -m src.metadata.indexer [--source olist|bird:<db_id>]): index_source (batches of 50 via call_resilient, downsamples to 768 dims, stores via PostgresVectorStore).
- src/metadata/retriever.py (python -m src.metadata.retriever [--source] [--query] [--k]): SchemaRetriever(store, embed_model) retrieving top-k schema components and ontology terms ranked by cosine similarity.
- Results: Olist indexed = 88 items (11 tables, 70 columns, 7 ontology terms); bird:california_schools indexed = 97 items (3 tables, 89 columns, 5 ontology terms). Query "late deliveries and high payments" retrieves Delivery Delay Days, orders, customers, and order_payments in top matches.

## L. Block 12: Baseline Text2SQL & Golden Set (DONE; tests/test_block12.py = 11 no-DB; suite 171 passed)
- prompts/baseline.txt: Baseline PostgreSQL prompt with schema context and strict SELECT-only instructions.
- src/text2sql/baseline/validator.py: ValidationResult(is_valid, cleaned_sql, tables, error_message); FORBIDDEN_EXPRESSIONS (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter, exp.Command, exp.Create); extract_sql_code(raw_text); validate_and_clean_sql(raw_sql, dialect="postgres", default_limit=100) enforcing SELECT-only, no data-modifying CTEs, and auto-LIMIT injection.
- src/text2sql/baseline/schema_context.py: format_schema_for_prompt(columns), get_baseline_schema_context(schemas, connector). Formats raw tables and columns into clean text context.
- src/text2sql/baseline/chain.py: BaselineResult(question, generated_sql, is_valid, tables_used, row_count, error, elapsed_ms, query_result); run_baseline(question, schemas=None, default_limit=100, connector=None) executing the end-to-end baseline chain.
- config/golden_olist.yaml: 50 golden questions across all dimensions (15 single-domain, 10 cross-domain, 10 ontology/metrics, 11 edge/DQ/ambiguous, 4 malicious injections) with gold PostgreSQL queries.
- src/eval/comparer.py: normalize_value, rows_match, compare_results(gold_rows, pred_rows, order_sensitive=False) supporting float tolerance (1e-3), string trimming/case-insensitivity, and order-insensitive multiset comparison.
- src/eval/runner.py (python -m src.eval.runner [--limit N] [--category CAT]): Evaluates golden queries against the baseline chain and reports Valid SQL %, Execution Accuracy %, and Average Latency.

## M. Block 12B: BIRD Benchmark Evaluation Harness (DONE; tests/test_block12b.py = 5 no-DB; suite 176 passed)
- src/eval/bird_sampler.py: find_bird_json() locating mini_dev_postgresql.json; sample_stratified(questions, target_count=100, seed=42) producing reproducible, proportional samples across 11 databases and 3 difficulty tiers (simple 30, moderate 50, challenging 20); get_bird_sample(target_count=100, seed=42, out_path). Writes data/bird/mini_dev_sample_100.json.
- src/eval/bird_cache.py: CACHE_FILE (data/bird/bird_eval_cache.json); make_cache_key(question_id, with_evidence, model_name); load_eval_cache(); save_eval_cache(); FreeTierThrottler(min_interval_seconds=4.2) enforcing safe pacing for Gemini Free Tier (15 RPM).
- src/eval/bird_runner.py (python -m src.eval.bird_runner [--limit N] [--all] [--no-evidence] [--db DB_ID]): Runs BIRD benchmark evaluation against PostgreSQL with search_path switching (bird_<db_id>), disk caching, AST validation (auto-limit disabled), tolerant execution matching, and accuracy breakdown by difficulty.
- tests/test_block12b.py: 5 unit tests verifying BIRD JSON discovery, stratified distribution math, cache key generation, atomic cache persistence, and throttler pacing.

## N. Block 13: Core LangGraph Multi-Agent Architecture (DONE; tests/test_block13.py = 8: 6 no-DB, 2 db; suite 184 passed)
- src/text2sql/agents/state.py: IntentType, AgentState TypedDict (24 state keys: question, rewritten_question, chat_history, intent, source_id, evidence, cache_hit, needs_clarification, clarification_question, resolved_terms, selected_domains, selected_tables, selected_columns, join_path, generated_sql, reasoning, validation_errors, is_valid_sql, retry_count, max_retries, execution_result, column_names, error_message, row_count, dq_warnings, final_answer, chart_suggestion); create_initial_state().
- src/text2sql/agents/generator.py: SqlGenerationOutput(reasoning, sql, tables_used) Pydantic model; get_target_schemas(source_id); build_generator_prompt(state, schema_ctx); sql_generator_node(state) executing structured SQL synthesis with evidence and resolved ontology context.
- src/text2sql/agents/validator_node.py: FORBIDDEN_SCHEMAS; sql_validator_node(state) verifying AST SELECT-only safety, appending LIMIT, and blocking internal schema leakage (raw, dq, meta, app).
- src/text2sql/agents/executor.py: resolve_search_path(source_id); sql_executor_node(state, connector) executing as t2s_reader with schema switching (bird_<db_id>) and capturing engine exceptions into state["error_message"].
- src/text2sql/agents/corrector.py: CORRECTOR_SYSTEM_PROMPT; build_corrector_prompt(state, schema_ctx); sql_corrector_node(state) diagnosing runtime/AST defects, incrementing retry_count, and synthesizing repaired SQL.
- src/text2sql/agents/graph.py: route_after_validation(state), route_after_execution(state), build_core_graph() assembling StateGraph with self-correction cycle, run_agentic_text2sql(question, source_id, evidence, max_retries).
- tests/test_block13.py: 8 unit & integration tests covering state initialization, validator safety/guardrails, conditional routing transitions, graph compilation, and live executor query/error capture.

## O. Block 14: Router, Rewriter, Clarifier, Ontology Resolver, DQ Advisor & Specialists (DONE; tests/test_block14.py = 9; suite 193 passed)
- src/ingestion/setup_roles.py: Updated to grant t2s_reader USAGE on schema dq and SELECT on dq.latest_results and dq.latest_profiles views.
- src/text2sql/agents/router.py: RouterOutput(intent, reasoning, confidence); build_router_prompt(); router_node(state) classifying into data_question, dq_question, metadata_question, or out_of_scope.
- src/text2sql/agents/rewriter.py: RewriterOutput(rewritten_question, was_rewritten); format_history(chat_history); rewriter_node(state) resolving conversational pronouns with fast-path bypass when history is empty.
- src/text2sql/agents/clarifier.py: ClarifierOutput(is_ambiguous, clarification_question, reasoning); build_clarifier_prompt(); clarifier_node(state) flagging critically underspecified data queries.
- src/text2sql/agents/ontology_resolver.py: load_ontology_terms(source_id); match_terms(question, terms); ontology_resolver_node(state) matching business terms by name/synonyms and injecting approved SQL expressions.
- src/text2sql/agents/dq_advisor.py: format_rule_advisory(table, cols, dim, rule_type, pass_pct); extract_table_names(state); dq_advisor_node(state, engine) querying dq.latest_results and dq.latest_profiles as t2s_reader, dynamically synthesizing executive-ready advisories by DQ dimension.
- src/text2sql/agents/specialists.py: REFUSAL_MESSAGE; refusal_node(state) returning polite enterprise refusal; dq_agent_node(state) answering DQ questions from scan results; metadata_agent_node(state) explaining ontology terms and metrics.
- src/text2sql/agents/graph.py: clarification_responder(state); answer_synthesizer(state); route_intent(state); route_clarification(state); route_after_validation(state); route_after_execution(state); build_agentic_graph(); build_core_graph alias; run_agentic_text2sql(question, source_id, evidence, chat_history, max_retries). Full LangGraph StateGraph pipeline.
- tests/test_block14.py: 9 tests (8 no-DB, 1 db) covering fast paths, ambiguity checks, ontology matching, dynamic dimension formatting, table extraction, refusal, conditional routing, graph compilation, and live DB advisor execution.

## P. Block 15: Semantic Cache (DONE)
- sql/08_app_schema.sql (hand-written, idempotent): app.semantic_cache [8 cols: id PK, source_id, question, generated_sql, tables_used, embedding vector(768), feedback_score, created_at], HNSW cosine index.
- src/app/init_schema.py (python -m src.app.init_schema [--reset]): init_app_schema(reset) applies the SQL and verifies that t2s_reader is blocked from accessing the app schema.
- src/app/cache.py (python -m src.app.cache): CacheEntry model; SemanticCache class with add(), search(limit=3, threshold=0.85), and _embed() (truncates to 768 dims and L2 normalizes). Uses admin_engine.
- src/text2sql/agents/cache_nodes.py (python -m src.text2sql.agents.cache_nodes): CacheVerification model; cache_lookup_node(state) finds vector matches and uses LLM to verify exact parameter matches; write_cache_feedback(state, score) helper for API integration.
- src/text2sql/agents/graph.py: Updated to include cache_lookup_node. route_clarification routes to cache_lookup; route_after_cache routes to sql_executor on hit, or ontology_resolver on miss.

## Q. Block 16: Cross-Domain Schema Linking (DONE)
- src/text2sql/agents/schema_linker.py (python -m src.text2sql.agents.schema_linker): schema_linker_node(state) uses SchemaRetriever to find top-10 semantic matches for tables/columns and appends base tables from resolved ontology terms.
- src/text2sql/agents/domain_selector.py (python -m src.text2sql.agents.domain_selector): domain_selector_node(state) uses NetworkX Knowledge Graph to find shortest join paths between selected tables, returning deterministic SQL join conditions.
- src/text2sql/agents/generator.py: Updated build_targeted_schema_context to filter schema to only selected_tables. Prompt updated to inject {join_path}.
- src/text2sql/agents/graph.py: Wired schema_linker and domain_selector into the main flow (ontology_resolver -> schema_linker -> domain_selector -> sql_generator).
- tests/test_block16.py: 5 db tests verifying semantic cache, vector retrieval, KG multi-hop join discovery, and targeted schema filtering.

## R. Block 17: Full Evaluation & Agentic Fixes (DONE)
- src/eval/comparer.py: Updated to ignore column aliases by comparing values positionally, and handles Decimal/float normalization.
- src/text2sql/agents/state.py: Added eval_mode boolean to AgentState to disable LIMIT 100 guardrail during testing.
- src/text2sql/agents/executor.py: Updated to return dictionaries via .mappings() instead of raw tuples.
- src/text2sql/agents/router.py: Prompt updated to explicitly classify "distinct values" and "statuses" as data_question.
- src/text2sql/agents/ontology_resolver.py: Restored get_admin_engine() for meta schema access, and updated match_terms to return a list of dictionaries.
- src/text2sql/agents/corrector.py: Fixed bug where it tried to .append() to a string validation_errors.
- src/text2sql/agents/dq_advisor.py: Fixed rounding bug by truncating pass_pct to 2 decimals to prevent 99.99% from rounding up to 100.0%.
- src/text2sql/agents/generator.py: Added prompt rules for ORDER BY, to_char(month), and LIMIT 10 for raw records.
- src/eval/eval_agentic.py (python -m src.eval.eval_agentic): Runs the full 50-question Olist golden set through the Agentic pipeline.
- src/eval/runner.py (python -m src.eval.runner): Runs the Baseline pipeline.

## S. Block 17B: FastAPI Backend (DONE)
- requirements.txt: Added fastapi>=0.110.0 and uvicorn>=0.29.0.
- src/api/models.py: Pydantic schemas (QueryRequest, QueryResponse, FeedbackRequest).
- src/api/security.py: verify_api_key using HTTPBearer token (default: trustsql-secret-key).
- src/api/main.py: FastAPI app with CORS middleware. Endpoints: GET /health, POST /query (runs run_agentic_text2sql), POST /feedback (writes to semantic cache).
- src/api/test_client.py: Built-in urllib script to test the protected /query endpoint.


## START NOW
When I say "all parts sent":
1. Reply with a 5-line summary of where we are (Blocks 0-5, 7-17b done; Block 6 deferred;
   Block 17b next).
2. Confirm you understood the rules (especially 11, 12, 17, 18, 22, 23), that cmd is my primary shell, and that at
   the end of every block you will ask if I want to update my master prompt and provide the exact section diffs.
3. List exactly which files you need for Block 15 (probably none).
4. Then wait for me to say "start Block 18".