from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from pydantic import model_validator
from pathlib import Path
from typing import List

class Settings(BaseSettings):
    APP_NAME: str = "TangentCloud AI Bots API"
    OPENAI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    LLM_PROVIDER: str = "openai"  # "openai" or "gemini"
    ENV: str = "development"
    QDRANT_PATH: str = str(Path(__file__).resolve().parents[3] / "qdrant_db")
    # RAG tuning
    RAG_CHUNK_SIZE: int = 800
    RAG_CHUNK_OVERLAP: int = 120
    RAG_RETRIEVAL_K: int = 6
    RAG_RETRIEVAL_FETCH_K: int = 24
    RAG_RETRIEVAL_SCORE_THRESHOLD: float = 0.18
    
    # Database (default: local Postgres). Override via environment or .env.
    DATABASE_URL: str = "postgresql+psycopg://kamarajp@localhost:5432/tcsaasbot"

    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_BACKEND: str = "redis"

    # Portable infrastructure backends
    STORAGE_BACKEND: str = "local"
    QUEUE_BACKEND: str = "memory"
    SECRETS_BACKEND: str = "env"
    ARTIFACTS_DIR: str = str(Path(__file__).resolve().parents[3] / "artifacts")

    # Security
    SECRET_KEY: str = "TCSAASBOT_SUPER_SECRET_KEY_CHANGE_IN_PROD"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    JWT_ISSUER: str = "tangentcloud-api"
    JWT_AUDIENCE: str = "tangentcloud-dashboard"
    AUTH_PASSWORD: str = "password123"
    AUTH_REQUIRE_EXISTING_TENANT: bool = True
    DEMO_AUTH_PASSWORD: str = "password123"
    DEMO_TENANT_IDS: str = (
        "ops@tangentcloud.in,ops@dataflo.io,ops@adamsbridge.com,ops@workez.in"
    )
    ALLOW_API_KEY_AUTH: bool = False
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PRICE_PRO_ID: str = ""
    STRIPE_PRICE_ENT_ID: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    FRONTEND_URL: str = "http://localhost:9101"
    AGENT_TOOL_ALLOWLIST: str = "calculator,weather"
    CORS_ORIGINS: str = (
        "http://localhost:9101,http://localhost:3000,http://localhost:9100,"
        "http://localhost:9102,http://127.0.0.1:9101,http://127.0.0.1:3000,"
        "http://127.0.0.1:9100,http://127.0.0.1:9102"
    )
    MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT_RPM: int = 120
    RATE_LIMIT_PUBLIC_CHAT_RPM: int = 30
    RATE_LIMIT_AUTH_RPM: int = 15
    RATE_LIMIT_POLICY_CACHE_SECONDS: int = 60
    RATE_LIMIT_ALERT_DEFAULT_MIN_HITS: int = 5
    RATE_LIMIT_ALERT_DEFAULT_WINDOW_MINUTES: int = 60
    RATE_LIMIT_ALERT_DEFAULT_COOLDOWN_MINUTES: int = 60
    SUPPORT_EMAIL: str = "support@tangentcloud.in"
    SUPPORT_URL: str = "mailto:support@tangentcloud.in"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def demo_tenant_ids(self) -> List[str]:
        return [tenant.strip() for tenant in self.DEMO_TENANT_IDS.split(",") if tenant.strip()]

    @model_validator(mode="after")
    def validate_production_secrets(self):
        env = (self.ENV or "").strip().lower()
        is_production = env in {"production", "prod"}
        if not is_production:
            return self

        insecure_auth_password = self.AUTH_PASSWORD == "password123"
        insecure_secret_key = self.SECRET_KEY == "TCSAASBOT_SUPER_SECRET_KEY_CHANGE_IN_PROD"

        if insecure_auth_password or insecure_secret_key:
            raise ValueError(
                "Insecure auth configuration for production. "
                "Set strong AUTH_PASSWORD and SECRET_KEY values."
            )
        return self

@lru_cache
def get_settings():
    return Settings()
