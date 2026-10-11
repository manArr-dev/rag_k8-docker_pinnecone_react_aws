from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "production"] = "production"
    log_level: str = "INFO"
    # Comma-separated origins. Empty means same-origin only (the default
    # deployment serves the UI and proxies /api from one host).
    cors_origins: str = ""

    # Ingestion and deletion require this key in the X-API-Key header. When it
    # is unset those endpoints are only open in development.
    admin_api_key: SecretStr | None = None
    max_upload_mb: int = 20

    # Generation. ANTHROPIC_API_KEY is read from the environment by the SDK.
    llm_model: str = "claude-opus-5-5"
    llm_max_tokens: int = 64000
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    # Re-run a request the model's safety classifiers decline on a fallback
    # model, server-side. Claude API only; turn off on Bedrock/Vertex/Foundry.
    llm_refusal_fallback: bool = True
    max_history_messages: int = 12

    pinecone_api_key: SecretStr | None = None
    pinecone_index: str = "rag-documents"
    pinecone_namespace: str = "default"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"
    pinecone_create_index: bool = True

    # PyTorch models. The Docker image bakes these two in and runs offline, so
    # changing them means rebuilding with the matching build args.
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_pooling: Literal["cls", "mean"] = "cls"
    embedding_query_prefix: str = "Represent this sentence for searching relevant passages: "
    embedding_batch_size: int = 32
    reranker_enabled: bool = True
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    torch_num_threads: int | None = None

    retrieval_top_k: int = 20
    rerank_top_n: int = 5
    chunk_size: int = 1200
    chunk_overlap: int = 200

    @model_validator(mode="after")
    def _check_chunking(self) -> "Settings":
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("chunk_overlap must be >= 0 and smaller than chunk_size")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
