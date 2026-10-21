from __future__ import annotations

import hashlib, hmac, json, secrets, threading, time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, update
from app.db.instrument import db_timer
from app.db.models import ApiKey
from app.db.types import utcnow

ROLES = ("viewer", "operator", "admin")
ROLE_RANK = {"viewer": 1, "operator": 2, "admin": 3}


@dataclass
class KeyRecord:
    key_id: str
    name: str
    role: str
    hash: str
    created_at: float
    expires_at: float | None = None
    revoked: bool = False


def _digest(pepper: bytes, secret: str) -> str:
    return hmac.new(pepper, secret.encode(), hashlib.sha256).hexdigest()


def _date(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc) if epoch is not None else None


def _record(row):
    return KeyRecord(row.key_id, row.name, row.role, row.secret_hash, row.created_at.timestamp(),
                     row.expires_at.timestamp() if row.expires_at else None, row.revoked_at is not None)


class KeyStore:
    """The application uses the sessionmaker path; path mode supports legacy unit fixtures."""
    def __init__(self, store, pepper: str, cache_ttl_s: float = 5.0) -> None:
        self.pepper = pepper.encode(); self._lock = threading.RLock()
        self._db = not isinstance(store, (str, Path)); self._sf = store if self._db else None
        self.path = Path(store) if not self._db else None
        self.cache_ttl_s = max(0, cache_ttl_s); self._cache = {}; self._last_used = {}; self._keys = {}
        if not self._db and self.path.exists():
            self._keys = {k: KeyRecord(**v) for k, v in json.loads(self.path.read_text(encoding="utf-8")).items()}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True); tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({k: asdict(v) for k, v in self._keys.items()}, indent=2), encoding="utf-8")
        tmp.chmod(0o600); tmp.replace(self.path); self.path.chmod(0o600)

    def create(self, name: str, role: str, ttl_days: float | None = None):
        if role not in ROLES: raise ValueError("invalid role")
        if not name or len(name) > 64: raise ValueError("name must be 1..64 chars")
        if ttl_days is not None and ttl_days <= 0: raise ValueError("ttl_days must be positive")
        key_id = secrets.token_hex(6); secret = secrets.token_urlsafe(32); now = time.time()
        expires = now + ttl_days * 86400 if ttl_days else None
        rec = KeyRecord(key_id, name, role, _digest(self.pepper, secret), now, expires)
        if self._db:
            with db_timer("key_write"), self._sf.begin() as s:
                s.add(ApiKey(key_id=key_id, name=name, role=role, secret_hash=rec.hash,
                             created_at=_date(now), expires_at=_date(expires)))
        else:
            with self._lock: self._keys[key_id] = rec; self._save()
        return f"eo_{key_id}.{secret}", rec

    def verify(self, presented: str, *, fresh: bool = False):
        try:
            prefix, secret = presented.split(".", 1)
            if not prefix.startswith("eo_") or len(presented) > 200: raise ValueError
            kid = prefix[3:]
        except ValueError:
            hmac.compare_digest("0" * 64, _digest(self.pepper, "x")); return None
        rec = None; now = time.monotonic()
        if self._db:
            with self._lock:
                entry = self._cache.get(kid)
                if not fresh and entry and now - entry[0] <= self.cache_ttl_s: rec = entry[1]
            if rec is None:
                with db_timer("key_read"), self._sf() as s:
                    row = s.scalar(select(ApiKey).where(ApiKey.key_id == kid))
                    rec = _record(row) if row else None
                if rec:
                    with self._lock:
                        if len(self._cache) >= 1024: self._cache.clear()
                        self._cache[kid] = (now, rec)
        else:
            with self._lock: rec = self._keys.get(kid)
        valid = hmac.compare_digest(rec.hash if rec else "0" * 64, _digest(self.pepper, secret))
        if not valid or rec is None or rec.revoked or (rec.expires_at is not None and time.time() > rec.expires_at): return None
        if self._db:
            with self._lock:
                if time.monotonic() - self._last_used.get(kid, 0) >= 60:
                    self._last_used[kid] = time.monotonic()
                    try:
                        with db_timer("key_write"), self._sf.begin() as s:
                            s.execute(update(ApiKey).where(ApiKey.key_id == kid).values(last_used_at=utcnow()))
                    except Exception:
                        import logging
                        logging.getLogger(__name__).exception("Key last-used update failed")
        return rec

    def revoke(self, key_id: str) -> bool:
        if self._db:
            with db_timer("key_write"), self._sf.begin() as s:
                result = s.execute(update(ApiKey).where(ApiKey.key_id == key_id, ApiKey.revoked_at.is_(None)).values(revoked_at=utcnow()))
            with self._lock: self._cache.pop(key_id, None)
            return result.rowcount == 1
        with self._lock:
            rec = self._keys.get(key_id)
            if not rec: return False
            rec.revoked = True; self._save(); return True

    def list(self):
        if self._db:
            with db_timer("key_read"), self._sf() as s: return [_record(r) for r in s.scalars(select(ApiKey).order_by(ApiKey.created_at))]
        with self._lock: return list(self._keys.values())

    def get(self, key_id: str, *, fresh: bool = False):
        if self._db:
            rec = None
            with self._lock:
                entry = self._cache.get(key_id)
                if not fresh and entry and time.monotonic() - entry[0] <= self.cache_ttl_s: rec = entry[1]
            if rec is None:
                with db_timer("key_read"), self._sf() as s:
                    row = s.scalar(select(ApiKey).where(ApiKey.key_id == key_id)); rec = _record(row) if row else None
                if rec:
                    with self._lock: self._cache[key_id] = (time.monotonic(), rec)
        else:
            with self._lock: rec = self._keys.get(key_id)
        if rec is None or rec.revoked or (rec.expires_at is not None and time.time() > rec.expires_at): return None
        return rec
