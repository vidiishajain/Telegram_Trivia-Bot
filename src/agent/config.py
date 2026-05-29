"""Application configuration, loaded from environment variables (and `.env`).

We use `pydantic-settings` so configuration is *typed* and *validated at startup*.
If a required variable like OPENROUTER_API_KEY is missing, the program stops
immediately with a clear error — instead of breaking mysteriously later on.

Two complementary tools, on purpose:
  - `load_dotenv()` reads `.env` into the real environment (`os.environ`). This is
    what third-party libraries that read env vars directly need — e.g. `fal_client`
    looks for `FAL_KEY` in the environment on its own.
  - `Settings` (below) gives *our* code typed, validated, autocompleted access.

Usage anywhere in the code:

    from agent.config import get_settings
    settings = get_settings()
    print(settings.llm_model)
"""

from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Populate os.environ from .env as early as possible, for libraries that read it.
load_dotenv()


class Settings(BaseSettings):
    """All configuration for this project, in one validated place."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM (required) -----------------------------------------------------
    # Get a key at https://openrouter.ai/keys
    openrouter_api_key: str = Field(description="Your OpenRouter API key.")
    # Which model each tier maps to lives in code — see agent/services/llm.py.

    # --- Logging ------------------------------------------------------------
    # How chatty the logs are: DEBUG, INFO, WARNING, ERROR.
    log_level: str = Field(default="INFO", description="Logging verbosity.")

    # --- Web app gate (optional) --------------------------------------------
    # If set, web demos require this password before showing anything. Leave unset
    # for local development; set it for anything you deploy publicly.
    app_password: str | None = Field(default=None, description="Password for deployed web apps.")

    # --- Media: fal.ai (optional) -------------------------------------------
    # Get a key at https://fal.ai/dashboard/keys. Needed for the media service.
    fal_key: str | None = Field(default=None, description="fal.ai API key (FAL_KEY).")

    # --- Storage: Cloudflare R2 / S3 (optional) -----------------------------
    # From your R2 dashboard. Needed for the storage service.
    r2_account_id: str | None = Field(default=None, description="Cloudflare account id.")
    r2_access_key_id: str | None = Field(default=None, description="R2 access key id.")
    r2_secret_access_key: str | None = Field(default=None, description="R2 secret access key.")
    r2_bucket: str | None = Field(default=None, description="R2 bucket name.")
    # If the bucket is shared, this prefix scopes everything you store into your
    # own slice of it (e.g. "student07"). The storage service adds/strips it for you.
    r2_prefix: str = Field(
        default="", description="Key prefix that scopes your slice of the bucket."
    )
    # Public/custom domain for the bucket (e.g. https://files.example.com). When
    # set, storage.public_url() builds stable, non-expiring links for your files.
    r2_public_base_url: str | None = Field(
        default=None, description="Public base URL (custom domain) for the bucket."
    )

    # --- Database: Neon Postgres (optional) ---------------------------------
    # Neon gives you an async-ready Postgres URL (postgresql://...).
    database_url: str | None = Field(
        default=None,
        description="Neon Postgres connection string. Needed for the db service.",
    )


@lru_cache
def get_settings() -> Settings:
    """Return the settings, loaded once and cached.

    Always call this instead of constructing `Settings()` yourself, so the
    `.env` file is read a single time.
    """
    # pydantic-settings fills required fields from the environment at runtime,
    # which the type checker can't see — hence the ignore on this one line.
    return Settings()  # pyright: ignore[reportCallIssue]
