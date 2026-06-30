from urllib.parse import quote_plus

from pydantic_settings import BaseSettings


_DEFAULT_JWT_SECRET = "change-this-to-a-random-secret-in-production"
_JWT_MIN_LENGTH = 32


class Settings(BaseSettings):
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "cyber_fraud_dsr"
    JWT_SECRET: str = _DEFAULT_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60
    CORS_ORIGINS: str = "http://localhost:5173"
    DISABLE_DOCS: bool = False

    # Chat / LLM (Phase 1 — see /backend/chat/*)
    # CHAT_ENABLED gates the entire feature: when false the /api/v1/chat
    # router is not mounted and the sidebar link is hidden via the
    # /api/v1/features endpoint. Default false so prod stays inert until
    # the GPU box is provisioned and migration 005 is applied.
    CHAT_ENABLED: bool = False
    # Point at the Ollama instance reachable from the backend. Local dev =
    # localhost; production = the IP of the GPU box on KSWAN.
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5-coder:14b-instruct"

    class Config:
        env_prefix = "CFDSR_"
        env_file = ".env"

    @property
    def database_url(self) -> str:
        pwd = quote_plus(self.DB_PASSWORD)
        return (
            f"mysql+asyncmy://{self.DB_USER}:{pwd}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


settings = Settings()

# Fail-loud on a weak JWT secret. Previously this only printed a warning,
# which meant prod ran for weeks with the publicly-known default value —
# anyone with the source could forge admin tokens. Now the backend refuses
# to start unless CFDSR_JWT_SECRET is set and looks plausibly strong.
if settings.JWT_SECRET == _DEFAULT_JWT_SECRET:
    raise RuntimeError(
        "CFDSR_JWT_SECRET is using the public default value. "
        "Set it in .env to a strong random value before starting the backend. "
        "Generate one with:  openssl rand -hex 32"
    )
if len(settings.JWT_SECRET) < _JWT_MIN_LENGTH:
    raise RuntimeError(
        f"CFDSR_JWT_SECRET is too short ({len(settings.JWT_SECRET)} chars). "
        f"Minimum {_JWT_MIN_LENGTH} characters. "
        f"Generate a stronger one with:  openssl rand -hex 32"
    )
