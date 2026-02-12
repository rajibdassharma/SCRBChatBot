import re
from sqlalchemy import create_engine, text
from config import MSSQL_SERVER, MSSQL_DATABASE, MSSQL_DRIVER, DB_MAX_ROWS, SCHEMA_MAX_LINES

# -------------------------------
# DB CONNECTION (Windows Auth)
# -------------------------------

def get_engine():
    conn_str = (
        f"mssql+pyodbc://@{MSSQL_SERVER}/{MSSQL_DATABASE}"
        f"?driver={MSSQL_DRIVER.replace(' ', '+')}"
        f"&Trusted_Connection=yes"
        f"&Encrypt=yes"
        f"&TrustServerCertificate=yes"
    )
    return create_engine(conn_str)

# -------------------------------
# SCHEMA FETCH (bounded)
# -------------------------------

def fetch_schema() -> str:
    sql = """
    SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE
    FROM INFORMATION_SCHEMA.COLUMNS
    ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
    """
    lines = []
    with get_engine().connect() as conn:
        rows = conn.execute(text(sql)).fetchall()
        for schema, table, col, dtype in rows:
            lines.append(f"{schema}.{table}.{col} ({dtype})")

    # Bound schema to keep prompt small
    return "\n".join(lines[:SCHEMA_MAX_LINES])

# -------------------------------
# SQL CLEANING + VALIDATION
# -------------------------------

def clean_sql(llm_output: str) -> str:
    s = (llm_output or "").strip()

    # Remove markdown fences ```sql ... ```
    s = re.sub(r"^```(?:sql)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```$", "", s)

    # If LLM returned JSON, try to pull value of "sql"
    # (works even if there is extra text around it)
    m_json = re.search(r'"sql"\s*:\s*"(.+?)"\s*}', s, flags=re.DOTALL)
    if m_json:
        s = m_json.group(1)

    # Convert escaped newlines/quotes if present
    s = s.replace("\\n", " ").replace('\\"', '"')

    # Extract from first SELECT onward (ignore any prose)
    m = re.search(r"(?is)\bselect\b.*", s)
    if m:
        s = m.group(0).strip()

    # Remove SQL comments
    s = re.sub(r"--.*?$", "", s, flags=re.MULTILINE)
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)

    # Strip trailing semicolons
    s = s.rstrip().rstrip(";").strip()

    # IMPORTANT: strip common trailing JSON artifacts
    # e.g. ... " }  or  }  or  " 
    s = re.sub(r'["\}\]]+\s*$', "", s).strip()

    # Normalize whitespace
    s = re.sub(r"\s+", " ", s).strip()

    return s


def validate_safe_select(sql: str):
    """
    Generic safety rules: SELECT only, single statement, no dangerous keywords.
    Returns (ok, reason)
    """
    if not sql:
        return False, "Empty SQL"

    if not re.match(r"(?is)^select\b", sql):
        return False, "Not a SELECT query"

    # No multi-statements
    if ";" in sql:
        return False, "Multiple statements detected"

    # Block dangerous keywords incl. USE
    banned = [
        "insert", "update", "delete", "drop", "alter", "truncate",
        "exec", "execute", "merge", "create", "grant", "revoke", "use"
    ]
    for b in banned:
        if re.search(rf"(?i)\b{b}\b", sql):
            return False, f"Blocked keyword: {b}"

    return True, "OK"

# -------------------------------
# SQL EXECUTION (bounded rows)
# -------------------------------

def run_sql(sql: str):
    with get_engine().connect() as conn:
        result = conn.execute(text(sql))
        cols = list(result.keys())
        rows = result.fetchmany(DB_MAX_ROWS)
        return {"columns": cols, "rows": [list(r) for r in rows]}
