from __future__ import annotations
import os
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EO_",
        env_file=os.environ.get("EO_SETTINGS_FILE", ".env"),
        extra="ignore",
    )
    app_name: str = "EntangleOps"
    data_dir: str = "./data"
    model_path: str = "./data/predictor.joblib"
    default_seed: int = 42
    default_dt_s: int = 60
    default_duration_h: float = 24.0
    forecast_horizon_steps: int = 5
    safety_margin: float = 0.01
    k_paths: int = 4
    enable_sequence: bool = False
    cors_origins: list[str] = ["*"]
    env: str = "development"
    api_key_pepper: str = ""
    model_signing_key: str = ""
    keys_path: str = "./data/keys.json"
    audit_path: str = "./data/audit.jsonl"
    enable_docs: bool = True
    behind_tls: bool = False
    trusted_proxy_count: int = 0
    max_body_bytes: int = 65536
    ws_ticket_ttl_s: int = 30
    ws_allowed_origins: list[str] = []
    rate_per_key_per_min: int = 120
    rate_per_ip_per_min: int = 240
    rate_auth_fail_per_ip_per_min: int = 10
    max_concurrent_runs: int = 2
    max_queued_runs: int = 10
    max_runs_per_key_active: int = 3
    max_stored_runs: int = 200
    run_timeout_s: int = 120
    max_ws_per_key: int = 3
    max_steps_per_run: int = 5760
    max_expected_requests_per_run: int = 20000
    metrics_enabled: bool = True
    metrics_token: str = ""
    log_level: str = "INFO"
    log_json: bool = True
    slow_request_s: float = 2.0
    drift_sample_every_steps: int = 10
    drift_ewma_alpha: float = 0.05
    audit_verify_interval_s: int = 300
    loop_lag_interval_s: float = 0.5
    otel_enabled: bool = False
    otel_endpoint: str = ""
    database_url: SecretStr = SecretStr("sqlite:///./data/entangleops.db")
    database_password_file: str = ""
    migration_database_url: SecretStr = SecretStr("")
    migration_password_file: str = ""
    allow_sqlite_in_production: bool = False
    db_auto_migrate: bool = True
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_timeout_s: int = 10
    db_pool_recycle_s: int = 1800
    db_statement_timeout_ms: int = 5000
    db_echo: bool = False
    key_cache_ttl_s: float = 5.0
    run_lease_s: int = 60
    db_maintenance_interval_s: int = 30
    max_stored_benchmarks: int = 200
    ml_models_dir: str = "./data/models"
    ml_risk_alpha: float = 0.10
    ml_prediction_cache_rows: int = 50_000
    ml_psi_window_rows: int = 2000
    ml_psi_min_rows: int = 500

class ScenarioConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    traffic_base: Annotated[float, Field(ge=0, le=1)] = 0.45
    traffic_amp: Annotated[float, Field(ge=0, le=.5)] = 0.30
    traffic_peak_hour: Annotated[float, Field(ge=0, lt=24)] = 20.0
    traffic_spike_count: Annotated[int, Field(ge=0, le=20)] = 4
    traffic_spike_height: Annotated[float, Field(ge=0, le=.6)] = 0.30
    temp_mean_c: Annotated[float, Field(ge=-30, le=45)] = 18.0
    temp_amp_c: Annotated[float, Field(ge=0, le=20)] = 8.0
    temp_peak_hour: Annotated[float, Field(ge=0, lt=24)] = 15.0
    wind_base_ms: Annotated[float, Field(ge=0, le=20)] = 3.0
    storm_enabled: bool = True
    storm_center_h: Annotated[float, Field(ge=0, le=48)] = 15.0
    storm_duration_h: Annotated[float, Field(gt=0, le=12)] = 3.0
    storm_wind_peak_ms: Annotated[float, Field(ge=0, le=45)] = 18.0
    storm_temp_drop_c: Annotated[float, Field(ge=0, le=20)] = 6.0
    arrival_rate_per_step: Annotated[float, Field(ge=0, le=2)] = 0.25
    min_fidelity_choices: Annotated[list[Annotated[float,Field(ge=.5,le=.999)]],Field(min_length=1,max_length=8)] = [0.80, 0.85, 0.88]
    min_fidelity_weights: Annotated[list[Annotated[float,Field(ge=0,le=1)]],Field(min_length=1,max_length=8)] = [0.4, 0.4, 0.2]
    demand_choices_pairs_s: Annotated[list[Annotated[float,Field(gt=0,le=1000)]],Field(min_length=1,max_length=8)] = [20.0, 50.0, 100.0, 200.0]
    mean_duration_steps: Annotated[float, Field(ge=1, le=500)] = 20.0

    @model_validator(mode="after")
    def _check_weights(self) -> ScenarioConfig:
        if len(self.min_fidelity_choices) != len(self.min_fidelity_weights) or not self.min_fidelity_weights or sum(self.min_fidelity_weights) <= 0:
            raise ValueError("min fidelity choices and weights must have equal nonzero length and positive total weight")
        return self

settings = Settings()
