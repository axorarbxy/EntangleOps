from __future__ import annotations

import numpy as np
from app.core.environment import generate_env
from app.core.physics import BANDS, link_werner
from app.core.predictor import FidelityPredictor, build_features, generate_training_data
from app.core.topology import get_preset, link_lookup
from monitoring.drift import DriftMonitor

def main() -> None:
    predictor=FidelityPredictor();X,y,_=generate_training_data(8,5,42);predictor.horizon_steps=5;predictor.fit(X,y)
    nodes,links=get_preset("metro");lookup=link_lookup(links);errors=[];outside=[]
    for seed in range(42,47):
        env=generate_env(list(lookup),24,60,seed)
        for lid,link in lookup.items():
            for band in BANDS:
                for t in range(0,env.n_steps-5,10):
                    x=build_features(env,link,band,t);errors.append(abs(float(predictor.predict_w([x])[0])-link_werner(link,band,env.conditions(lid,t+5))))
                    outside.append(any(v<a or v>b for v,a,b in zip(x,predictor.feature_min,predictor.feature_max)))
    print({"mean_abs_error":float(np.mean(errors)),"p95_abs_error":float(np.quantile(errors,.95)),"out_of_range_ratio":float(np.mean(outside)),"seeds":[42,43,44,45,46]})

if __name__ == "__main__": main()
