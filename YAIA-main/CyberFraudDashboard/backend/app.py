import os
from decimal import Decimal

import pyodbc
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

MSSQL_SERVER = os.getenv("MSSQL_SERVER", "localhost")
MSSQL_DATABASE = os.getenv("MSSQL_DATABASE", "NCRP")
MSSQL_DRIVER = os.getenv("MSSQL_DRIVER", "ODBC Driver 18 for SQL Server")

CONN_STR = (
    f"Driver={{{MSSQL_DRIVER}}};"
    f"Server={MSSQL_SERVER};"
    f"Database={MSSQL_DATABASE};"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

from graph_api import router as graph_router
from investigation_api import router as investigation_router
from profiler_api import router as profiler_router
from triage_api import router as triage_router
from intelligence_api import router as intelligence_router

app = FastAPI(title="NCRP Cyber Fraud Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(graph_router, prefix="/api")
app.include_router(investigation_router, prefix="/api")
app.include_router(profiler_router, prefix="/api")
app.include_router(triage_router, prefix="/api")
app.include_router(intelligence_router, prefix="/api")


def get_conn():
    return pyodbc.connect(CONN_STR)


def to_float(val) -> float:
    if val is None:
        return 0.0
    if isinstance(val, Decimal):
        return float(val)
    return float(val)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/summary/{ack_no}")
def get_summary(ack_no: int):
    conn = get_conn()
    try:
        cur = conn.cursor()

        # MoneyTransferTo
        cur.execute(
            "SELECT COUNT(*), ISNULL(SUM(TransactionAmount),0), ISNULL(SUM(DisputedAmount),0) "
            "FROM dbo.MoneyTransferTo WHERE AcknowledgementNo = ?",
            (ack_no,),
        )
        mt = cur.fetchone()

        # OtherTransactions
        cur.execute(
            "SELECT COUNT(*), ISNULL(SUM(OtherAmount),0) "
            "FROM dbo.OtherTransactions WHERE AcknowledgementNo = ?",
            (ack_no,),
        )
        ot = cur.fetchone()

        # PutOnHold
        cur.execute(
            "SELECT COUNT(*), ISNULL(SUM(PutOnHoldAmount),0) "
            "FROM dbo.PutOnHold WHERE AcknowledgementNo = ?",
            (ack_no,),
        )
        ph = cur.fetchone()

        # OthersLessThan500
        cur.execute(
            "SELECT COUNT(*) FROM dbo.OthersLessThan500 WHERE AcknowledgementNo = ?",
            (ack_no,),
        )
        lt = cur.fetchone()

        # AEPS
        cur.execute(
            "SELECT COUNT(*), ISNULL(SUM(WithdrawalAmount),0) "
            "FROM dbo.AEPS WHERE AcknowledgementNo = ?",
            (ack_no,),
        )
        ae = cur.fetchone()

        # ATMWithdrawal
        cur.execute(
            "SELECT COUNT(*), ISNULL(SUM(WithdrawalAmount),0), ISNULL(SUM(DisputedAmount),0) "
            "FROM dbo.ATMWithdrawal WHERE AcknowledgementNo = ?",
            (ack_no,),
        )
        atm = cur.fetchone()

        total_rows = mt[0] + ot[0] + ph[0] + lt[0] + ae[0] + atm[0]
        if total_rows == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No records found for Acknowledgement No: {ack_no}",
            )

        total_transaction = to_float(mt[1]) + to_float(ot[1])
        total_disputed = to_float(mt[2]) + to_float(atm[2])
        total_put_on_hold = to_float(ph[1])
        total_withdrawal = to_float(ae[1]) + to_float(atm[1])
        total_atm_withdrawal = to_float(atm[1])

        return {
            "ack_no": ack_no,
            "total_transaction_amount": round(total_transaction, 2),
            "total_disputed_amount": round(total_disputed, 2),
            "total_put_on_hold_amount": round(total_put_on_hold, 2),
            "total_withdrawal_amount": round(total_withdrawal, 2),
            "total_atm_withdrawal": round(total_atm_withdrawal, 2),
            "total_records": total_rows,
        }

    finally:
        conn.close()


@app.get("/api/layers/{ack_no}")
def get_layers(ack_no: int):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT ISNULL(Layer, 0) AS Layer, "
            "ISNULL(SUM(TransactionAmount), 0) AS TotalAmount "
            "FROM dbo.MoneyTransferTo "
            "WHERE AcknowledgementNo = ? "
            "GROUP BY Layer ORDER BY Layer",
            (ack_no,),
        )
        rows = cur.fetchall()
        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"No layer data for Acknowledgement No: {ack_no}",
            )
        return [
            {"layer": int(r[0]), "amount": round(to_float(r[1]), 2)}
            for r in rows
        ]
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
