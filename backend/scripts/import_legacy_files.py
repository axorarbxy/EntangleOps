from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select, func
from app.config import settings
from app.db.jsonutil import to_jsonable
from app.db.models import ApiKey, AuditEntry, Run, RunStep
from app.db.runtime import open_database
from app.db.types import utcnow
from app.schemas import SimRequest
from security.audit import AuditLog, GENESIS

KEY_ID = re.compile(r"^[0-9a-f]{12}$")
RUN_ID = re.compile(r"^[A-Za-z0-9_-]{8,32}$")
STEP_FIELDS = ("step", "t_s", "active", "arrivals", "admitted", "blocked", "reroutes", "sla_violations", "mean_fidelity", "useful_rate_pairs_s", "raw_rate_pairs_s", "links", "allocations")


def dt(epoch): return datetime.fromtimestamp(float(epoch), timezone.utc) if epoch is not None else None


def main():
    parser = argparse.ArgumentParser(description="One-time additive import from the legacy JSON data directory")
    parser.add_argument("--data-dir", default=settings.data_dir)
    parser.add_argument("--owner-key-id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(); data = Path(args.data_dir)
    engine, sf = open_database(migrate_development=True)
    counts = {"imported": 0, "skipped": 0, "failed": 0}
    try:
        keys_file = data / "keys.json"
        with sf.begin() as s:
            raw_keys = json.loads(keys_file.read_text(encoding="utf-8")) if keys_file.exists() else {}
            for key_id, value in raw_keys.items():
                if not KEY_ID.fullmatch(key_id): counts["failed"] += 1; continue
                if s.get(ApiKey, key_id): counts["skipped"] += 1; continue
                if not args.dry_run:
                    s.add(ApiKey(key_id=key_id, name=value["name"], role=value["role"],
                        secret_hash=value["hash"], created_at=dt(value["created_at"]),
                        expires_at=dt(value.get("expires_at")), revoked_at=utcnow() if value.get("revoked") else None))
                counts["imported"] += 1

        audit_file = data / "audit.jsonl"
        if audit_file.exists():
            ok, _, error = AuditLog.verify_chain(audit_file)
            if not ok: raise SystemExit(f"Legacy audit chain is invalid; no audit entries imported: {error}")
            with sf.begin() as s:
                existing = s.scalar(select(func.count()).select_from(AuditEntry)) or 0
                if existing:
                    counts["skipped"] += len(audit_file.read_text(encoding="utf-8").splitlines())
                else:
                    for line in audit_file.read_text(encoding="utf-8").splitlines():
                        if not line.strip(): continue
                        item = json.loads(line); claimed = item.pop("hash")
                        canonical = json.dumps(item, sort_keys=True, separators=(",", ":"))
                        if not args.dry_run:
                            kid=item.get("key_id")
                            s.add(AuditEntry(ts=float(item["ts"]),kind=item["kind"],key_id=kid if isinstance(kid,str) and KEY_ID.fullmatch(kid) else None,
                                             body=canonical,prev=item["prev"],hash=claimed))
                        counts["imported"] += 1

        runs_dir = data / "runs"
        owner_default = args.owner_key_id
        for path in sorted(runs_dir.glob("*.json")) if runs_dir.exists() else []:
            rid = path.stem
            if not RUN_ID.fullmatch(rid): counts["skipped"] += 1; continue
            try: item = json.loads(path.read_text(encoding="utf-8"))
            except Exception: counts["failed"] += 1; continue
            owner = item.get("owner") or item.get("owner_key_id") or owner_default
            if not owner:
                print(f"skip {rid}: no owner key id")
                counts["skipped"] += 1; continue
            with sf.begin() as s:
                if s.get(Run, rid): counts["skipped"] += 1; continue
                if s.get(ApiKey, owner) is None: counts["failed"] += 1; print(f"skip {rid}: owner key does not exist"); continue
                config = item.get("config", {})
                if hasattr(config, "model_dump"): config=config.model_dump(mode="json")
                config = SimRequest.model_validate(config); records=item.get("records", [])
                status=item.get("status", "error"); summary=item.get("summary")
                error=item.get("error")
                if status not in ("done", "error") or (status == "done" and not summary): status="error";error="interrupted"
                if status == "error": error=error if error in ("timeout","internal","interrupted") else "internal"
                created=item.get("created_at")
                try: created_at=datetime.fromisoformat(created) if isinstance(created,str) else utcnow()
                except ValueError: created_at=utcnow()
                if not args.dry_run:
                    s.add(Run(id=rid,owner_key_id=owner,status=status,policy=config.policy,topology_preset=config.topology_preset,
                        seed=config.seed,duration_hours=config.duration_hours,dt_s=config.dt_s,n_steps=max(1,len(records) or int(config.duration_hours*3600/config.dt_s)),
                        config=to_jsonable(config.model_dump(mode="json")),summary=to_jsonable(summary) if status=="done" else None,
                        error=error if status=="error" else None,created_at=created_at,finished_at=utcnow() if status in ("done","error") else None))
                    if status=="done":
                        for start in range(0,len(records),500):
                            rows=[]
                            for row in records[start:start+500]: rows.append({"run_id":rid,**{k:row[k] for k in STEP_FIELDS}})
                            if rows:s.execute(RunStep.__table__.insert(),rows)
                counts["imported"] += 1
        print(json.dumps(counts, sort_keys=True))
        if not args.dry_run and counts["imported"]:
            AuditLog(sf).event("db.import", imported=counts["imported"], skipped=counts["skipped"], failed=counts["failed"])
    finally: engine.dispose()


if __name__ == "__main__": main()
