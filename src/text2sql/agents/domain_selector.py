# src/text2sql/agents/domain_selector.py
import networkx as nx
from itertools import combinations

from src.common.logging import get_logger
from src.common.db import get_admin_engine
from src.metadata.kg_graph import load_graph, find_join_path

logger = get_logger(__name__)


def domain_selector_node(state: dict) -> dict:
    """
    Uses the Knowledge Graph to find valid join paths between the selected tables.
    """
    tables = state.get("selected_tables", [])
    source_id = state.get("source_id")

    if not tables or not source_id:
        return {"join_path": ""}

    if len(tables) < 2:
        logger.info("Only one table selected; no joins needed.")
        return {"join_path": ""}

    engine = get_admin_engine()
    try:
        G = load_graph(engine, source_id)
    except Exception as e:
        logger.error(f"Failed to load Knowledge Graph: {e}")
        return {"join_path": ""}

    unique_joins = set()

    # Find shortest paths between all pairs of selected tables
    for t1, t2 in combinations(tables, 2):
        try:
            hops = find_join_path(G, source_id, t1, t2)
            for hop in hops:
                # Create a canonical, order-independent representation of the join condition
                col1 = f"{hop['from_table']}.{hop['from_col']}"
                col2 = f"{hop['to_table']}.{hop['to_col']}"

                # Sort to ensure A=B and B=A are treated as the same join
                cond = tuple(sorted([col1, col2]))
                unique_joins.add(f"{cond[0]} = {cond[1]}")

                # Also ensure intermediate tables in the path are added to selected_tables
                if hop["from_table"] not in tables:
                    tables.append(hop["from_table"])
                if hop["to_table"] not in tables:
                    tables.append(hop["to_table"])

        except Exception as e:
            logger.warning(f"Error finding path between {t1} and {t2}: {e}")

    if not unique_joins:
        return {"join_path": "", "selected_tables": sorted(list(set(tables)))}

    join_path_str = "Known valid join conditions:\n" + "\n".join(
        f"- {j}" for j in sorted(list(unique_joins))
    )
    logger.info(f"Discovered join paths:\n{join_path_str}")

    return {
        "join_path": join_path_str,
        # Update selected_tables in case the KG path required intermediate tables
        "selected_tables": sorted(list(set(tables))),
    }


if __name__ == "__main__":
    # Quick test on Olist: Joining customers to products requires 3 hops!
    # (customers -> orders -> order_items -> products)
    test_state = {
        "source_id": "olist",
        "selected_tables": ["customer.customers", "catalog.products"],
    }
    print("--- Testing Domain Selector (KG Join Paths) ---")
    res = domain_selector_node(test_state)
    print(f"\nUpdated Selected Tables: {res['selected_tables']}")
    print(f"\nJoin Path Context:\n{res['join_path']}")
