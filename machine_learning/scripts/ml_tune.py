from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import loguniform
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold, ParameterSampler

_repo_root = Path(__file__).resolve().parents[2]
_backend_root = _repo_root / "backend"
for _path in (_repo_root, _backend_root):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from app.config import settings
from app.core.predictor import generate_training_data
from app.ml.constants import TRAIN_SEED_BASE
from app.ml.datagen import generate_dataset
from app.ml.features import physics_w_np
from app.ml.profiles import PROFILES
from app.db.repos.ml_experiments import ExperimentRepo
from machine_learning.scripts._ml_cli import dump_report, open_ml_db, require_signing_key


def main():
    p=argparse.ArgumentParser();p.add_argument("--profile",choices=tuple(PROFILES),required=True);p.add_argument("--n-iter",type=int,default=12);p.add_argument("--folds",type=int,default=5);p.add_argument("--seed",type=int,default=0);p.add_argument("--store",action="store_true");a=p.parse_args()
    require_signing_key();profile=PROFILES[a.profile]
    if a.profile=="baseline_v1":X,y,g=generate_training_data(24,settings.forecast_horizon_steps,a.seed)
    else:
        d=generate_dataset(TRAIN_SEED_BASE+a.seed,24,settings.forecast_horizon_steps,schema=profile.feature_schema);X,y,g=d.X,d.y,d.groups
    space={"learning_rate":loguniform(.03,.15),"max_iter":[200,300,500],"max_leaf_nodes":[15,31,63],"min_samples_leaf":[20,50,100],"l2_regularization":[0,.1,1.0],"max_depth":[None,6,8]}
    if profile.target_mode=="direct":space["monotonic"]=[False,True]
    params=list(ParameterSampler(space,n_iter=max(1,min(a.n_iter,50)),random_state=a.seed));n_splits=min(max(2,a.folds),len(np.unique(g)));cv=GroupKFold(n_splits=n_splits);trials=[]
    for sampled in params:
        candidate=dict(sampled);monotonic=candidate.pop("monotonic",False)
        maes=[];aerial_maes=[]
        for train,test in cv.split(X,y,g):
            base=physics_w_np(X[train]) if profile.target_mode=="residual" else 0
            overrides=dict(candidate)
            if monotonic:
                if "monotonic_cst" not in inspect.signature(HistGradientBoostingRegressor).parameters:raise SystemExit("installed scikit-learn does not support monotonic_cst")
                constraints=np.zeros(X.shape[1],dtype=int);constraints[0]=constraints[3]=constraints[7]=-1
                overrides["monotonic_cst"]=constraints.tolist()
            estimator=HistGradientBoostingRegressor(**{**profile.hgb,**overrides}).fit(X[train],y[train]-base)
            pred=estimator.predict(X[test])
            if profile.target_mode=="residual":pred+=physics_w_np(X[test])
            abs_error=np.abs(y[test]-np.clip(pred,0,.97));maes.append(float(np.mean(abs_error)))
            mask=X[test,1]>=1
            if np.any(mask):aerial_maes.append(float(np.mean(abs_error[mask])))
        trials.append({"params":{**candidate,"monotonic":monotonic},"mae":float(np.mean(maes)),"aerial_mae":float(np.mean(aerial_maes)) if aerial_maes else None})
    trials.sort(key=lambda x:(x["mae"],float("inf") if x["aerial_mae"] is None else x["aerial_mae"]));best=trials[0]
    best_params=dict(best["params"]);monotonic=best_params.pop("monotonic",False)
    if monotonic:
        constraints=np.zeros(X.shape[1],dtype=int);constraints[0]=constraints[3]=constraints[7]=-1
        best_params["monotonic_cst"]=constraints.tolist()
    output={"profile":a.profile,"best_params":best_params,"best_mae":best["mae"],"best_aerial_mae":best["aerial_mae"],"trials":trials}
    path=Path(settings.data_dir)/"exports"/"ml"/f"tune_{a.profile}.json";path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(output,indent=2,allow_nan=False),encoding="utf-8")
    if a.store:
        engine,sf=open_ml_db()
        try:output["experiment_id"]=ExperimentRepo(sf).record("tuning",f"tuning {a.profile}",{"seed":a.seed,"folds":n_splits,"trials":len(trials)},output,profile=a.profile)
        finally:engine.dispose()
    dump_report(output)
if __name__=="__main__":main()
