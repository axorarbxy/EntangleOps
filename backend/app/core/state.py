from __future__ import annotations
from dataclasses import dataclass
from app.core.physics import LinkParams
from app.core.requests_gen import EntRequest

@dataclass
class Allocation:
    request:EntRequest;path:list[str];link_ids:list[str];bands:list[str];start_step:int;reroutes:int=0

class NetworkState:
    def __init__(self,links:dict[str,LinkParams]):self.links=links;self._active:dict[int,Allocation]={};self._used={k:0 for k in links}
    def free_channels(self,link_id:str)->int:return self.links[link_id].channels-self._used[link_id]
    def can_reserve(self,link_ids:list[str])->bool:
        counts={}
        for lid in link_ids:counts[lid]=counts.get(lid,0)+1
        return all(self.free_channels(k)>=v for k,v in counts.items())
    def reserve(self,alloc:Allocation)->None:
        if alloc.request.id in self._active:raise ValueError("request already allocated")
        if not self.can_reserve(alloc.link_ids):raise ValueError("no channel capacity")
        for lid in alloc.link_ids:self._used[lid]+=1
        self._active[alloc.request.id]=alloc
    def release(self,request_id:int)->Allocation|None:
        a=self._active.pop(request_id,None)
        if a:
            for lid in a.link_ids:self._used[lid]-=1
        return a
    def active(self)->dict[int,Allocation]:return dict(self._active)
    def utilization(self)->dict[str,float]:return {k:self._used[k]/v.channels for k,v in self.links.items()}
