from __future__ import annotations
import numpy as np
from app.core.predictor import FidelityPredictor,generate_training_data

def test_predictor_fit_save_load(tmp_path):
    X,y,_=generate_training_data(2,5,9,preset="tiny")
    p=FidelityPredictor();p.fit(X,y);before=p.predict_w(X[:8]);path=tmp_path/"model.joblib";p.save(path)
    loaded=FidelityPredictor.load(path);assert np.array_equal(before,loaded.predict_w(X[:8]))
