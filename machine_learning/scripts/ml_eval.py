from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

_repo_root = Path(__file__).resolve().parents[2]
_backend_root = _repo_root / "backend"
for _path in (_repo_root, _backend_root):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from app.config import settings
from app.core.predictor import FidelityPredictor
from app.ml.datagen import suite
from app.ml.evaluate import evaluate_dataset
from app.db.repos.ml_experiments import ExperimentRepo
from app.db.repos.model_registry import ModelRegistry
from machine_learning.scripts._ml_cli import candidate_path, dump_report, open_ml_db, require_signing_key


def evaluate(model_id=None, file=None, suites="eval_v1,ood_v1", store=False):
    require_signing_key()
    engine,sf=open_ml_db();registry=ModelRegistry(sf);model=None;resolved_id=model_id
    try:
        if model_id is not None:
            row=registry.get(int(model_id))
            if row is None:raise SystemExit("model id not found")
            path=candidate_path(row["sha256"])
            if hashlib.sha256(path.read_bytes()).hexdigest()!=row["sha256"]:raise SystemExit("model digest mismatch")
            model=FidelityPredictor.load(path)
        else:
            model=FidelityPredictor.load(file)
        reports={};suite_hashes={};slices={}
        for name in suites.split(","):
            if name not in {"eval_v1","ood_v1"}:raise SystemExit("only eval_v1 and ood_v1 are supported")
            data=suite(name,model.horizon_steps,schema=model.feature_schema)
            reports[name]=evaluate_dataset(model,data);suite_hashes[name]=data.meta["sha256"];slices[name]=reports[name].pop("slices")
        report={"model_id":resolved_id,"sha256":row["sha256"] if resolved_id is not None else hashlib.sha256(Path(file).read_bytes()).hexdigest(),
                "profile":model.profile,"reports":reports,"slices":slices}
        if store:
            eid=ExperimentRepo(sf).record("evaluation",f"evaluation {model.profile}",{"suite_hashes":suite_hashes,"sha256":report["sha256"]},
                                          {"reports":reports},slices=slices,profile=model.profile,model_id=resolved_id)
            report["experiment_id"]=eid
        return report
    finally:engine.dispose()


def main():
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument("--model-id",type=int);g.add_argument("--file")
    p.add_argument("--suites",default="eval_v1,ood_v1");p.add_argument("--store",action="store_true");p.add_argument("--json",action="store_true")
    a=p.parse_args();dump_report(evaluate(a.model_id,a.file,a.suites,a.store))
if __name__=="__main__":main()
