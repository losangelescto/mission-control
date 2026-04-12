from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app
import app.api.routes as system_routes
from app.middleware import REQUEST_ID_HEADER, add_error_middleware


def test_health_endpoint_returns_ok_with_timestamp() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "timestamp" in body and body["timestamp"]


def test_info_endpoint_returns_version_environment_uptime() -> None:
    client = TestClient(app)
    response = client.get("/info")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"version", "environment", "uptime_seconds"}
    assert isinstance(body["uptime_seconds"], (int, float))
    assert body["uptime_seconds"] >= 0


def test_ready_returns_ready_when_db_check_passes(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(system_routes, "get_readiness", lambda _db: True)

    client = TestClient(app)
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "connected"}


def test_ready_returns_503_when_db_check_fails(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(system_routes, "get_readiness", lambda _db: False)

    client = TestClient(app)
    response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["detail"]["status"] == "not_ready"
    assert body["detail"]["database"] == "disconnected"


def test_error_middleware_returns_500_for_unhandled_errors() -> None:
    test_app = FastAPI()
    add_error_middleware(test_app)

    @test_app.get("/boom")
    def boom() -> dict[str, str]:
        raise RuntimeError("boom")

    client = TestClient(test_app)
    response = client.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "internal server error"
    # Middleware now attaches a request id to error responses so log
    # entries can be correlated to the client-visible error.
    assert "request_id" in body
    assert response.headers.get(REQUEST_ID_HEADER) == body["request_id"]


def test_request_id_round_trip_through_middleware() -> None:
    client = TestClient(app)
    response = client.get("/health", headers={REQUEST_ID_HEADER: "test-req-id"})
    assert response.status_code == 200
    assert response.headers.get(REQUEST_ID_HEADER) == "test-req-id"
