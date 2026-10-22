from __future__ import annotations
import argparse,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import settings
from app.core.predictor import FidelityPredictor
from app.ml.constants import TRAIN_SEED_BASE
from app.ml.datagen import generate_dataset,suite
from app.ml.conformal import calibrate
from app.ml.evaluate import evaluate_dataset
from app.ml.profiles import PROFILES
from app.db.repos.ml_experiments import ExperimentRepo
from scripts._ml_cli import dump_report,open_ml_db,require_signing_key

def main():
 p=argparse.ArgumentParser();p.add_argument('--seed',type=int,default=0);p.add_argument('--n-scenarios',type=int,default=24);p.add_argument('--store',action='store_true');a=p.parse_args();require_signing_key();rows={}
 for name,profile in PROFILES.items():
  data=generate_dataset(TRAIN_SEED_BASE+a.seed,a.n_scenarios,settings.forecast_horizon_steps,schema=profile.feature_schema)
  model=FidelityPredictor(name);model.horizon_steps=settings.forecast_horizon_steps;model.fit(data.X,data.y,data.groups)
  if profile.calibrated:
   cal=suite('cal_v1',model.horizon_steps,schema=profile.feature_schema);model.calibration=calibrate(model,cal.X,cal.y,suite_sha256=cal.meta['sha256'],train_fingerprints=data.meta['fingerprints'],calibration_fingerprints=cal.meta['fingerprints'])
  ev=suite('eval_v1',model.horizon_steps,schema=profile.feature_schema);ood=suite('ood_v1',model.horizon_steps,schema=profile.feature_schema)
  rows[name]={'eval':evaluate_dataset(model,ev),'ood':evaluate_dataset(model,ood)}
 horizons={}
 for h in (1,5,15):
  data=generate_dataset(TRAIN_SEED_BASE+a.seed,a.n_scenarios,h,schema='v1');model=FidelityPredictor('baseline_v1');model.horizon_steps=h;model.fit(data.X,data.y,data.groups)
  test=generate_dataset(90000,8,h,schema='v1');pred=model.predict_w(test.X);from app.ml.features import physics_w_np
  mae=float(np.mean(np.abs(test.y-pred)));base=float(np.mean(np.abs(test.y-physics_w_np(test.X))))
  horizons[str(h)]={'mae_w':mae,'skill_vs_persistence':1-mae/base if base else 0.0}
 result={'profiles':rows,'horizons':horizons}
 if a.store:
  engine,sf=open_ml_db()
  try:result['experiment_id']=ExperimentRepo(sf).record('ablation','profile and horizon ablation',{'seed':a.seed,'n_scenarios':a.n_scenarios},result)
  finally:engine.dispose()
 dump_report(result)
if __name__=='__main__':main()
