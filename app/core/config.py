from pydantic import Field
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── Database (Aiven Postgres) ──
    DATABASE_URL: str = "postgresql+asyncpg://localhost/zorvyn"

    # ── Redis / Valkey (Aiven) ──
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_SSL_CA_CERTS: str = "ca.pem"  # path to Aiven CA cert for TLS (rediss://)

    # ── Kafka (Aiven) ──
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_SSL_CAFILE: str = ""
    KAFKA_SSL_CERTFILE: str = ""
    KAFKA_SSL_KEYFILE: str = ""

    # ── JWT ──
    JWT_SECRET_KEY: str = Field(...)  # required – no insecure default
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60

    # ── App ──
    DEBUG: bool = False
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:3030"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
