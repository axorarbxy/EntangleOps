from __future__ import annotations
import re,secrets
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp,Message,Receive,Scope,Send
_RID=re.compile(r"^[A-Za-z0-9_-]{8,64}$")
class _TooLarge(Exception):pass
class BodySizeLimitMiddleware:
    def __init__(self,app:ASGIApp,max_bytes:int)->None:self.app=app;self.max_bytes=max_bytes
    async def __call__(self,scope:Scope,receive:Receive,send:Send)->None:
        if scope["type"]!="http":return await self.app(scope,receive,send)
        headers=dict(scope["headers"]);cl=headers.get(b"content-length")
        if cl is not None:
            try:
                if int(cl)>self.max_bytes:return await self._reject(send,413,b'{"error":"payload_too_large"}')
            except ValueError:return await self._reject(send,400,b'{"error":"bad_content_length"}')
        received=0;started=False
        async def limited()->Message:
            nonlocal received
            msg=await receive()
            if msg["type"]=="http.request":
                received+=len(msg.get("body",b""))
                if received>self.max_bytes:raise _TooLarge()
            return msg
        async def tracking(msg:Message)->None:
            nonlocal started
            if msg["type"]=="http.response.start":started=True
            await send(msg)
        try:await self.app(scope,limited,tracking)
        except _TooLarge:
            if not started:await self._reject(send,413,b'{"error":"payload_too_large"}')
    @staticmethod
    async def _reject(send:Send,status:int,body:bytes)->None:
        await send({"type":"http.response.start","status":status,"headers":[(b"content-type",b"application/json"),(b"content-length",str(len(body)).encode())]});await send({"type":"http.response.body","body":body})
class SecurityHeadersMiddleware:
    def __init__(self,app:ASGIApp,hsts:bool)->None:self.app=app;self.hsts=hsts
    async def __call__(self,scope:Scope,receive:Receive,send:Send)->None:
        if scope["type"]!="http":return await self.app(scope,receive,send)
        async def wrapped(msg:Message)->None:
            if msg["type"]=="http.response.start":
                h=MutableHeaders(scope=msg);h["X-Content-Type-Options"]="nosniff";h["X-Frame-Options"]="DENY";h["Referrer-Policy"]="no-referrer";h["Cross-Origin-Resource-Policy"]="same-site";h["Permissions-Policy"]="geolocation=(), camera=(), microphone=()"
                if not scope["path"].startswith(("/docs","/redoc","/openapi.json")):h["Content-Security-Policy"]="default-src 'none'; frame-ancestors 'none'";h["Cache-Control"]="no-store"
                if self.hsts:h["Strict-Transport-Security"]="max-age=31536000; includeSubDomains"
            await send(msg)
        await self.app(scope,receive,wrapped)
class RequestIdMiddleware:
    def __init__(self,app:ASGIApp)->None:self.app=app
    async def __call__(self,scope:Scope,receive:Receive,send:Send)->None:
        if scope["type"]!="http":return await self.app(scope,receive,send)
        incoming=dict(scope["headers"]).get(b"x-request-id",b"").decode("latin-1");rid=incoming if _RID.fullmatch(incoming) else secrets.token_urlsafe(9);scope.setdefault("state",{})["request_id"]=rid
        async def wrapped(msg:Message)->None:
            if msg["type"]=="http.response.start":MutableHeaders(scope=msg)["X-Request-ID"]=rid
            await send(msg)
        await self.app(scope,receive,wrapped)
