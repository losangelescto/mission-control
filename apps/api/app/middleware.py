import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.request_context import clear_request_id, set_request_id

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"

# Health probes hit the API every few seconds; skip logging them to keep
# the log volume focused on real traffic.
_SILENT_PATHS = {"/health", "/ready", "/info"}


def add_error_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context_and_logging(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid4())
        set_request_id(request_id)
        start = time.perf_counter()
        path = request.url.path
        method = request.method

        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.exception(
                "unhandled request error",
                extra={
                    "method": method,
                    "path": path,
                    "duration_ms": duration_ms,
                    "status_code": 500,
                },
            )
            clear_request_id()
            return JSONResponse(
                status_code=500,
                content={"detail": "internal server error", "request_id": request_id},
                headers={REQUEST_ID_HEADER: request_id},
            )

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        if path not in _SILENT_PATHS:
            logger.info(
                "request",
                extra={
                    "method": method,
                    "path": path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
        response.headers[REQUEST_ID_HEADER] = request_id
        clear_request_id()
        return response
