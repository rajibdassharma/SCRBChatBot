import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DB_MODEL = os.getenv("DB_MODEL", "qwen2.5-coder:7b-instruct")
PDF_MODEL = os.getenv("PDF_MODEL", "llama3.1:8b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")


CHROMA_PATH = os.getenv("CHROMA_PATH", "chroma_db")

MSSQL_SERVER = os.getenv("MSSQL_SERVER", "localhost")
MSSQL_DATABASE = os.getenv("MSSQL_DATABASE", "")
MSSQL_DRIVER = os.getenv("MSSQL_DRIVER", "ODBC Driver 18 for SQL Server")

DB_MAX_ROWS = int(os.getenv("DB_MAX_ROWS", "200"))
SCHEMA_MAX_LINES = int(os.getenv("SCHEMA_MAX_LINES", "250"))
