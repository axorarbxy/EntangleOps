from pathlib import Path
import secrets
import os

target = Path(__file__).resolve().parents[2] / "database" / "secrets"
target.mkdir(parents=True, exist_ok=True)
for name in ("db_admin_password", "db_owner_password", "db_app_password"):
    path = target / name
    if path.exists():
        raise SystemExit(f"Refusing to overwrite existing secret file: {name}")
    path.write_text(secrets.token_urlsafe(32), encoding="ascii")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
print("Generated database secret files with restrictive permissions.")
