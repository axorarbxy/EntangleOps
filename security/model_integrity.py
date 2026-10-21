from __future__ import annotations
import hashlib,hmac
from pathlib import Path
def _mac(key:str,data:bytes)->str:return hmac.new(key.encode(),data,hashlib.sha256).hexdigest()
def sign_file(path:str|Path,key:str)->Path:
    p=Path(path);sig=p.with_suffix(p.suffix+".sig");sig.write_text(_mac(key,p.read_bytes()),encoding="ascii");sig.chmod(0o600);p.chmod(0o600);return sig
def verify_file(path:str|Path,key:str)->bool:
    p=Path(path);sig=p.with_suffix(p.suffix+".sig")
    if not key or not p.exists() or not sig.exists():return False
    try:return hmac.compare_digest(sig.read_text(encoding="ascii").strip(),_mac(key,p.read_bytes()))
    except (OSError,UnicodeError):return False
