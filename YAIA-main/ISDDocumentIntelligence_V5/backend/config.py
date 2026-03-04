import os
from dotenv import load_dotenv

load_dotenv()

# ── JWT Authentication ────────────────────────────────────────────────────────
# Set JWT_SECRET_KEY in .env — must be a long random string for production
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-production-use-a-long-random-string")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
PDF_MODEL = os.getenv("PDF_MODEL", "llama3.1:8b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")

CHROMA_PATH = os.getenv("CHROMA_PATH", "chroma_db")

# Whisper STT (local, offline)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")

# RAG Accuracy: Hybrid Search, Multi-Query, Re-ranking
ENABLE_HYBRID_SEARCH = os.getenv("ENABLE_HYBRID_SEARCH", "true").lower() == "true"
ENABLE_MULTI_QUERY = os.getenv("ENABLE_MULTI_QUERY", "true").lower() == "true"
ENABLE_RERANKING = os.getenv("ENABLE_RERANKING", "true").lower() == "true"

# LLM-powered document parser (Docling + Ollama) — set false to use legacy heuristic parser
USE_LLM_PARSER = os.getenv("USE_LLM_PARSER", "true").lower() == "true"

# Max LLM calls for PDF field extraction (default 25 — enough for 84+ page documents)
MAX_LLM_CALLS_PDF = int(os.getenv("MAX_LLM_CALLS_PDF", "25"))

# ── SQL Server (MSSQL) ────────────────────────────────────────────────────────
MSSQL_SERVER = os.getenv("MSSQL_SERVER", r"localhost\SQLEXPRESS")
MSSQL_DATABASE = os.getenv("MSSQL_DATABASE", "ISDIntelligence")
MSSQL_DRIVER = os.getenv("MSSQL_DRIVER", "ODBC Driver 17 for SQL Server")
MSSQL_AUTH = os.getenv("MSSQL_AUTH", "windows")
MSSQL_USER = os.getenv("MSSQL_USER", "")
MSSQL_PASSWORD = os.getenv("MSSQL_PASSWORD", "")

# ── Neo4j Graph Database ──────────────────────────────────────────────────────
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

if MSSQL_AUTH.lower() == "windows":
    MSSQL_CONNECTION_STRING = (
        f"DRIVER={{{MSSQL_DRIVER}}};"
        f"SERVER={MSSQL_SERVER};"
        f"DATABASE={MSSQL_DATABASE};"
        f"Trusted_Connection=yes;"
        f"TrustServerCertificate=yes;"
    )
else:
    MSSQL_CONNECTION_STRING = (
        f"DRIVER={{{MSSQL_DRIVER}}};"
        f"SERVER={MSSQL_SERVER};"
        f"DATABASE={MSSQL_DATABASE};"
        f"UID={MSSQL_USER};"
        f"PWD={MSSQL_PASSWORD};"
        f"TrustServerCertificate=yes;"
    )
