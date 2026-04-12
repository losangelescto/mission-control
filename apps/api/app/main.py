import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router as system_router
from app.config import get_settings
from app.logging_setup import configure_logging
from app.middleware import add_error_middleware
from app.security import add_security_middleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    logger.info(
        "mission_control startup (phase 1 POC feature flags)",
        extra={
            "event": "startup_flags",
            "context": {
                "use_fixture_mailbox": s.use_fixture_mailbox,
                "use_graph_mailbox": s.use_graph_mailbox,
                "enable_live_canon_sync": s.enable_live_canon_sync,
                "enable_teams_call_connector": s.enable_teams_call_connector,
                "enable_outbound_rollups": s.enable_outbound_rollups,
            },
        },
    )
    if s.enable_live_canon_sync:
        logger.warning(
            "ENABLE_LIVE_CANON_SYNC is true: automated external canon sync is not implemented in Phase 1",
            extra={"event": "live_canon_sync_not_implemented"},
        )
    yield


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    app = FastAPI(title="Mission Control API", lifespan=lifespan)
    add_security_middleware(app, settings)
    add_error_middleware(app)
    app.include_router(system_router)
    return app


app = create_app()
