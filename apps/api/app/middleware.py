import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def add_error_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def handle_exceptions(request: Request, call_next):  # type: ignore[no-untyped-def]
        try:
            return await call_next(request)
        except Exception:  # noqa: BLE001
            logger.exception("unhandled request error", extra={"path": request.url.path})
            return JSONResponse(status_code=500, content={"detail": "internal server error"})
