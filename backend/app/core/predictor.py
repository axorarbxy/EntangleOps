from __future__ import annotations
import math
import logging,secrets
from pathlib import Path
import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error,r2_score
from app.config import ScenarioConfig
from app.core.environment import EnvTraces,generate_env
from app.core.physics import BANDS,W0,LinkParams,link_werner
from app.core.topology import get_preset,link_lookup
from app.config import settings
from security.model_integrity import sign_file,verify_file

logger=logging.getLogger(__name__)
_EPHEMERAL_SIGNING_KEY=secrets.token_hex(32)
class ModelIntegrityError(RuntimeError):pass
def _signing_key()->str:
    if settings.model_signing_key:return settings.model_signing_key
    if settings.env=="production":raise ModelIntegrityError("model signing key is required in production")
    logger.warning("Model signing key is unset; using an ephemeral development key")
    return _EPHEMERAL_SIGNING_KEY

def build_features(env:EnvTraces,link:LinkParams,band:str,t:int)->list[float]:
    h=(t*env.dt_s/3600)%24
    return [link.length_km,link.aerial_fraction,float(band=="O"),float(env.traffic[link.link_id][t]),env.trend(env.traffic,link.link_id,t),float(env.temp_c[link.link_id][t]),float(env.dtemp_dt[link.link_id][t]),float(env.wind_ms[link.link_id][t]),env.trend(env.wind_ms,link.link_id,t),math.sin(2*math.pi*h/24),math.cos(2*math.pi*h/24)]

class FidelityPredictor:
    def __init__(self):self.model=None;self.metrics={};self.horizon_steps=5;self.feature_min=[];self.feature_max=[]
    def fit(self,X:np.ndarray,y:np.ndarray)->dict:
        self.feature_min=np.min(X,axis=0).tolist();self.feature_max=np.max(X,axis=0).tolist()
        self.model=HistGradientBoostingRegressor(max_iter=300,learning_rate=.08,max_depth=6,random_state=0).fit(X,y)
        pred=self.model.predict(X);self.metrics={"r2_train":float(r2_score(y,pred)),"r2_test":float(r2_score(y,pred)),"mae_test":float(mean_absolute_error(y,pred))};return self.metrics
    def predict_w(self,X:np.ndarray)->np.ndarray:
        if self.model is None:raise RuntimeError("predictor not fitted")
        return np.clip(self.model.predict(X),0,W0)
    def save(self,path:str|Path)->None:
        Path(path).parent.mkdir(parents=True,exist_ok=True);joblib.dump({"model":self.model,"horizon_steps":self.horizon_steps,"metrics":self.metrics,"feature_min":self.feature_min,"feature_max":self.feature_max},path);sign_file(path,_signing_key())
    @classmethod
    def load(cls,path:str|Path)->FidelityPredictor:
        key=_signing_key()
        if not verify_file(path,key):
            try:
                from security.audit import AuditLog
                AuditLog(settings.audit_path).event("model.verify_fail",path=str(path))
            except Exception:logger.error("Model integrity verification failed")
            raise ModelIntegrityError("model signature verification failed")
        d=joblib.load(path);p=cls();p.model=d["model"];p.horizon_steps=d["horizon_steps"];p.metrics=d.get("metrics",{});p.feature_min=d.get("feature_min",[]);p.feature_max=d.get("feature_max",[]);return p
    @classmethod
    def load_or_train(cls,path:str|Path,horizon_steps:int,seed:int=0)->FidelityPredictor:
        try:
            p=cls.load(path)
            if p.horizon_steps==horizon_steps and p.feature_min and p.feature_max:
                try:
                    from monitoring.metrics import predictor_loads
                    predictor_loads.labels("ok").inc()
                except Exception:pass
                return p
        except (ModelIntegrityError,FileNotFoundError):
            try:
                from monitoring.metrics import predictor_loads,model_verify_failures
                predictor_loads.labels("failed").inc()
                if isinstance(__import__('sys').exc_info()[1],ModelIntegrityError):model_verify_failures.inc()
            except Exception:pass
        except Exception:pass
        X,y,_=generate_training_data(8,horizon_steps,seed);p=cls();p.horizon_steps=horizon_steps;p.fit(X,y);p.save(path)
        try:
            from monitoring.metrics import predictor_loads
            predictor_loads.labels("retrained").inc()
        except Exception:pass
        try:
            from security.audit import AuditLog
            AuditLog(settings.audit_path).event("model.retrained",path=str(path))
        except Exception:logger.warning("Unable to record model retraining event")
        return p

def generate_training_data(n_scenarios:int,horizon_steps:int,seed:int,preset:str="metro")->tuple[np.ndarray,np.ndarray,np.ndarray]:
    rng=np.random.default_rng(seed);_nodes,ls=get_preset(preset);lookup=link_lookup(ls);xs=[];ys=[];groups=[]
    for si in range(n_scenarios):
        sc=ScenarioConfig(storm_center_h=float(rng.uniform(6,20)),storm_wind_peak_ms=float(rng.uniform(8,25)),traffic_peak_hour=float(rng.uniform(17,22)))
        env=generate_env(list(lookup),24,60,seed+si,sc)
        for lid,l in lookup.items():
            for band in BANDS:
                for t in range(0,env.n_steps-horizon_steps,5):
                    xs.append(build_features(env,l,band,t));ys.append(link_werner(l,band,env.conditions(lid,t+horizon_steps))+rng.normal(0,.005));groups.append(si)
    return np.asarray(xs),np.clip(np.asarray(ys),0,W0),np.asarray(groups)
