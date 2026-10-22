from __future__ import annotations
from fastapi.testclient import TestClient
from app.main import create_app

def test_health_and_topology_routes():
    app=create_app()
    with TestClient(app) as client:
        assert client.get("/health").json()["status"]=="ok"
        key,_=app.state.keystore.create("viewer","viewer")
        assert len(client.get("/api/v1/topology?preset=tiny",headers={"X-API-Key":key}).json()["links"])==3

def test_me_returns_authenticated_principal():
    app=create_app()
    with TestClient(app) as client:
        key,record=app.state.keystore.create("viewer","viewer")
        response=client.get("/api/v1/me",headers={"X-API-Key":key})
        assert response.status_code==200
        assert response.json()=={"key_id":record.key_id,"name":"viewer","role":"viewer"}

def test_ml_registry_endpoints_are_viewer_readable():
    app=create_app()
    with TestClient(app) as client:
        key,_=app.state.keystore.create("ml viewer","viewer")
        headers={"X-API-Key":key}
        model=client.get("/api/v1/ml/model",headers=headers)
        experiments=client.get("/api/v1/ml/experiments",headers=headers)
        assert model.status_code==200
        assert model.json() is None or {"profile","feature_schema","horizon_steps","sha256"}.issubset(model.json())
        assert experiments.status_code==200
        assert isinstance(experiments.json(),list)
