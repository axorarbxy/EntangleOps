from __future__ import annotations
from security.audit import AuditLog

def test_audit_chain_and_redaction(tmp_path):
    p=tmp_path/"audit.jsonl";log=AuditLog(p);log.event("test",ticket="do-not-store",note="line\nforged");log.event("second")
    ok,count,error=AuditLog.verify_chain(p)
    assert (ok,count,error)==(True,2,None)
    raw=p.read_text();assert "do-not-store" not in raw and "line?forged" in raw
    p.write_text(raw.replace("second","edited"));assert not AuditLog.verify_chain(p)[0]
