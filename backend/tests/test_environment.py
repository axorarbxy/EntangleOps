from __future__ import annotations
import numpy as np
from app.config import ScenarioConfig
from app.core.environment import generate_env

def test_environment_determinism_and_ranges():
    a=generate_env(["A-B"],24,60,42,ScenarioConfig());b=generate_env(["A-B"],24,60,42,ScenarioConfig())
    assert np.array_equal(a.traffic["A-B"],b.traffic["A-B"])
    assert np.all((a.traffic["A-B"]>=0)&(a.traffic["A-B"]<=1));assert np.all(a.wind_ms["A-B"]>=0)
    c=generate_env(["A-B"],24,60,43,ScenarioConfig());assert not np.array_equal(a.wind_ms["A-B"],c.wind_ms["A-B"])
