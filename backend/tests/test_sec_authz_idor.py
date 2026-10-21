from __future__ import annotations
from types import SimpleNamespace
from app.schemas import SimRequest
from app.services.runner import RunStore

def test_runs_are_owner_scoped_and_ids_unguessable():
    store=RunStore();rid=store.create_run(SimRequest(duration_hours=1,topology_preset="tiny"),"owner-a")
    owner=SimpleNamespace(key_id="owner-a",role="operator");other=SimpleNamespace(key_id="owner-b",role="operator");admin=SimpleNamespace(key_id="root",role="admin")
    assert len(rid)>=16 and store.get_for(owner,rid) is not None
    assert store.get_for(other,rid) is None and store.get_for(admin,rid) is not None
    assert store.list_for(other)==[]
