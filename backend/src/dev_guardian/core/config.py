"""
Pydantic Configuration Models for Agentic Dev Guardian.

Configuration contract (ticket 06):

  * **Environment variables are the primary channel.** An MCP client
    (Cursor, Claude Desktop, Windsurf) spawns `dev-guardian serve` with its own
    `env` block, so anything Guardian needs must be settable that way.
  * Every setting accepts a `GUARDIAN_`-prefixed name — unambiguous inside a
    shared IDE environment — and keeps its unprefixed vendor name
    (`GROQ_API_KEY`, `ANTHROPIC_API_KEY`, ...) so an existing shell profile
    keeps working.
  * Dotenv files are a convenience, not the source of truth. They are read in
    ascending priority: the user-level file first, then the repo-local ones,
    so a checkout can override a global default. Real environment variables
    beat every file.
  * **Nothing is written by Guardian.** `dev-guardian mcp-config` emits the
    JSON block for the user to paste; there is no secret store to manage,
    corrupt, or leak.
  * Global vs per-project: credentials and provider choice are global
    (user-level env or dotenv). The indexed repository is per-invocation — it
    is a CLI argument or `GUARDIAN_REPO`, never a setting — and its graph and
    vector stores live inside it, under `.guardian/`.
"""

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings

# User-level config, valid for an installed copy that has no checkout around
# it. Honours XDG_CONFIG_HOME implicitly via the conventional path.
USER_CONFIG_DIR = Path.home() / ".config" / "guardian"
USER_ENV_FILE = USER_CONFIG_DIR / ".env"

# Lowest priority first — pydantic-settings lets later files override earlier.
_ENV_FILES = (str(USER_ENV_FILE), "backend/.env", ".env")


def _alias(*names: str) -> AliasChoices:
    return AliasChoices(*names)


class GuardianSettings(BaseSettings):
    """
    Central configuration, resolved from environment then dotenv files.

    Attributes:
        groq_api_key: API key for Groq LLM inference provider.
        langfuse_public_key: Public key for Langfuse LLMOps tracing.
        langfuse_secret_key: Secret key for Langfuse LLMOps tracing.
        langfuse_host: Langfuse server host URL.
        default_language: Default programming language for AST parsing.
        embedding_model: fastembed model used for code embeddings.
    """

    groq_api_key: str = Field(
        default="", validation_alias=_alias("GUARDIAN_GROQ_API_KEY", "GROQ_API_KEY")
    )
    langfuse_public_key: str = Field(
        default="",
        validation_alias=_alias("GUARDIAN_LANGFUSE_PUBLIC_KEY", "LANGFUSE_PUBLIC_KEY"),
    )
    langfuse_secret_key: str = Field(
        default="",
        validation_alias=_alias("GUARDIAN_LANGFUSE_SECRET_KEY", "LANGFUSE_SECRET_KEY"),
    )
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com",
        validation_alias=_alias("GUARDIAN_LANGFUSE_HOST", "LANGFUSE_HOST"),
    )
    default_language: str = Field(
        default="python",
        validation_alias=_alias("GUARDIAN_DEFAULT_LANGUAGE", "DEFAULT_LANGUAGE"),
    )

    embedding_model: str = Field(
        default="jinaai/jina-embeddings-v2-base-code",
        validation_alias=_alias("GUARDIAN_EMBEDDING_MODEL", "EMBEDDING_MODEL"),
    )

    class Config:
        env_file = _ENV_FILES
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


def get_settings() -> GuardianSettings:
    """Return a validated GuardianSettings instance."""
    return GuardianSettings()
