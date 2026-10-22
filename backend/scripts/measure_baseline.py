from __future__ import annotations

import numpy as np
import argparse
from app.config import settings
from app.core.environment import generate_env
from app.core.physics import BANDS, link_werner
from app.core.predictor import FidelityPredictor, build_features, generate_training_data
from app.core.topology import get_preset, link_lookup
from monitoring.drift import DriftMonitor
from app.db.repos.model_registry import ModelRegistry
from app.db.runtime import open_database

def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument("--store",action="store_true");parser.add_argument("--ml",action="store_true",help="also measure calibrated interval, ID/OOD and feature-drift baselines for the active model");args=parser.parse_args()
    predictor=FidelityPredictor();X,y,_=generate_training_data(8,5,42);predictor.horizon_steps=5;predictor.fit(X,y)
    nodes,links=get_preset("metro");lookup=link_lookup(links);errors=[];outside=[]
    for seed in range(42,47):
        env=generate_env(list(lookup),24,60,seed)
        for lid,link in lookup.items():
            for band in BANDS:
                for t in range(0,env.n_steps-5,10):
                    x=build_features(env,link,band,t);errors.append(abs(float(predictor.predict_w([x])[0])-link_werner(link,band,env.conditions(lid,t+5))))
                    outside.append(any(v<a or v>b for v,a,b in zip(x,predictor.feature_min,predictor.feature_max)))
    result={"mean_abs_error":float(np.mean(errors)),"p95_abs_error":float(np.quantile(errors,.95)),"out_of_range_ratio":float(np.mean(outside)),"seeds":[42,43,44,45,46]}
    if args.ml:
        from app.ml.datagen import suite
        from app.ml.evaluate import evaluate_dataset
        try:
            active_model=FidelityPredictor.load(settings.model_path)
            eval_data=suite("eval_v1",active_model.horizon_steps,schema=active_model.feature_schema)
            ood_data=suite("ood_v1",active_model.horizon_steps,schema=active_model.feature_schema)
            result["ml"]={"eval_v1":evaluate_dataset(active_model,eval_data),"ood_v1":evaluate_dataset(active_model,ood_data),
                          "feature_reference_available":bool(active_model.reference),"model_profile":active_model.profile}
            result["ml"]["suite_hashes"]={"eval_v1":eval_data.meta["sha256"],"ood_v1":ood_data.meta["sha256"]}
        except Exception as exc:
            raise SystemExit(f"ML baseline measurement failed: {type(exc).__name__}") from exc
    if args.store:
        engine,sf=open_database(migrate_development=True)
        try:
            registry=ModelRegistry(sf);model_id=registry.active_id()
            if model_id is None:raise SystemExit("no active model is registered; start the backend or train the predictor first")
            registry.store_baseline(model_id,result["seeds"],result["mean_abs_error"],result["p95_abs_error"],result["out_of_range_ratio"])
            if args.ml:
                from app.db.repos.ml_experiments import ExperimentRepo
                ExperimentRepo(sf).record("drift_baseline","measured active model baseline",
                    {"suite_hashes":result["ml"]["suite_hashes"],"seeds":result["seeds"]},result["ml"],
                    profile=result["ml"]["model_profile"],model_id=model_id)
        finally:engine.dispose()
    print(result)

if __name__ == "__main__": main()
