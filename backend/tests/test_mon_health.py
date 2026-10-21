from fastapi.testclient import TestClient
from app.main import create_app

def test_public_health_routes():
    c=TestClient(create_app())
    assert c.get("/health/live").status_code==200
    assert c.get("/health").status_code==200
    assert c.get("/health/ready").status_code in (200,503)
