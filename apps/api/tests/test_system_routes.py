from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app
import app.api.routes as system_routes
from app.middleware import add_error_middleware


def test_health_endpoint_still_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_ready_when_db_check_passes(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(system_routes, "get_readiness", lambda _db: True)

    client = TestClient(app)
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_503_when_db_check_fails(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(system_routes, "get_readiness", lambda _db: False)

    client = TestClient(app)
    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "database not ready"}


def test_error_middleware_returns_500_for_unhandled_errors() -> None:
    test_app = FastAPI()
    add_error_middleware(test_app)

    @test_app.get("/boom")
    def boom() -> dict[str, str]:
        raise RuntimeError("boom")

    client = TestClient(test_app)
    response = client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {"detail": "internal server error"}
