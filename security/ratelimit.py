from __future__ import annotations
import threading,time

class TokenBucketLimiter:
    def __init__(self,per_minute:int,burst:int|None=None)->None:
        self.rate=per_minute/60.;self.capacity=float(burst if burst is not None else per_minute);self._buckets:dict[str,tuple[float,float]]={};self._lock=threading.Lock()
    def _refill(self,key:str,now:float)->float:
        tokens,last=self._buckets.get(key,(self.capacity,now));return min(self.capacity,tokens+(now-last)*self.rate)
    def peek(self,key:str)->bool:
        with self._lock:return self._refill(key,time.monotonic())>=1
    def consume(self,key:str,cost:float=1.)->bool:
        now=time.monotonic()
        with self._lock:
            tokens=self._refill(key,now);ok=tokens>=cost;self._buckets[key]=(tokens-cost if ok else tokens,now)
            if len(self._buckets)>10000:self._gc(now)
            return ok
    def _gc(self,now:float)->None:
        for k,(_,last) in list(self._buckets.items()):
            if now-last>600:self._buckets.pop(k,None)
