from __future__ import annotations
from dataclasses import dataclass
from fastapi import Depends,HTTPException,Request
from fastapi.security import APIKeyHeader
from security.keys import ROLE_RANK

api_key_header=APIKeyHeader(name="X-API-Key",auto_error=False)
@dataclass(frozen=True)
class Principal:
    key_id:str;name:str;role:str
def _deny(request:Request,reason:str)->HTTPException:
    request.app.state.audit.event("auth.fail",ip=request.app.state.client_ip(request),reason=reason,path=request.url.path)
    return HTTPException(401,"Invalid or missing credentials",headers={"WWW-Authenticate":"ApiKey"})
async def get_principal(request:Request,key:str|None=Depends(api_key_header))->Principal:
    app=request.app;ip=app.state.client_ip(request)
    if not app.state.limiter_auth_fail.peek(ip):
        app.state.audit.event("auth.throttled",ip=ip);raise HTTPException(429,"Too many failed attempts",headers={"Retry-After":"60"})
    if not key:
        app.state.limiter_auth_fail.consume(ip);raise _deny(request,"missing_key")
    rec=app.state.keystore.verify(key)
    if rec is None:
        app.state.limiter_auth_fail.consume(ip);raise _deny(request,"invalid_key")
    if not app.state.limiter_key.consume(rec.key_id):
        app.state.audit.event("ratelimit.key",key_id=rec.key_id,path=request.url.path);raise HTTPException(429,"Rate limit exceeded",headers={"Retry-After":"30"})
    request.state.principal=Principal(rec.key_id,rec.name,rec.role);return request.state.principal
def require_role(minimum:str):
    async def dependency(principal:Principal=Depends(get_principal))->Principal:
        if ROLE_RANK[principal.role]<ROLE_RANK[minimum]:raise HTTPException(403,"Insufficient role")
        return principal
    return dependency
