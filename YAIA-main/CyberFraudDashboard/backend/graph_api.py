import os

from fastapi import APIRouter, HTTPException
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "sandy411")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

router = APIRouter(prefix="/graph", tags=["Graph"])

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))


@router.get("/ack/{ack_no}")
def graph_by_ack(ack_no: str):
    """Return record count for an AcknowledgementNo graph."""
    query = """
    MATCH (p:Account)-[r:TRANSFERRED_TO]->(c:Account)
    WHERE r.crime_no = $ack_no
    RETURN p, r, c
    """
    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            result = session.run(query, ack_no=ack_no)
            records = [r.data() for r in result]
        return {"ok": True, "recordCount": len(records)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ack/{ack_no}/summary")
def graph_summary(ack_no: str):
    """Summary stats for the graph of an AcknowledgementNo."""
    query = """
    MATCH (p:Account)-[r:TRANSFERRED_TO]->(c:Account)
    WHERE r.crime_no = $ack_no
    RETURN
        count(DISTINCT p) + count(DISTINCT c) AS total_accounts,
        sum(r.amount) AS total_amount,
        max(c.level) AS max_layer
    """
    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            res = session.run(query, ack_no=ack_no).single()
        if not res or res["total_accounts"] == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No graph data for Acknowledgement No: {ack_no}",
            )
        return {
            "ack_no": ack_no,
            "total_accounts": res["total_accounts"],
            "total_amount": res["total_amount"],
            "max_layer": res["max_layer"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
