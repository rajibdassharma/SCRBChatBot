"""
Case Management for ISD Document Intelligence V4.

A "case" is a named, isolated workspace that belongs to one user.
All documents, vectors, and structured data are scoped to a case_id.

Provides:
  - init_cases_table()  — creates the cases table in MSSQL (called at import)
  - router              — FastAPI APIRouter with /cases/* endpoints
  - get_active_case()   — FastAPI dependency that validates case ownership
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from mssql_db import get_conn, _fetchone, _fetchall
from auth import CurrentUser, get_current_user


# ---------------------------------------------------------------------------
# Database initialisation
# ---------------------------------------------------------------------------

def init_cases_table() -> None:
    """Create the cases table in MSSQL if it does not already exist."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            IF NOT EXISTS (
                SELECT 1 FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_NAME = 'cases'
            )
            CREATE TABLE cases (
                id          INT IDENTITY(1,1) PRIMARY KEY,
                user_id     INT           NOT NULL,
                name        NVARCHAR(200) NOT NULL,
                description NVARCHAR(500),
                collection  NVARCHAR(50)  NOT NULL DEFAULT 'IR',
                created_at  DATETIME      NOT NULL DEFAULT GETDATE(),
                CONSTRAINT fk_cases_user FOREIGN KEY (user_id)
                    REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        conn.commit()
        print("[Cases] cases table ready")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helper: resolve and authorise a case
# ---------------------------------------------------------------------------

def _get_case_for_user(case_id: int, user_id: int) -> dict:
    """
    Fetch the case row and verify it belongs to the requesting user.
    Raises HTTP 404 if not found, HTTP 403 if owned by someone else.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, user_id, name, description, collection, created_at "
            "FROM cases WHERE id = ?",
            case_id,
        )
        row = _fetchone(cur)
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found.")
    if row["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied to this case.")
    row["created_at"] = str(row["created_at"])
    return row


# ---------------------------------------------------------------------------
# FastAPI dependency: get_active_case
# ---------------------------------------------------------------------------

def get_active_case(case_id: int, current_user: CurrentUser = Depends(get_current_user)) -> dict:
    """
    FastAPI dependency.  Resolves the case and confirms the current user owns it.
    Inject into any endpoint that is scoped to a specific case:

        @app.get("/docs/list")
        def docs_list(case: dict = Depends(get_active_case)):
            collection_name = f"{case['collection']}_{case['id']}"
            ...
    """
    return _get_case_for_user(case_id, current_user.user_id)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CreateCaseRequest(BaseModel):
    name: str
    description: Optional[str] = None
    collection: str = "IR"          # "IR" or "SMAC"


class UpdateCaseRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("")
def list_cases(current_user: CurrentUser = Depends(get_current_user)):
    """Return all cases belonging to the current user, newest first."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, description, collection, created_at "
            "FROM cases WHERE user_id = ? ORDER BY created_at DESC",
            current_user.user_id,
        )
        rows = _fetchall(cur)
        for r in rows:
            r["created_at"] = str(r["created_at"])
        return {"ok": True, "cases": rows, "count": len(rows)}
    finally:
        conn.close()


@router.post("", status_code=201)
def create_case(
    payload: CreateCaseRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new case for the current user."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Case name cannot be empty.")
    if payload.collection not in ("IR", "SMAC"):
        raise HTTPException(status_code=400, detail="Collection must be 'IR' or 'SMAC'.")

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO cases (user_id, name, description, collection) VALUES (?, ?, ?, ?)",
            current_user.user_id,
            name,
            payload.description or "",
            payload.collection,
        )
        conn.commit()

        # Return the newly created case
        cur.execute(
            "SELECT id, name, description, collection, created_at "
            "FROM cases WHERE user_id = ? AND name = ? "
            "ORDER BY created_at DESC",
            current_user.user_id,
            name,
        )
        row = _fetchone(cur)
        row["created_at"] = str(row["created_at"])
        return {"ok": True, "case": row}
    finally:
        conn.close()


@router.get("/{case_id}")
def get_case(
    case_id: int,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return a single case (must belong to current user)."""
    case = _get_case_for_user(case_id, current_user.user_id)
    return {"ok": True, "case": case}


@router.patch("/{case_id}")
def update_case(
    case_id: int,
    payload: UpdateCaseRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Rename or update the description of a case."""
    _get_case_for_user(case_id, current_user.user_id)   # ownership check

    updates = []
    params = []
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Case name cannot be empty.")
        updates.append("name = ?")
        params.append(name)
    if payload.description is not None:
        updates.append("description = ?")
        params.append(payload.description)

    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update.")

    params.append(case_id)
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"UPDATE cases SET {', '.join(updates)} WHERE id = ?", *params)
        conn.commit()
        case = _get_case_for_user(case_id, current_user.user_id)
        return {"ok": True, "case": case}
    finally:
        conn.close()


@router.delete("/{case_id}")
def delete_case(
    case_id: int,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Delete a case and all its associated data.
    ChromaDB collections for this case are also purged.
    """
    case = _get_case_for_user(case_id, current_user.user_id)

    # Purge ChromaDB collections for this case
    try:
        import chromadb
        from config import CHROMA_PATH
        import os
        chroma_path = os.path.join(
            os.path.dirname(__file__), CHROMA_PATH, f"case_{case_id}"
        )
        client = chromadb.PersistentClient(path=chroma_path)
        for col in client.list_collections():
            client.delete_collection(col.name)
        print(f"[Cases] Purged ChromaDB collections for case {case_id}")
    except Exception as e:
        print(f"[Cases] Warning: could not purge ChromaDB for case {case_id}: {e}")

    # Delete the case row (FK cascade deletes child MSSQL rows in Phase 3)
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM cases WHERE id = ?", case_id)
        conn.commit()
        return {"ok": True, "message": f"Case '{case['name']}' deleted."}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Module-level bootstrap
# ---------------------------------------------------------------------------
init_cases_table()
