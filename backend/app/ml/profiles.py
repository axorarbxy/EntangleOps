from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    name: str
    feature_schema: str
    target_mode: str
    hgb: dict
    calibrated: bool = False


PROFILES = {
    "baseline_v1": Profile("baseline_v1", "v1", "direct", {"max_iter": 300, "learning_rate": .08, "max_depth": 6, "random_state": 0}),
    "hgb_residual_v1": Profile("hgb_residual_v1", "v1", "residual", {"max_iter": 400, "learning_rate": .06, "max_leaf_nodes": 31, "l2_regularization": .1, "early_stopping": False, "random_state": 0}, True),
    "hgb_direct_v2": Profile("hgb_direct_v2", "v2", "direct", {"max_iter": 400, "learning_rate": .06, "max_leaf_nodes": 31, "l2_regularization": .1, "early_stopping": False, "random_state": 0}, True),
    "hgb_residual_v2": Profile("hgb_residual_v2", "v2", "residual", {"max_iter": 400, "learning_rate": .06, "max_leaf_nodes": 31, "l2_regularization": .1, "early_stopping": False, "random_state": 0}, True),
}
