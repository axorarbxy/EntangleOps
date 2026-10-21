from __future__ import annotations
import pytest
from app.config import Settings
from security.validation import InsecureConfigError,enforce

def test_production_rejects_missing_secrets_and_wildcard_cors():
    with pytest.raises(InsecureConfigError):enforce(Settings(env="production"))
    enforce(Settings(env="production",api_key_pepper="p"*40,model_signing_key="s"*40,cors_origins=["https://dashboard.example"]))
