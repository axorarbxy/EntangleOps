from __future__ import annotations
from fastapi.testclient import TestClient
from app.main import create_app

def test_health_and_topology_routes():
    app=create_app()
    with TestClient(app) as client:
        assert client.get("/health").json()["status"]=="ok"
        key,_=app.state.keystore.create("viewer","viewer")
        assert len(client.get("/api/v1/topology?preset=tiny",headers={"X-API-Key":key}).json()["links"])==3
