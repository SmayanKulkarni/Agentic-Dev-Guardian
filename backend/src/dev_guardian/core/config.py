"""
Pydantic Configuration Models for Agentic Dev Guardian.

Architecture Blueprint Reference: Phase 1 — Core Python Package.
All environment variables and runtime settings are validated through
Pydantic BaseSettings, loading from `backend/.env`.
"""

from pydantic_settings import BaseSettings


class GuardianSettings(BaseSettings):
    """
    Central configuration loaded from the backend/.env file.

    Attributes:
        groq_api_key: API key for Groq LLM inference provider.
        langfuse_public_key: Public key for Langfuse LLMOps tracing.
        langfuse_secret_key: Secret key for Langfuse LLMOps tracing.
        langfuse_host: Langfuse server host URL.
        default_language: Default programming language for AST parsing.
    """

    groq_api_key: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    default_language: str = "python"

    # Phase 2: Database connections
    memgraph_host: str = "127.0.0.1"
    memgraph_port: int = 7687
    qdrant_host: str = "127.0.0.1"
    qdrant_port: int = 6333
    embedding_model: str = "jinaai/jina-embeddings-v2-base-code"

    class Config:
        env_file = "backend/.env"
        env_file_encoding = "utf-8"
        case_sensitive = False


def get_settings() -> GuardianSettings:
    """Return a validated GuardianSettings instance."""
    return GuardianSettings()
