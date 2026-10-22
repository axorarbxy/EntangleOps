from __future__ import annotations

import numpy as np
from app.ml.constants import FEATURES_V1, FEATURES_V2


def permutation_importance(predictor, X, y, *, n_repeats=5, seed=0):
    X,y=np.asarray(X,dtype=float),np.asarray(y,dtype=float)
    rng=np.random.default_rng(seed);base=float(np.mean(np.abs(y-predictor.predict_w(X))))
    names=FEATURES_V1 if predictor.feature_schema=="v1" else FEATURES_V2
    individual={}
    for i,name in enumerate(names):
        values=[]
        for _ in range(n_repeats):
            xp=X.copy();xp[:,i]=xp[rng.permutation(len(xp)),i]
            values.append(float(np.mean(np.abs(y-predictor.predict_w(xp)))-base))
        individual[name]={"mean":float(np.mean(values)),"std":float(np.std(values))}
    groups={"traffic":["traffic_now","traffic_trend","traffic_trend_15","traffic_mean_30"],
            "thermal":["temp_now","dtemp_dt_now","dtemp_trend_5"],"wind":["wind_now","wind_trend","wind_trend_15","wind_max_30"],
            "geometry":["length_km","aerial_fraction","aerial_km"],"time":["hour_sin","hour_cos"],"physics-prior":["phys_w_now"]}
    grouped={}
    for group,features in groups.items():
        cols=[names.index(name) for name in features if name in names]
        if not cols:continue
        vals=[]
        for _ in range(n_repeats):
            xp=X.copy();perm=rng.permutation(len(xp));xp[:,cols]=xp[perm][:,cols]
            vals.append(float(np.mean(np.abs(y-predictor.predict_w(xp)))-base))
        grouped[group]={"mean":float(np.mean(vals)),"std":float(np.std(vals))}
    return {"individual":individual,"groups":grouped,"method":"permutation MAE increase; descriptive, not causal"}


def partial_dependence(predictor, X, *, max_rows=2000):
    X=np.asarray(X,dtype=float);names=FEATURES_V1 if predictor.feature_schema=="v1" else FEATURES_V2
    rng=np.random.default_rng(0)
    if len(X)>max_rows:X=X[np.sort(rng.choice(len(X),size=max_rows,replace=False))]
    output={}
    for feature in ("wind_now","traffic_now","dtemp_dt_now"):
        idx=names.index(feature);grid=np.unique(np.quantile(X[:,idx],np.linspace(0,1,10)));means=[]
        for value in grid:
            copy=X.copy();copy[:,idx]=value;means.append(float(np.mean(predictor.predict_w(copy))))
        output[feature]={"values":grid.tolist(),"mean_prediction":means}
    return output


def model_card(predictor, *, data=None, importance=None, evaluation=None):
    return {"intended_use":"forecast link fidelity inside the EntangleOps digital twin",
            "data":data or {"source":"synthetic scenarios"},"profile":predictor.profile,
            "feature_schema":predictor.feature_schema,"target_mode":predictor.target_mode,
            "horizon_steps":predictor.horizon_steps,"metrics":predictor.metrics,
            "training":{"seed":getattr(predictor,"train_seed",None),"n_scenarios":getattr(predictor,"n_scenarios",None),
                        "generator_version":"synthetic_v1"},
            "calibration":predictor.calibration,"evaluation":evaluation,"importance":importance,
            "limitations":["stronger storms than training","unseen topologies","horizon fixed at h","synthetic labels"],
            "statement":"Synthetic data from an illustrative physics model; not calibrated to any real network. Not a quantum-security guarantee."}
