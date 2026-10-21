from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import settings
from security.audit import AuditLog
from app.db.runtime import open_database

def main()->None:
    engine,sf=open_database(migrate_development=True)
    try:
        ok,count,error=AuditLog.verify_chain(sf)
        print(f"{'OK' if ok else 'FAIL'}: checked {count} entries"+(f" ({error})" if error else ""))
        if not ok:sys.exit(1)
    finally:engine.dispose()
if __name__=="__main__":main()
