from __future__ import annotations
import re
from fastapi import Request
_CTRL=re.compile(r"[\x00-\x1f\x7f]")
def sanitize(value:object,max_len:int=200)->str:return _CTRL.sub("?",str(value))[:max_len]
def make_client_ip(trusted_proxy_count:int):
    def client_ip(request:Request)->str:
        if trusted_proxy_count>0:
            parts=[p.strip() for p in request.headers.get("x-forwarded-for","").split(",") if p.strip()]
            if len(parts)>=trusted_proxy_count:return sanitize(parts[-trusted_proxy_count],64)
        return sanitize(request.client.host if request.client else "unknown",64)
    return client_ip
