from fastapi.testclient import TestClient
from app.main import create_app
from app.config import settings

def test_metrics_endpoint_auth(monkeypatch):
    monkeypatch.setattr(settings,"metrics_token","test-token-which-is-long-enough-123456")
    c=TestClient(create_app())
    assert c.get("/metrics").status_code==401
    r=c.get("/metrics",headers={"Authorization":"Bearer test-token-which-is-long-enough-123456"})
    assert r.status_code==200 and "eo_http_requests_total" in r.text
    assert "/metrics" not in c.get("/openapi.json").text
