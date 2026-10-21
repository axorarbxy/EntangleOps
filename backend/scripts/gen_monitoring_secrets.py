from __future__ import annotations

import argparse
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "monitoring" / "secrets" / "metrics_token"

def main() -> None:
    parser = argparse.ArgumentParser(description="Create the Prometheus scrape token")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    DEST.parent.mkdir(parents=True, exist_ok=True)
    if DEST.exists() and not args.force:
        parser.error(f"{DEST} already exists; use --force to replace it")
    token = secrets.token_hex(32)
    DEST.write_text(token, encoding="ascii")
    try: DEST.chmod(0o644)
    except OSError: pass
    print(f"Add this line to backend/.env: EO_METRICS_TOKEN={token}")

if __name__ == "__main__": main()
