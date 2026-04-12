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
    cors_origins: str = "http://localhost:3000"

    # Rate limits. Format accepted by slowapi: "<count>/<period>"
    rate_limit_default: str = "100/minute"
    rate_limit_recommendation: str = "10/minute"
    rate_limit_enabled: bool = True

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
