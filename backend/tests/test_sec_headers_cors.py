from __future__ import annotations
from fastapi import FastAPI
from fastapi.testclient import TestClient
from security.middleware import RequestIdMiddleware,SecurityHeadersMiddleware

def test_security_headers_and_request_id():
    app=FastAPI();app.add_middleware(SecurityHeadersMiddleware,hsts=True);app.add_middleware(RequestIdMiddleware)
    @app.get("/")
    def home():return {"ok":True}
    with TestClient(app) as client:
        response=client.get("/",headers={"X-Request-ID":"valid_id-123"})
        assert response.headers["X-Request-ID"]=="valid_id-123"
        assert response.headers["X-Content-Type-Options"]=="nosniff"
        assert response.headers["Strict-Transport-Security"].startswith("max-age=")
