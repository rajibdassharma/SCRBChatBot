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
TRANSLATE_MODEL = os.getenv("TRANSLATE_MODEL", "translategemma:12b")

CHROMA_PATH_SMAC = os.getenv("CHROMA_PATH_SMAC", "chroma_db_smac_v6")
CHROMA_PATH_IR = os.getenv("CHROMA_PATH_IR", "chroma_db_ir_v6")

# Whisper STT (local, offline)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")

# RAG Accuracy: Hybrid Search, Multi-Query, Re-ranking
ENABLE_HYBRID_SEARCH = os.getenv("ENABLE_HYBRID_SEARCH", "true").lower() == "true"
ENABLE_MULTI_QUERY = os.getenv("ENABLE_MULTI_QUERY", "true").lower() == "true"
ENABLE_RERANKING = os.getenv("ENABLE_RERANKING", "true").lower() == "true"

# LLM-powered document parser (Docling + Ollama) — per collection
USE_LLM_PARSER_SMAC = os.getenv("USE_LLM_PARSER_SMAC", "false").lower() == "true"
USE_LLM_PARSER_IR = os.getenv("USE_LLM_PARSER_IR", "true").lower() == "true"

# Embedding method: true = Ollama HTTP API, false = sentence-transformers direct GPU
USE_OLLAMA_EMBEDDINGS = os.getenv("USE_OLLAMA_EMBEDDINGS", "true").lower() == "true"

# Max LLM calls for PDF field extraction (default 25 — enough for 84+ page documents)
MAX_LLM_CALLS_PDF = int(os.getenv("MAX_LLM_CALLS_PDF", "25"))

# ── MySQL ────────────────────────────────────────────────────────────────────
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "ISDIntelligence")
