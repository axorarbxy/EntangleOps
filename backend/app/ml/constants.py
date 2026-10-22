from __future__ import annotations

TRAIN_SEED_BASE = 10_000
CAL_SEED_BASE = 50_000
EVAL_SEED_BASE = 90_000
OOD_SEED_BASE = 95_000
SELECT_SEEDS = range(100, 105)
REPORT_SEEDS = range(42, 47)
ALPHAS = (0.05, 0.10, 0.20)
SUITES = {"cal_v1": (CAL_SEED_BASE, 8, "id"), "eval_v1": (EVAL_SEED_BASE, 8, "id"), "ood_v1": (OOD_SEED_BASE, 6, "ood")}
FEATURES_V1 = ("length_km", "aerial_fraction", "band_is_o", "traffic_now", "traffic_trend", "temp_now", "dtemp_dt_now", "wind_now", "wind_trend", "hour_sin", "hour_cos")
FEATURES_V2 = FEATURES_V1 + ("wind_trend_15", "traffic_trend_15", "dtemp_trend_5", "wind_max_30", "traffic_mean_30", "aerial_km", "phys_w_now")
SCHEMAS = {"v1": FEATURES_V1, "v2": FEATURES_V2}
IDX = {name: i for i, name in enumerate(FEATURES_V2)}
DYNAMIC_FEATURES = ("traffic_now", "traffic_trend", "temp_now", "dtemp_dt_now", "wind_now", "wind_trend", "wind_trend_15", "traffic_trend_15", "dtemp_trend_5", "wind_max_30", "traffic_mean_30", "phys_w_now")
GROUPS = ("buried", "mixed", "aerial")
EXPERIMENT_KINDS = ("train", "evaluation", "tuning", "ablation", "policy_study", "drift_baseline")
