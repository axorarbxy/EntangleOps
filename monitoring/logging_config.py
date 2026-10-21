from __future__ import annotations
import json,logging,re,sys,time
from contextvars import ContextVar
request_id_var:ContextVar[str]=ContextVar("request_id",default="-")
_KEY=re.compile(r"eo_[0-9a-f]{12}\.[A-Za-z0-9_\-]{20,}");_MAX=2000
def _scrub(value:object)->object:return _KEY.sub("eo_[redacted]",value) if isinstance(value,str) else value
class SecretRedactFilter(logging.Filter):
    def filter(self,record:logging.LogRecord)->bool:
        record.msg=_scrub(record.getMessage());record.args=None;fields=getattr(record,"fields",None)
        if isinstance(fields,dict):record.fields={k:_scrub(v) for k,v in fields.items()}
        return True
class JsonFormatter(logging.Formatter):
    def format(self,record:logging.LogRecord)->str:
        payload={"ts":time.strftime("%Y-%m-%dT%H:%M:%S",time.gmtime(record.created))+f".{int(record.msecs):03d}Z","level":record.levelname,"logger":record.name,"msg":str(record.msg)[:_MAX],"request_id":request_id_var.get()}
        fields=getattr(record,"fields",None)
        if isinstance(fields,dict):payload.update({k:v for k,v in fields.items() if k not in payload})
        if record.exc_info:payload["exc"]=self.formatException(record.exc_info)[:_MAX*2]
        return json.dumps(payload,default=str)
class RequestIdFilter(logging.Filter):
    def filter(self,record:logging.LogRecord)->bool:record.request_id=request_id_var.get();return True
def configure_logging(level:str="INFO",as_json:bool=True)->None:
    root=logging.getLogger();root.handlers.clear();root.setLevel(level.upper());handler=logging.StreamHandler(sys.stdout);handler.addFilter(SecretRedactFilter())
    if as_json:handler.setFormatter(JsonFormatter())
    else:handler.addFilter(RequestIdFilter());handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"))
    root.addHandler(handler)
    for name in ("uvicorn","uvicorn.error"):
        logger=logging.getLogger(name);logger.handlers.clear();logger.propagate=True
    logging.getLogger("uvicorn.access").disabled=True
