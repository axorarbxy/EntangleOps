from __future__ import annotations
from typing import Annotated,Literal
from pydantic import BaseModel,ConfigDict,Field
from app.config import ScenarioConfig,settings

class SimRequest(BaseModel):
    model_config=ConfigDict(extra="forbid",allow_inf_nan=False)
    policy:Literal["static_c","static_o","adaptive"]="adaptive"
    seed:Annotated[int,Field(ge=0,le=2**31-1)]=settings.default_seed
    duration_hours:float=Field(settings.default_duration_h,gt=0,le=48)
    dt_s:int=Field(settings.default_dt_s,ge=15,le=600)
    topology_preset:Literal["metro","tiny"]="metro"
    scenario:ScenarioConfig=Field(default_factory=ScenarioConfig)
class BenchmarkRequest(BaseModel):
    model_config=ConfigDict(extra="forbid",allow_inf_nan=False)
    seed:Annotated[int,Field(ge=0,le=2**31-1)]=settings.default_seed;duration_hours:float=Field(settings.default_duration_h,gt=0,le=48);dt_s:int=Field(settings.default_dt_s,ge=15,le=600);topology_preset:Literal["metro","tiny"]="metro";scenario:ScenarioConfig=Field(default_factory=ScenarioConfig)
class PredictRequest(BaseModel):
    model_config=ConfigDict(extra="forbid",allow_inf_nan=False)
    length_km:float=Field(ge=.1,le=200);aerial_fraction:float=Field(ge=0,le=1);band:Literal["C","O"];traffic_now:float=Field(ge=0,le=1);traffic_trend:float=Field(ge=-1,le=1);temp_now:float=Field(ge=-40,le=60);dtemp_dt_now:float=Field(ge=-50,le=50);wind_now:float=Field(ge=0,le=60);wind_trend:float=Field(ge=-60,le=60);hour:float=Field(ge=0,le=24)
class WsTicketRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    run_id:str=Field(pattern=r"^[A-Za-z0-9_-]{8,32}$")
class RunStatus(BaseModel): id:str;status:str;created_at:str;error:str|None=None
class RunSummary(RunStatus): config:SimRequest;summary:dict|None=None
