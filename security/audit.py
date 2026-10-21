from __future__ import annotations
import hashlib,json,threading,time,logging
from pathlib import Path
from security.netutil import sanitize
GENESIS="0"*64
_REDACT={"key","api_key","secret","ticket","authorization","pepper","signing_key","hash"}
class AuditLog:
    def __init__(self,path:str|Path)->None:
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self._lock=threading.Lock();self._last=self._recover_last_hash();self._listeners=[]
    def add_listener(self,listener)->None:self._listeners.append(listener)
    def _recover_last_hash(self)->str:
        if not self.path.exists():return GENESIS
        last=GENESIS
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():last=json.loads(line)["hash"]
        return last
    def event(self,kind:str,**fields:object)->None:
        clean={k:("[redacted]" if k.lower() in _REDACT else sanitize(v)) for k,v in fields.items()};body={"ts":round(time.time(),3),"kind":sanitize(kind,64),**clean}
        with self._lock:
            body["prev"]=self._last;canonical=json.dumps(body,sort_keys=True,separators=(",",":"));body["hash"]=hashlib.sha256((self._last+canonical).encode()).hexdigest()
            with self.path.open("a",encoding="utf-8") as f:f.write(json.dumps(body,sort_keys=True)+"\n")
            self.path.chmod(0o600);self._last=body["hash"]
        for listener in tuple(self._listeners):
            try:listener(kind,clean)
            except Exception:logging.getLogger(__name__).exception("Audit listener failed")
    def entries(self,limit:int=100)->list[dict]:
        if not self.path.exists():return []
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines() if x.strip()][-limit:]
    @staticmethod
    def verify_chain(path:str|Path)->tuple[bool,int,str|None]:
        prev=GENESIS;p=Path(path)
        if not p.exists():return True,0,None
        for n,line in enumerate((x for x in p.read_text(encoding="utf-8").splitlines() if x.strip())):
            rec=json.loads(line);claimed=rec.pop("hash",None)
            if rec.get("prev")!=prev:return False,n,f"broken link at entry {n}"
            canonical=json.dumps(rec,sort_keys=True,separators=(",",":"))
            if hashlib.sha256((prev+canonical).encode()).hexdigest()!=claimed:return False,n,f"hash mismatch at entry {n}"
            prev=claimed
        return True,n+1 if 'n' in locals() else 0,None
