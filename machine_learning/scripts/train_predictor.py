from __future__ import annotations
from pathlib import Path
import sys
import argparse
_repo_root = Path(__file__).resolve().parents[2]
_backend_root = _repo_root / "backend"
for _path in (_repo_root, _backend_root):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
from app.config import settings
from app.core.predictor import FidelityPredictor,generate_training_data
from app.db.repos.datasets import DatasetStore,FEATURE_COLUMNS
from app.db.repos.model_registry import ModelRegistry
from app.db.runtime import open_database

def main()->None:
    parser=argparse.ArgumentParser();parser.add_argument("--from-dataset",help="train from a stored dataset id");args=parser.parse_args()
    if args.from_dataset:
        engine,sf=open_database(migrate_development=True)
        try:
            rows=DatasetStore(sf).training_rows(args.from_dataset)
            import numpy as np
            X=np.asarray([[float(row[c]) for c in FEATURE_COLUMNS] for row in rows]);y=np.asarray([float(row["label_w"]) for row in rows])
            train=np.asarray([row["split"]=="train" for row in rows]);test=~train
            if not train.any() or not test.any():raise SystemExit("dataset must contain train and test scenario groups")
        finally:engine.dispose()
    else:
        X,y,groups=generate_training_data(24,settings.forecast_horizon_steps,settings.default_seed)
        split=int((groups.max()+1)*.8);train=groups<split;test=~train
    model=FidelityPredictor();model.horizon_steps=settings.forecast_horizon_steps
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error,r2_score
    model.model=HistGradientBoostingRegressor(max_iter=300,learning_rate=.08,max_depth=6,random_state=0).fit(X[train],y[train])
    model.metrics={"r2_train":float(r2_score(y[train],model.model.predict(X[train]))),"r2_test":float(r2_score(y[test],model.model.predict(X[test]))),"mae_test":float(mean_absolute_error(y[test],model.model.predict(X[test])))}
    model.feature_min=X[train].min(axis=0).tolist();model.feature_max=X[train].max(axis=0).tolist()
    model.save(settings.model_path)
    engine,sf=open_database(migrate_development=True)
    try:
        model_id=ModelRegistry(sf).record(settings.model_path,{"horizon_steps":model.horizon_steps,"metrics":model.metrics,
            "feature_min":model.feature_min,"feature_max":model.feature_max},training_dataset_id=args.from_dataset)
    finally:engine.dispose()
    print({"model_id":model_id,**model.metrics})
if __name__=="__main__":main()
