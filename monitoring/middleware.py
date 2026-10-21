from __future__ import annotations
import logging,secrets,time
from starlette.requests import Request
from starlette.types import ASGIApp,Message,Receive,Scope,Send
from app.config import settings
from monitoring import metrics as M
from monitoring.logging_config import request_id_var
log=logging.getLogger("entangleops.access");_QUIET={"/metrics","/health/live","/health"}
def route_label(scope:Scope)->str:
    route=scope.get("route");path=getattr(route,"path_format",None) or getattr(route,"path",None)
    return path if isinstance(path,str) and path else "unmatched"
class MetricsMiddleware:
    def __init__(self,app:ASGIApp)->None:self.app=app
    async def __call__(self,scope:Scope,receive:Receive,send:Send)->None:
        if scope["type"]!="http":return await self.app(scope,receive,send)
        state=scope.setdefault("state",{});rid=state.get("request_id") or secrets.token_urlsafe(9);token=request_id_var.set(rid);start=time.perf_counter();status=500
        try:M.http_in_flight.inc()
        except Exception:logging.getLogger(__name__).exception("HTTP in-flight metric failed")
        async def send_wrapper(msg:Message)->None:
            nonlocal status
            if msg["type"]=="http.response.start":status=msg["status"]
            await send(msg)
        try:await self.app(scope,receive,send_wrapper)
        finally:
            duration=time.perf_counter()-start
            try:M.http_in_flight.dec()
            except Exception:logging.getLogger(__name__).exception("HTTP in-flight metric failed")
            try:
                method=M.bounded(scope.get("method",""),M.METHODS,"OTHER");route=route_label(scope);status_class=f"{status//100}xx" if 100<=status<=599 else "5xx"
                M.http_requests.labels(method,route,status_class).inc();M.http_duration.labels(method,route).observe(duration)
                if route not in _QUIET:self._access_log(scope,method,route,status,duration)
            except Exception:logging.getLogger(__name__).exception("metrics middleware failure")
            request_id_var.reset(token)
    @staticmethod
    def _access_log(scope:Scope,method:str,route:str,status:int,duration:float)->None:
        principal=scope.get("state",{}).get("principal")
        try:ip=scope["app"].state.client_ip(Request(scope))
        except Exception:
            client=scope.get("client");ip=client[0] if client and isinstance(client[0],str) else "unknown"
        level=logging.ERROR if status>=500 else logging.WARNING if duration>settings.slow_request_s else logging.INFO
        log.log(level,"request",extra={"fields":{"method":method,"route":route,"status":status,"duration_ms":round(duration*1000,1),"key_id":getattr(principal,"key_id",None),"role":getattr(principal,"role",None),"ip":ip,"slow":duration>settings.slow_request_s}})
