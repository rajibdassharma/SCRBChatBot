# backend/neo4j_client.py
import os
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "sandy411")

_driver = None

def get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver

def run_cypher(query: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    drv = get_driver()
    params = params or {}
    with drv.session() as session:
        res = session.run(query, params)

        records = []
        keys = res.keys()

        for r in res:
            row = {}
            for k in keys:
                v = r.get(k)
                # Neo4j Nodes/Relationships are not JSON serializable by default.
                # Convert to dict when possible.
                try:
                    if hasattr(v, "items"):  # dict-like
                        row[k] = dict(v)
                    elif hasattr(v, "_properties"):  # Node/Relationship
                        row[k] = dict(v._properties)
                    else:
                        row[k] = v
                except Exception:
                    row[k] = str(v)
            records.append(row)

        return {"columns": list(keys), "rows": records}
