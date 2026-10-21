from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import settings
from security.audit import AuditLog

def main()->None:
    ok,count,error=AuditLog.verify_chain(settings.audit_path)
    print(f"{'OK' if ok else 'FAIL'}: checked {count} entries"+(f" ({error})" if error else ""))
    if not ok:sys.exit(1)
if __name__=="__main__":main()
