import json
import logging
from monitoring.logging_config import JsonFormatter,SecretRedactFilter

def test_log_formatter_is_json_and_redacts_api_keys():
    record=logging.LogRecord("test",logging.INFO,"",1,"key eo_0123456789ab.abcdefghijklmnopqrstuvwxyz",(),None)
    SecretRedactFilter().filter(record)
    payload=json.loads(JsonFormatter().format(record))
    assert "eo_[redacted]" in payload["msg"]
