from __future__ import annotations

from types import SimpleNamespace

from app.db.migrate import upgrade_to_head
from app.db.repos.runs import RunRepo
from app.db.session import make_engine, make_session_factory, resolve_url
from app.schemas import SimRequest
from app.services.runner import RunStore
from security.audit import AuditLog
from security.keys import KeyStore
from security.tickets import TicketService


def test_run_state_and_security_records_survive_engine_restart(tmp_path):
    db_url = resolve_url(f"sqlite:///{(tmp_path / 'entangleops.db').as_posix()}")
    engine = make_engine(db_url)
    upgrade_to_head(engine)
    sf = make_session_factory(engine)
    keys = KeyStore(sf, "k" * 40)
    key, record = keys.create("integration", "operator")
    audit = AuditLog(sf)
    audit.event("test.persist", key_id=record.key_id, ticket="never-store")
    tickets = TicketService("t" * 40, 30, sf)
    ticket = tickets.issue(record.key_id, "run-example-123")
    assert tickets.redeem(ticket, "run-example-123") == record.key_id
    assert tickets.redeem(ticket, "run-example-123") is None

    repo = RunRepo(sf)
    store = RunStore(repo, sf)
    run_id = store.create_run(SimRequest(duration_hours=1, dt_s=600, topology_preset="tiny"), record.key_id)
    assert run_id and repo.set_running(run_id)
    step = {"step": 0, "t_s": 0, "active": 0, "arrivals": 0, "admitted": 0,
            "blocked": 0, "reroutes": 0, "mean_fidelity": None, "useful_rate_pairs_s": 0.0,
            "raw_rate_pairs_s": 0.0, "sla_violations": 0, "links": {}, "allocations": []}
    assert repo.finish_ok(run_id, [step], {"sla_satisfied_pairs": 0.0, "violation_fraction": 0.0})
    engine.dispose()

    restarted_engine = make_engine(db_url)
    restarted_sf = make_session_factory(restarted_engine)
    restarted_repo = RunRepo(restarted_sf)
    principal = SimpleNamespace(key_id=record.key_id, role="operator")
    stored = restarted_repo.get_for(principal, run_id)
    assert stored["status"] == "done"
    assert restarted_repo.read_steps(run_id, -1) == [step]
    assert KeyStore(restarted_sf, "k" * 40).verify(key) is not None
    assert AuditLog.verify_chain(restarted_sf) == (True, 1, None)
    restarted_engine.dispose()
