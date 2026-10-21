from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.db.session import resolve_url

url = resolve_url(settings.database_url.get_secret_value(), settings.database_password_file)
if url.get_backend_name() != "sqlite":
    raise SystemExit("EO_DATABASE_URL is not SQLite")
source = Path(url.database).expanduser().resolve()
if not source.is_file(): raise SystemExit("database file does not exist")
target_dir = Path("backups"); target_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
try: os.chmod(target_dir, 0o700)
except OSError: pass
target = target_dir / f"entangleops-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.db"
with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
    src.backup(dst)
try: os.chmod(target, 0o600)
except OSError: pass
print(target)
