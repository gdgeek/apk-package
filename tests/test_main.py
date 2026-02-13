"""Tests for app/main.py - CORS, global exception handler, health check."""

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthCheck:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestCORS:
    def test_cors_headers_present(self, client):
        resp = client.options(
            "/health",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # CORS middleware should respond with an allow-origin header
        assert "access-control-allow-origin" in resp.headers


class TestGlobalExceptionHandler:
    def test_unhandled_exception_returns_internal_error(self):
        """Add a temporary route that raises, verify unified error format."""
        test_router = APIRouter()

        @test_router.get("/_test_error")
        async def _raise():
            raise RuntimeError("boom")

        app.include_router(test_router)
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/_test_error")
            assert resp.status_code == 500
            body = resp.json()
            assert body["error"]["code"] == "INTERNAL_ERROR"
            assert "boom" in body["error"]["message"]
            assert body["error"]["details"] == {}
        finally:
            # Clean up the temporary route
            app.routes[:] = [r for r in app.routes if getattr(r, "path", "") != "/_test_error"]
