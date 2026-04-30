"""Regression tests for CORS configuration.

The deploy on commit b5f2c54 broke every browser-driven write because the
staging container had no `CORS_ORIGINS` env var and the default in
`config.py` was `"http://localhost:3000"` only. Browser preflights from
the deployed web FQDN got HTTP 400, the actual POST never fired, and the
user saw a 503-equivalent fetch failure. These tests pin the defaults to
include the deployed origins and prove the middleware approves their
preflights.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.security import add_security_middleware, parse_cors_origins


def _client_with_cors(origins: str) -> TestClient:
    settings = Settings(cors_origins=origins, rate_limit_enabled=False)
    app = FastAPI()
    add_security_middleware(app, settings)

    @app.post("/echo")
    def _echo() -> dict:
        return {"ok": True}

    return TestClient(app)


def test_default_cors_origins_include_deployed_web_fqdns() -> None:
    settings = get_settings()
    origins = parse_cors_origins(settings.cors_origins)
    assert "https://mc-web.lemonplant-e20984ee.canadacentral.azurecontainerapps.io" in origins
    assert "https://mc-web-staging.lemonplant-e20984ee.canadacentral.azurecontainerapps.io" in origins
    assert "http://localhost:3000" in origins


def test_preflight_from_configured_origin_succeeds() -> None:
    client = _client_with_cors(
        "https://mc-web-staging.lemonplant-e20984ee.canadacentral.azurecontainerapps.io"
    )
    res = client.options(
        "/echo",
        headers={
            "Origin": "https://mc-web-staging.lemonplant-e20984ee.canadacentral.azurecontainerapps.io",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert res.status_code == 200
    assert (
        res.headers.get("access-control-allow-origin")
        == "https://mc-web-staging.lemonplant-e20984ee.canadacentral.azurecontainerapps.io"
    )
    assert "POST" in res.headers.get("access-control-allow-methods", "")


def test_preflight_from_unconfigured_origin_is_rejected() -> None:
    client = _client_with_cors("https://other.example.com")
    res = client.options(
        "/echo",
        headers={
            "Origin": "https://malicious.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    # Starlette CORS middleware returns 400 for disallowed origins.
    assert res.status_code == 400
    assert "access-control-allow-origin" not in res.headers


def test_post_with_configured_origin_returns_allow_origin_header() -> None:
    """A real (non-preflight) POST also needs the allow-origin response
    header so the browser will accept the response body."""
    origin = "http://localhost:3000"
    client = _client_with_cors(origin)
    res = client.post("/echo", json={"x": 1}, headers={"Origin": origin})
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == origin


# ─── Latent-bug guard: explicit headers list ────────────────────────────
# When allow_credentials=True browsers refuse "*" wildcards on methods or
# headers, so the middleware must spell each one out. The next four tests
# pin the contract so a future refactor cannot silently drop a header and
# break browser POSTs without anyone noticing in the smoke checks.

def _preflight(client: TestClient, *, request_headers: str) -> object:
    return client.options(
        "/echo",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": request_headers,
        },
    )


def test_options_preflight_returns_200_with_cors_headers() -> None:
    client = _client_with_cors("http://localhost:3000")
    res = _preflight(client, request_headers="Content-Type")
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert res.headers.get("access-control-max-age")


def test_options_preflight_includes_post_in_allow_methods() -> None:
    client = _client_with_cors("http://localhost:3000")
    res = _preflight(client, request_headers="Content-Type")
    methods = res.headers.get("access-control-allow-methods", "")
    for verb in ("GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"):
        assert verb in methods, f"{verb} missing from allow-methods: {methods}"


def test_options_preflight_includes_content_type_in_allow_headers() -> None:
    client = _client_with_cors("http://localhost:3000")
    res = _preflight(client, request_headers="Content-Type")
    headers = res.headers.get("access-control-allow-headers", "").lower()
    assert "content-type" in headers


def test_options_preflight_includes_authorization_in_allow_headers() -> None:
    """Future-proofing — the moment any route adds Bearer-token auth the
    browser will start sending Authorization on preflight; if it isn't
    in allow_headers the actual POST never fires."""
    client = _client_with_cors("http://localhost:3000")
    res = _preflight(client, request_headers="Authorization")
    headers = res.headers.get("access-control-allow-headers", "").lower()
    assert "authorization" in headers


def test_options_preflight_includes_idempotency_key_in_allow_headers() -> None:
    """Defense-in-depth for any future idempotent-write feature."""
    client = _client_with_cors("http://localhost:3000")
    res = _preflight(client, request_headers="X-Idempotency-Key")
    headers = res.headers.get("access-control-allow-headers", "").lower()
    assert "x-idempotency-key" in headers


# ─── OPTIONS catch-all: defense-in-depth against bare OPTIONS ───────────
# Without an Origin header, CORSMiddleware does not intercept and the
# request hits the route's method handler — which returns 405 because
# the underlying route doesn't declare OPTIONS. The catch-all in
# apps/api/app/main.py absorbs every such request and returns 200, so
# probes and tools that don't speak CORS no longer see a misleading 405.

def _client_with_real_app() -> TestClient:
    """Build a TestClient against the real app factory so we exercise the
    OPTIONS catch-all route registered in main.create_app."""
    from app.main import create_app

    return TestClient(create_app())


def test_options_without_origin_returns_200_at_root_path() -> None:
    client = _client_with_real_app()
    res = client.options("/")
    assert res.status_code == 200, (
        f"OPTIONS without Origin should be 200; got {res.status_code} "
        "— catch-all not registered or being shadowed"
    )


def test_options_without_origin_returns_200_at_tasks_endpoint() -> None:
    client = _client_with_real_app()
    res = client.options("/tasks")
    assert res.status_code == 200


def test_options_without_origin_returns_200_at_dynamic_path() -> None:
    client = _client_with_real_app()
    res = client.options("/tasks/123/recommendation")
    assert res.status_code == 200


def test_options_without_origin_returns_200_at_arbitrary_path() -> None:
    client = _client_with_real_app()
    res = client.options("/some/path/that/does/not/exist")
    assert res.status_code == 200


def test_options_with_origin_still_routes_through_cors_middleware() -> None:
    """The catch-all must NOT shadow CORSMiddleware's preflight handling.
    With a configured Origin and Access-Control-Request-* headers, the
    response must still carry the access-control-allow-* headers
    CORSMiddleware injects."""
    client = _client_with_real_app()
    res = client.options(
        "/tasks",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "POST" in res.headers.get("access-control-allow-methods", "")
