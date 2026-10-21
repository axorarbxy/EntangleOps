from __future__ import annotations
import pytest
from pydantic import ValidationError
from app.schemas import SimRequest
from app.config import ScenarioConfig

def test_strict_bounds_reject_unknown_nan_and_bad_weights():
    with pytest.raises(ValidationError):SimRequest.model_validate({"duration_hours":1,"extra":"bad"})
    with pytest.raises(ValidationError):SimRequest.model_validate_json('{"duration_hours":NaN}')
    with pytest.raises(ValidationError):ScenarioConfig(min_fidelity_choices=[.8],min_fidelity_weights=[.4,.6])
    with pytest.raises(ValidationError):ScenarioConfig(traffic_base=1.5)
