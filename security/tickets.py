from __future__ import annotations
import hashlib,hmac,secrets,threading,time
class TicketService:
    def __init__(self,secret:str,ttl_s:int)->None:
        self._key=hmac.new(secret.encode(),b"ws-ticket-v1",hashlib.sha256).digest();self.ttl_s=ttl_s;self._used:dict[str,float]={};self._lock=threading.Lock()
    def _sign(self,payload:str)->str:return hmac.new(self._key,payload.encode(),hashlib.sha256).hexdigest()
    def issue(self,key_id:str,run_id:str)->str:
        exp=int(time.time())+self.ttl_s;nonce=secrets.token_urlsafe(9);payload=f"{key_id}|{run_id}|{exp}|{nonce}";return f"{payload}|{self._sign(payload)}"
    def redeem(self,ticket:str,run_id:str)->str|None:
        try:key_id,t_run,exp_s,nonce,sig=ticket.split("|");exp=int(exp_s)
        except (ValueError,AttributeError):return None
        payload=f"{key_id}|{t_run}|{exp_s}|{nonce}"
        if not hmac.compare_digest(sig,self._sign(payload)) or t_run!=run_id or time.time()>exp:return None
        with self._lock:
            now=time.time();self._used={n:e for n,e in self._used.items() if e>now}
            if nonce in self._used:return None
            self._used[nonce]=exp
        return key_id
