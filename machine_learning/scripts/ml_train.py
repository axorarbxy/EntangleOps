from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[2]
_backend_root = _repo_root / "backend"
for _path in (_repo_root, _backend_root):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import numpy as np

from app.config import settings
from app.core.predictor import FidelityPredictor, generate_training_data
from app.ml.constants import TRAIN_SEED_BASE
from app.ml.datagen import generate_dataset, legacy_fingerprints, suite
from app.ml.conformal import calibrate
from app.ml.explain import model_card
from app.db.repos.model_registry import ModelRegistry
from app.db.repos.ml_experiments import ExperimentRepo
from app.ml.evaluate import evaluate_dataset
from machine_learning.scripts._ml_cli import audit, dump_report, git_version, open_ml_db, require_signing_key


def train(args):
    require_signing_key()
    from app.ml.profiles import PROFILES
    profile=PROFILES[args.profile]
    if args.profile=="baseline_v1":
        X,y,groups=generate_training_data(args.n_scenarios,args.horizon,args.seed)
        data_meta={"seed":args.seed,"n_scenarios":args.n_scenarios,"sha256":hashlib.sha256(X.tobytes()+y.tobytes()).hexdigest(),"fingerprints":legacy_fingerprints(args.n_scenarios,args.seed)}
    else:
        seed=TRAIN_SEED_BASE+args.seed
        data=generate_dataset(seed,args.n_scenarios,args.horizon,schema=profile.feature_schema,kind="id",label_noise_sigma=.005)
        X,y,groups=data.X,data.y,data.groups;data_meta=data.meta
    model=FidelityPredictor(args.profile);model.horizon_steps=args.horizon
    model.n_scenarios=args.n_scenarios;model.train_seed=args.seed
    params=json.loads(Path(args.params_json).read_text(encoding="utf-8")) if args.params_json else None
    if params:
        from app.ml.training import fit_profile
        fitted=fit_profile(profile,X,y,groups,params)
        model.model=fitted.estimator;model.metrics=fitted.metrics;model.feature_min=fitted.feature_min;model.feature_max=fitted.feature_max
        model.reference=fitted.reference;model.mean_target=fitted.mean_target;model.feature_schema=profile.feature_schema;model.target_mode=profile.target_mode;model.format_version=2
    else:
        model.fit(X,y,groups)
    cal_data=None
    if args.calibrate:
        cal_data=suite("cal_v1",args.horizon,schema=profile.feature_schema,label_noise_sigma=0)
        model.calibration=calibrate(model,cal_data.X,cal_data.y,suite_sha256=cal_data.meta["sha256"],
                                    train_fingerprints=data_meta.get("fingerprints"),calibration_fingerprints=cal_data.meta.get("fingerprints"))
        model.format_version=2
    from sklearn import __version__ as sklearn_version
    model.sklearn_version=sklearn_version
    model_dir=Path(settings.ml_models_dir);model_dir.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="ml_candidate_",suffix=".joblib",dir=model_dir,delete=False) as f: temp=Path(f.name)
    try:
        model.save(temp)
        digest=hashlib.sha256(temp.read_bytes()).hexdigest();target=model_dir/f"{digest}.joblib"
        sig=temp.with_suffix(temp.suffix+".sig");final_sig=target.with_suffix(target.suffix+".sig")
        if target.exists():temp.unlink(missing_ok=True);sig.unlink(missing_ok=True)
        else:os.replace(temp,target);os.replace(sig,final_sig)
        try:target.chmod(0o600);final_sig.chmod(0o600);model_dir.chmod(0o700)
        except OSError:pass
    finally:
        temp.unlink(missing_ok=True);temp.with_suffix(temp.suffix+".sig").unlink(missing_ok=True)
    engine,sf=open_ml_db()
    try:
        card=model_card(model,data={"source":"synthetic","seed":args.seed,"n_scenarios":args.n_scenarios,"training_sha256":data_meta["sha256"]})
        registry=ModelRegistry(sf)
        registry_meta={"horizon_steps":model.horizon_steps,"metrics":{**model.metrics,"mean_target":model.mean_target,"format_version":model.format_version},
            "feature_min":model.feature_min,"feature_max":model.feature_max,"profile":model.profile,
            "feature_schema":model.feature_schema,"target_mode":model.target_mode,"calibration":model.calibration,
            "card":card,"sklearn_version":model.sklearn_version,"n_scenarios":args.n_scenarios,"train_seed":args.seed}
        model_id=registry.record(str(target),registry_meta,activate=False)
        exp_id=ExperimentRepo(sf).record("train",f"{args.profile} candidate",{"seed":args.seed,"n_scenarios":args.n_scenarios,"horizon":args.horizon,"params":params or profile.hgb,"training_sha256":data_meta["sha256"],"calibration_sha256":cal_data.meta["sha256"] if cal_data else None},model.metrics,profile=args.profile,model_id=model_id)
        audit(sf,"model.train",model_id=model_id,experiment_id=exp_id,profile=args.profile)
    finally:engine.dispose()
    report={"model_id":model_id,"sha256":digest,"profile":args.profile,"metrics":model.metrics,"calibrated":bool(model.calibration)}
    if args.evaluate:
        eval_data=suite("eval_v1",args.horizon,schema=model.feature_schema)
        ood_data=suite("ood_v1",args.horizon,schema=model.feature_schema)
        eval_report=evaluate_dataset(model,eval_data);ood_report=evaluate_dataset(model,ood_data)
        hashes={"eval_v1":eval_data.meta["sha256"],"ood_v1":ood_data.meta["sha256"]}
        evaluation={"reports":{"eval_v1":eval_report,"ood_v1":ood_report},"suite_hashes":hashes}
        engine,sf=open_ml_db()
        try:
            evaluation["experiment_id"]=ExperimentRepo(sf).record("evaluation",f"evaluation {args.profile}",
                {"sha256":digest,"suite_hashes":hashes},{"reports":evaluation["reports"]},
                profile=args.profile,model_id=model_id)
        finally:engine.dispose()
        report["evaluation"]=evaluation
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument("--profile",choices=("baseline_v1","hgb_residual_v1","hgb_direct_v2","hgb_residual_v2"),default="baseline_v1")
    p.add_argument("--horizon",type=int,default=settings.forecast_horizon_steps);p.add_argument("--n-scenarios",type=int,default=24);p.add_argument("--seed",type=int,default=0)
    p.add_argument("--params-json");p.add_argument("--calibrate",action=argparse.BooleanOptionalAction,default=None);p.add_argument("--evaluate",action="store_true")
    a=p.parse_args();from app.ml.profiles import PROFILES;a.calibrate=PROFILES[a.profile].calibrated if a.calibrate is None else a.calibrate
    dump_report(train(a))
if __name__=="__main__":main()
