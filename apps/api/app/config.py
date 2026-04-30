from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    app_version: str = "dev"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = "postgresql://postgres:postgres@localhost:5432/mission_control"
    log_level: str = "INFO"
    sources_upload_dir: str = "data/uploads"

    # Comma-separated list of allowed origins for CORS. No wildcard in prod.
    # The deployed staging/prod web FQDNs are baked in as a safety net so
    # that a missing CORS_ORIGINS env var on the container does not silently
    # block every browser write (the symptom is a 400 on every preflight).
    cors_origins: str = (
        "http://localhost:3000,"
        "http://127.0.0.1:3000,"
        "https://mc-web.lemonplant-e20984ee.canadacentral.azurecontainerapps.io,"
        "https://mc-web-staging.lemonplant-e20984ee.canadacentral.azurecontainerapps.io"
    )

    # Rate limits. Format accepted by slowapi: "<count>/<period>"
    rate_limit_default: str = "100/minute"
    rate_limit_recommendation: str = "10/minute"
    rate_limit_enabled: bool = True

    # --- LLM provider ---
    # `mock` (default, deterministic, no network), `anthropic`, or `openai`.
    llm_provider: str = "mock"
    llm_api_key: str = ""
    llm_model: str = "claude-sonnet-4-6"
    llm_max_tokens: int = 1500
    llm_temperature: float = 0.3
    # How long a recommendation stays fresh before it may be regenerated.
    # Only honored if the task itself has not been modified since generation.
    recommendation_cache_seconds: int = 300

    # --- Transcription provider ---
    # `mock` (default, no network) or `whisper` (OpenAI Whisper API).
    transcription_provider: str = "mock"
    # API key for OpenAI Whisper. May be the same key as llm_api_key when both
    # providers are OpenAI; left separate so each can be rotated independently.
    whisper_api_key: str = ""
    whisper_model: str = "whisper-1"
    # Per-file safety cap. Files longer than this are rejected up front.
    max_audio_duration_seconds: int = 7200

    # --- Source processing ---
    # Per-batch timeout for chunked PDF page extraction. If a batch exceeds
    # this, the document is marked partial and processing moves on.
    pdf_batch_timeout_seconds: int = 60
    # Hard ceiling on the entire processing run for a single document.
    processing_overall_timeout_seconds: int = 1800

    # --- Task extraction ---
    # When true, source ingestion automatically runs candidate extraction
    # after text is in place. Canon documents are skipped regardless.
    auto_extract_tasks: bool = True
    # Candidates with confidence below this threshold are still saved but
    # tagged so the UI can hide them unless the operator opts in.
    extraction_confidence_threshold: float = 0.6
    # For long transcripts, split into windows of this many minutes and
    # extract per window. Set to 0 to disable windowing.
    extraction_window_minutes: int = 10

    # --- Phase 1 POC feature flags (handoff for live integrations) ---
    use_fixture_mailbox: bool = Field(
        default=True,
        description="Allow /mail/sync-fixture and fixture mailbox connector (local POC).",
    )
    use_graph_mailbox: bool = Field(
        default=False,
        description="Enable GraphMailboxConnectorStub when Graph credentials are set (no live Exchange).",
    )
    enable_live_canon_sync: bool = Field(
        default=False,
        description="Reserved for future automated canon sync from external systems (not implemented in Phase 1).",
    )
    enable_teams_call_connector: bool = Field(
        default=True,
        description="Allow call artifact upload and extract-actions (manual/stub; no live Teams connector).",
    )
    enable_outbound_rollups: bool = Field(
        default=False,
        description="Reserved for outbound roll-up delivery (email/Teams/chat); persistence always allowed.",
    )

    # Microsoft Graph (optional): stub only; requires USE_GRAPH_MAILBOX=true and all three set.
    microsoft_graph_tenant_id: str | None = None
    microsoft_graph_client_id: str | None = None
    microsoft_graph_client_secret: str | None = None

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
