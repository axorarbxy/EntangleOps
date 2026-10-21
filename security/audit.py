from __future__ import annotations

import hashlib, json, logging, threading, time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.instrument import db_timer
from app.db.models import AuditEntry
from security.netutil import sanitize

GENESIS = "0" * 64
_REDACT = {"key", "api_key", "secret", "ticket", "authorization", "pepper", "signing_key", "hash"}
_KEY_ID = __import__("re").compile(r"^[0-9a-f]{12}$")
log = logging.getLogger(__name__)


class AuditLog:
    """Append-only audit service. The application supplies a DB sessionmaker."""
    def __init__(self, store):
        self._db = not isinstance(store, (str, Path)); self._sf = store if self._db else None
        self.path = None if self._db else Path(store)
        self._lock = threading.Lock(); self._listeners = []
        if not self._db:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._last = self._recover_last_hash()

    def add_listener(self, listener): self._listeners.append(listener)

    def _recover_last_hash(self):
        if not self.path.exists(): return GENESIS
        last = GENESIS
        with self.path.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip(): last = json.loads(line)["hash"]
        return last

    @staticmethod
    def _clean(kind, fields):
        clean = {k: ("[redacted]" if k.lower() in _REDACT else sanitize(v)) for k, v in fields.items()}
        return {"ts": round(time.time(), 3), "kind": sanitize(kind, 64), **clean}, clean

    def event(self, kind: str, **fields: object) -> None:
        body, clean = self._clean(kind, fields)
        if self._db:
            for _ in range(6):
                try:
                    with self._lock, db_timer("audit_append"), self._sf.begin() as s:
                        prev = s.scalar(select(AuditEntry.hash).order_by(AuditEntry.seq.desc()).limit(1)) or GENESIS
                        item = dict(body, prev=prev)
                        canonical = json.dumps(item, sort_keys=True, separators=(",", ":"))
                        digest = hashlib.sha256((prev + canonical).encode("utf-8")).hexdigest()
                        kid = item.get("key_id")
                        s.add(AuditEntry(ts=item["ts"], kind=item["kind"], key_id=kid if isinstance(kid, str) and _KEY_ID.fullmatch(kid) else None,
                                         body=canonical, prev=prev, hash=digest))
                    break
                except IntegrityError:
                    continue
                except Exception:
                    log.exception("audit write failed")
                    try:
                        from monitoring.metrics import audit_write_failures
                        audit_write_failures.inc()
                    except Exception: pass
                    return
            else:
                log.error("audit write gave up after retries")
                return
        else:
            with self._lock:
                body["prev"] = self._last
                canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
                body["hash"] = hashlib.sha256((self._last + canonical).encode()).hexdigest()
                with self.path.open("a", encoding="utf-8") as stream: stream.write(json.dumps(body, sort_keys=True) + "\n")
                self.path.chmod(0o600); self._last = body["hash"]
        for listener in tuple(self._listeners):
            try: listener(kind, clean)
            except Exception: log.exception("Audit listener failed")

    def tail(self, limit: int = 100, before_seq: int | None = None):
        if self._db:
            from app.db.models import AuditEntry
            with db_timer("audit_read"), self._sf() as s:
                q = select(AuditEntry)
                if before_seq is not None: q = q.where(AuditEntry.seq < before_seq)
                rows = list(s.scalars(q.order_by(AuditEntry.seq.desc()).limit(limit)))
            rows.reverse()
            result = []
            for row in rows:
                body = json.loads(row.body); body["seq"] = row.seq; body["hash"] = row.hash; result.append(body)
            return result
        if not self.path.exists(): return []
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines() if x.strip()][-limit:]

    def entries(self, limit: int = 100): return self.tail(limit)

    @staticmethod
    def verify_chain(source):
        if not isinstance(source, (str, Path)):
            with db_timer("audit_read"), source() as s:
                rows = list(s.scalars(select(AuditEntry).order_by(AuditEntry.seq)))
            prev = GENESIS
            for row in rows:
                if row.prev != prev: return False, row.seq, f"broken link at seq {row.seq}"
                try: body = json.loads(row.body)
                except ValueError: return False, row.seq, f"invalid body at seq {row.seq}"
                if body.get("prev") != prev: return False, row.seq, f"broken link at seq {row.seq}"
                if hashlib.sha256((prev + row.body).encode()).hexdigest() != row.hash: return False, row.seq, f"hash mismatch at seq {row.seq}"
                if body.get("kind") != row.kind or body.get("ts") != row.ts: return False, row.seq, f"column/body mismatch at seq {row.seq}"
                prev = row.hash
            return True, len(rows), None
        prev = GENESIS; path = Path(source)
        if not path.exists(): return True, 0, None
        for n, line in enumerate(x for x in path.read_text(encoding="utf-8").splitlines() if x.strip()):
            rec = json.loads(line); claimed = rec.pop("hash", None)
            if rec.get("prev") != prev: return False, n, f"broken link at entry {n}"
            canonical = json.dumps(rec, sort_keys=True, separators=(",", ":"))
            if hashlib.sha256((prev + canonical).encode()).hexdigest() != claimed: return False, n, f"hash mismatch at entry {n}"
            prev = claimed
        return True, n + 1 if 'n' in locals() else 0, None

    @staticmethod
    def verify_chain_from(session_factory, after_seq: int, prev: str, batch: int = 1000):
        last_seq = after_seq; last_hash = prev; checked = 0; batch_size = min(5000, max(1, batch))
        while True:
            with db_timer("audit_read"), session_factory() as s:
                rows = list(s.scalars(select(AuditEntry).where(AuditEntry.seq > last_seq)
                    .order_by(AuditEntry.seq).limit(batch_size)))
            if not rows: return True, checked, None, last_seq, last_hash
            for row in rows:
                if row.prev != last_hash: return False, checked, f"broken link at seq {row.seq}", last_seq, last_hash
                try: body = json.loads(row.body)
                except ValueError: return False, checked, f"invalid body at seq {row.seq}", last_seq, last_hash
                if body.get("prev") != last_hash: return False, checked, f"broken link at seq {row.seq}", last_seq, last_hash
                if hashlib.sha256((last_hash + row.body).encode()).hexdigest() != row.hash:
                    return False, checked, f"hash mismatch at seq {row.seq}", last_seq, last_hash
                if body.get("kind") != row.kind or body.get("ts") != row.ts:
                    return False, checked, f"column/body mismatch at seq {row.seq}", last_seq, last_hash
                last_seq = row.seq; last_hash = row.hash; checked += 1
            if len(rows) < batch_size: return True, checked, None, last_seq, last_hash
