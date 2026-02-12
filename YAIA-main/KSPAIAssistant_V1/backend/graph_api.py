from fastapi import APIRouter, HTTPException
from neo4j import GraphDatabase
from config import NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD

router = APIRouter(prefix="/graph", tags=["Graph Intelligence"])

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
)

# --------------------------------------------------
# 1️⃣ Fetch graph for a Crime No
# --------------------------------------------------
@router.get("/crime/{crime_no}")
def graph_by_crime(crime_no: str):
    query = """
    MATCH (p:Account)-[r:TRANSFERRED_TO]->(c:Account)
    WHERE r.crime_no = $crime_no
    RETURN p, r, c
    """
    try:
        with driver.session() as session:
            result = session.run(query, crime_no=crime_no)
            records = [r.data() for r in result]
        return {"ok": True, "records": records}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --------------------------------------------------
# 2️⃣ Investigator summary (used later by chat)
# --------------------------------------------------
@router.get("/crime/{crime_no}/summary")
def crime_summary(crime_no: str):
    query = """
    MATCH (p:Account)-[r:TRANSFERRED_TO]->(c:Account)
    WHERE r.crime_no = $crime_no
    RETURN
        count(DISTINCT p) AS total_accounts,
        sum(r.amount) AS total_amount,
        max(c.accused_account_level) AS max_layer
    """
    with driver.session() as session:
        res = session.run(query, crime_no=crime_no).single()

    return {
        "crime_no": crime_no,
        "total_accounts": res["total_accounts"],
        "total_amount": res["total_amount"],
        "max_layer": res["max_layer"]
    }
