from monitoring import metrics
from monitoring.audit_hooks import on_audit_event

def test_audit_labels_are_bounded():
    before=metrics.audit_events.labels("other")._value.get()
    on_audit_event("attacker supplied kind",{"reason":"attacker supplied reason"})
    assert metrics.audit_events.labels("other")._value.get()==before+1
