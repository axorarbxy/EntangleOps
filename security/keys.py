from __future__ import annotations
import hashlib,hmac,json,secrets,threading,time
from dataclasses import asdict,dataclass
from pathlib import Path

ROLES=("viewer","operator","admin");ROLE_RANK={"viewer":1,"operator":2,"admin":3}
@dataclass
class KeyRecord:
    key_id:str;name:str;role:str;hash:str;created_at:float;expires_at:float|None=None;revoked:bool=False
def _digest(pepper:bytes,secret:str)->str:return hmac.new(pepper,secret.encode(),hashlib.sha256).hexdigest()
class KeyStore:
    def __init__(self,path:str|Path,pepper:str)->None:
        self.path=Path(path);self.pepper=pepper.encode();self._lock=threading.Lock();self._keys:dict[str,KeyRecord]={};self._load()
    def _load(self)->None:
        if self.path.exists():
            raw=json.loads(self.path.read_text(encoding="utf-8"));self._keys={k:KeyRecord(**v) for k,v in raw.items()}
    def _save(self)->None:
        self.path.parent.mkdir(parents=True,exist_ok=True);tmp=self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({k:asdict(v) for k,v in self._keys.items()},indent=2),encoding="utf-8");tmp.chmod(0o600);tmp.replace(self.path);self.path.chmod(0o600)
    def create(self,name:str,role:str,ttl_days:float|None=None)->tuple[str,KeyRecord]:
        if role not in ROLES:raise ValueError("invalid role")
        if not name or len(name)>64:raise ValueError("name must be 1..64 chars")
        if ttl_days is not None and ttl_days<=0:raise ValueError("ttl_days must be positive")
        key_id=secrets.token_hex(6);secret=secrets.token_urlsafe(32);now=time.time();rec=KeyRecord(key_id,name,role,_digest(self.pepper,secret),now,now+ttl_days*86400 if ttl_days else None)
        with self._lock:self._keys[key_id]=rec;self._save()
        return f"eo_{key_id}.{secret}",rec
    def verify(self,presented:str)->KeyRecord|None:
        try:
            prefix,secret=presented.split(".",1)
            if not prefix.startswith("eo_") or len(presented)>200:raise ValueError
            kid=prefix[3:]
        except ValueError:
            hmac.compare_digest("0"*64,_digest(self.pepper,"x"));return None
        with self._lock:rec=self._keys.get(kid)
        valid=hmac.compare_digest(rec.hash if rec else "0"*64,_digest(self.pepper,secret))
        if not valid or rec is None or rec.revoked or (rec.expires_at is not None and time.time()>rec.expires_at):return None
        return rec
    def revoke(self,key_id:str)->bool:
        with self._lock:
            rec=self._keys.get(key_id)
            if not rec:return False
            rec.revoked=True;self._save();return True
    def list(self)->list[KeyRecord]:
        with self._lock:return list(self._keys.values())
    def get(self,key_id:str)->KeyRecord|None:
        with self._lock:
            r=self._keys.get(key_id)
            if r is None or r.revoked or (r.expires_at is not None and time.time()>r.expires_at):return None
            return r
