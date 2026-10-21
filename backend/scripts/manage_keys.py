from __future__ import annotations
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import settings
from security.audit import AuditLog
from security.keys import KeyStore,ROLES

def main()->None:
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest="cmd",required=True)
    c=sub.add_parser("create");c.add_argument("--name",required=True);c.add_argument("--role",choices=ROLES,required=True);c.add_argument("--ttl-days",type=float)
    sub.add_parser("list");r=sub.add_parser("revoke");r.add_argument("--key-id",required=True)
    args=ap.parse_args()
    if not settings.api_key_pepper and settings.env=="production":raise SystemExit("EO_API_KEY_PEPPER is required in production")
    store=KeyStore(settings.keys_path,settings.api_key_pepper or "development-only-pepper");audit=AuditLog(settings.audit_path)
    if args.cmd=="create":
        key,rec=store.create(args.name,args.role,args.ttl_days);audit.event("key.create",key_id=rec.key_id,role=rec.role);print("Save this API key now; it is shown only once:");print(key)
    elif args.cmd=="list":
        print("key_id       name                         role       created               expires               revoked")
        for k in store.list():print(f"{k.key_id:12s} {k.name[:28]:28s} {k.role:10s} {k.created_at:.0f} {k.expires_at or '-'} {k.revoked}")
    elif args.cmd=="revoke":
        if not store.revoke(args.key_id):raise SystemExit("key not found")
        audit.event("key.revoke",key_id=args.key_id);print("Key revoked")
if __name__=="__main__":main()
