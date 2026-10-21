from __future__ import annotations
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import settings
from app.core.predictor import FidelityPredictor,generate_training_data

def main()->None:
    X,y,groups=generate_training_data(24,settings.forecast_horizon_steps,settings.default_seed)
    split=int((groups.max()+1)*.8)
    train=groups<split;test=~train
    model=FidelityPredictor();model.horizon_steps=settings.forecast_horizon_steps
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error,r2_score
    model.model=HistGradientBoostingRegressor(max_iter=300,learning_rate=.08,max_depth=6,random_state=0).fit(X[train],y[train])
    model.metrics={"r2_train":float(r2_score(y[train],model.model.predict(X[train]))),"r2_test":float(r2_score(y[test],model.model.predict(X[test]))),"mae_test":float(mean_absolute_error(y[test],model.model.predict(X[test])))}
    model.save(settings.model_path);print(model.metrics)
if __name__=="__main__":main()
