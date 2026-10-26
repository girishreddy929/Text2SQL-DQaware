# src/text2sql/agents/schema_linker.py
from src.common.logging import get_logger
from src.common.db import get_admin_engine
from src.common.llm import get_embeddings
from src.adapters.vectordb.pgvector import PostgresVectorStore
from src.metadata.retriever import SchemaRetriever

logger = get_logger(__name__)


def schema_linker_node(state: dict) -> dict:
    """
    Retrieves the most relevant tables and columns for the question using Vector Search.
    Also includes any base tables required by resolved ontology terms.
    """
    question = state.get("rewritten_question") or state.get("question")
    source_id = state.get("source_id")

    if not question or not source_id:
        logger.warning("Missing question or source_id in state.")
        return {"selected_tables": [], "selected_columns": []}

    # 1. Initialize Vector Store and Retriever (using admin engine for meta schema access)
    engine = get_admin_engine()
    embeddings = get_embeddings()
    store = PostgresVectorStore(engine)
    retriever = SchemaRetriever(store, embeddings)

    # 2. Retrieve top 10 semantic matches
    logger.info(f"Retrieving schema elements for: '{question}'")
    try:
        results = retriever.retrieve(query=question, source_id=source_id, k=10)
    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        results = []

    selected_tables = set()
    selected_columns = []

    for res in results:
        # res is a SearchResult which has entity_type and entity_name
        if res.entity_type == "table":
            selected_tables.add(res.entity_name)
        elif res.entity_type == "column":
            # entity_name is formatted as "schema.table.column"
            parts = res.entity_name.split(".")
            if len(parts) >= 2:
                table_name = f"{parts[0]}.{parts[1]}"
                selected_tables.add(table_name)
                selected_columns.append(res.entity_name)

    # 3. Add tables required by the Ontology Resolver
    resolved_terms = state.get("resolved_terms", [])
    for term in resolved_terms:
        if term.get("base_table"):
            selected_tables.add(term["base_table"])
            logger.info(f"Added ontology base table: {term['base_table']}")

        # Also add any mapped columns' tables
        for col in term.get("mapped_columns", []):
            parts = col.split(".")
            if len(parts) >= 2:
                selected_tables.add(f"{parts[0]}.{parts[1]}")

    tables_list = sorted(list(selected_tables))
    logger.info(f"Schema Linker selected tables: {tables_list}")

    return {"selected_tables": tables_list, "selected_columns": selected_columns}


if __name__ == "__main__":
    # Quick test on Olist
    test_state = {
        "question": "Show me the late deliveries and high payments",
        "source_id": "olist",
        "resolved_terms": [
            {"term_name": "Delivery Delay Days", "base_table": "sales.orders"}
        ],
    }
    print("--- Testing Schema Linker ---")
    res = schema_linker_node(test_state)
    print(f"\nSelected Tables: {res['selected_tables']}")
    print(f"Selected Columns (Top matches): {res['selected_columns'][:3]}")
