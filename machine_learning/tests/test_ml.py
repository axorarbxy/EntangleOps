from __future__ import annotations

from pathlib import Path
import sys

_repo_root = Path(__file__).resolve().parents[2]
_backend_root = _repo_root / "backend"
for _path in (_repo_root, _backend_root):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import numpy as np
import pytest
import copy
from sqlalchemy import text

from app.core.predictor import FidelityPredictor, generate_training_data
from app.db.migrate import upgrade_to_head
from app.db.repos.ml_experiments import ExperimentRepo
from app.db.repos.model_registry import ModelRegistry
from app.db.session import make_engine, make_session_factory, resolve_url
from app.ml.conformal import calibrate, conformal_quantile
from app.ml.datagen import generate_dataset, suite
from app.ml.features import build_matrix, build_features, physics_w_np
from app.core.physics import link_werner
from app.ml.serving import RowCachePredictor
from app.core.topology import get_preset, link_lookup


def test_vectorized_v1_features_match_legacy_row_builder():
    _, links = get_preset("tiny")
    link = links[0]
    env = generate_dataset(21000, 2, 5, preset="tiny").envs[0]
    steps = np.asarray([0, 5, 20, 100])
    expected = np.asarray([build_features(env, link, "C", int(step)) for step in steps])
    assert np.array_equal(build_matrix(env, link, "C", steps), expected)


def test_v2_features_do_not_read_future_and_physics_baseline_matches():
    _, links = get_preset("tiny")
    link = links[0]
    env = generate_dataset(21000, 2, 5, preset="tiny").envs[0]
    step = 100
    expected = np.asarray(build_features(env, link, "O", step, schema="v2"))
    changed = copy.deepcopy(env)
    for traces in (changed.traffic, changed.temp_c, changed.dtemp_dt, changed.wind_ms):
        for series in traces.values(): series[step + 1:] = np.random.default_rng(4).normal(size=len(series) - step - 1)
    assert np.array_equal(expected, np.asarray(build_features(changed, link, "O", step, schema="v2")))
    row = build_features(env, link, "O", step)
    assert np.isclose(physics_w_np(np.asarray([row]))[0], link_werner(link, "O", env.conditions(link.link_id, step)), rtol=1e-12)


def test_datasets_are_deterministic_and_scenario_sets_do_not_overlap():
    first = generate_dataset(10000, 2, 5, preset="tiny")
    second = generate_dataset(10000, 2, 5, preset="tiny")
    cal = suite("cal_v1", 5, schema="v1", preset="tiny")
    assert first.meta["sha256"] == second.meta["sha256"]
    assert set(first.meta["fingerprints"]).isdisjoint(cal.meta["fingerprints"])


def test_conformal_quantile_and_group_fallback():
    assert conformal_quantile(np.asarray([1, 2, 3, 4]), .2) == 4
    with pytest.raises(ValueError):
        conformal_quantile(np.asarray([1]), .05)
    X, y, _ = generate_training_data(2, 5, 31, preset="tiny")
    model = FidelityPredictor(); model.fit(X, y)
    cal = X[:400]
    model.calibration = calibrate(model, cal, y[:400], min_group_n=500)
    assert model.calibration["fallback_groups"]
    assert model.predict_w_interval_full(cal[:3], .1)[1].shape == (3,)


def test_row_cache_preserves_full_intervals_and_is_bounded():
    class Dummy:
        horizon_steps = 5
        feature_schema = "v1"
        calibration = {"q": {"0.1": {"global": .05}}}
        feature_min = [0.0]
        feature_max = [1.0]
        def predict_w(self, X): return np.asarray(X)[:, 0]
        def predict_w_interval_full(self, X, alpha):
            point = self.predict_w(X)
            return point, point - .1, point + .1

    cache = RowCachePredictor(Dummy(), max_rows=2)
    X = np.asarray([[.2], [.3], [.4]])
    point, low, high = cache.predict_w_interval_full(X, .1)
    assert np.allclose(point, [.2, .3, .4])
    assert np.allclose(low, [.1, .2, .3]) and np.allclose(high, [.3, .4, .5])
    assert len(cache._interval) == 2


def test_experiments_are_append_only_and_benchmarks_remain_three_policy(tmp_path):
    engine = make_engine(resolve_url(f"sqlite:///{(tmp_path / 'ml.db').as_posix()}"))
    upgrade_to_head(engine)
    sf = make_session_factory(engine)
    repo = ExperimentRepo(sf)
    exp_id = repo.record("evaluation", "test", {"suite": "eval_v1"}, {"mae": .1})
    assert repo.get(exp_id)["id"] == exp_id
    with pytest.raises(Exception):
        with engine.begin() as conn:
            conn.execute(text("UPDATE ml_experiments SET name='changed' WHERE id=:id"), {"id": exp_id})
    with engine.connect() as conn:
        definition=conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='benchmark_results'")).scalar_one()
        assert "adaptive_risk" not in definition
    engine.dispose()


def test_model_registry_records_candidate_and_requires_calibration_for_promotion(tmp_path):
    engine = make_engine(resolve_url(f"sqlite:///{(tmp_path / 'registry.db').as_posix()}"))
    upgrade_to_head(engine)
    sf = make_session_factory(engine)
    X, y, _ = generate_training_data(2, 5, 9, preset="tiny")
    model = FidelityPredictor(); model.fit(X, y)
    path = tmp_path / "candidate.joblib"; model.save(path)
    registry = ModelRegistry(sf)
    mid = registry.record(str(path), {"horizon_steps": 5, "feature_min": model.feature_min,
        "feature_max": model.feature_max, "metrics": model.metrics}, activate=False)
    assert registry.get(mid)["status"] == "candidate"
    assert registry.active_id() is None
    engine.dispose()
