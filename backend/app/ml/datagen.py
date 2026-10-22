from __future__ import annotations

import hashlib
import json
import time
import threading
from dataclasses import dataclass

import numpy as np

from app.config import ScenarioConfig
from app.core.environment import EnvTraces, generate_env
from app.core.physics import BANDS, link_werner
from app.core.topology import get_preset, link_lookup
from app.ml.constants import CAL_SEED_BASE, EVAL_SEED_BASE, OOD_SEED_BASE, SUITES, TRAIN_SEED_BASE
from app.ml.features import build_matrix, werner_np

_SUITE_CACHE: dict[tuple, "Dataset"] = {}
_SUITE_LOCK = threading.Lock()


@dataclass
class Dataset:
    X: np.ndarray
    y: np.ndarray
    groups: np.ndarray
    meta: dict
    envs: list[EnvTraces]


def randomized_scenario(rng: np.random.Generator) -> ScenarioConfig:
    return ScenarioConfig(storm_center_h=float(rng.uniform(6, 20)), storm_wind_peak_ms=float(rng.uniform(8, 25)),
                          traffic_peak_hour=float(rng.uniform(17, 22)))


def randomized_scenario_ood(rng: np.random.Generator) -> ScenarioConfig:
    return ScenarioConfig(storm_center_h=float(rng.uniform(6, 20)), storm_wind_peak_ms=float(rng.uniform(26, 40)),
                          storm_temp_drop_c=float(rng.uniform(10, 18)), storm_duration_h=float(rng.uniform(3, 6)),
                          traffic_base=float(rng.uniform(.55, .7)), traffic_amp=float(rng.uniform(.3, .45)),
                          traffic_spike_count=8)


def _fingerprint(env: EnvTraces) -> str:
    digest = hashlib.sha256()
    for lid in sorted(env.traffic):
        for traces in (env.traffic, env.temp_c, env.dtemp_dt, env.wind_ms):
            digest.update(np.asarray(traces[lid], dtype=np.float64).tobytes())
    return digest.hexdigest()


def legacy_fingerprints(n_scenarios: int, seed: int, preset: str = "metro") -> list[str]:
    """Recreate only the legacy scenario generator's environment traces for split checks."""
    _, links = get_preset(preset)
    link_ids = list(link_lookup(links))
    fingerprints = []
    rng = np.random.default_rng(seed)
    for i in range(n_scenarios):
        config = ScenarioConfig(storm_center_h=float(rng.uniform(6, 20)),
            storm_wind_peak_ms=float(rng.uniform(8, 25)), traffic_peak_hour=float(rng.uniform(17, 22)))
        fingerprints.append(_fingerprint(generate_env(link_ids, 24, 60, seed + i, config)))
    return fingerprints


def generate_dataset(seed_base: int, n_scenarios: int, horizon_steps: int, *, schema: str = "v1", kind: str = "id",
                     preset: str = "metro", label_noise_sigma: float = .005, noise_seed: int | None = None) -> Dataset:
    started = time.perf_counter()
    if n_scenarios < 2 or horizon_steps < 1 or kind not in {"id", "ood"}:
        raise ValueError("invalid dataset configuration")
    nodes, links = get_preset(preset)
    del nodes
    lookup = link_lookup(links)
    x_blocks, y_blocks, group_blocks, envs, configs, fingerprints = [], [], [], [], [], []
    for i in range(n_scenarios):
        seed = seed_base + i
        rng = np.random.default_rng(seed)
        config = randomized_scenario_ood(rng) if kind == "ood" else randomized_scenario(rng)
        env = generate_env(list(lookup), 24.0, 60, seed, config)
        envs.append(env)
        configs.append(config.model_dump(mode="json"))
        fingerprints.append(_fingerprint(env))
        steps = np.arange(0, env.n_steps - horizon_steps, 5, dtype=np.int64)
        noise = np.random.default_rng((noise_seed if noise_seed is not None else seed_base + 7919) + i)
        for link in lookup.values():
            for band in BANDS:
                x = build_matrix(env, link, band, steps, schema)
                y = werner_np(link.length_km, link.aerial_fraction, band == "O", env.traffic[link.link_id][steps + horizon_steps],
                              env.dtemp_dt[link.link_id][steps + horizon_steps], env.wind_ms[link.link_id][steps + horizon_steps])
                if label_noise_sigma:
                    y = y + noise.normal(0, label_noise_sigma, size=y.shape)
                x_blocks.append(x)
                y_blocks.append(np.clip(y, 0, .97))
                group_blocks.append(np.full(len(steps), i, dtype=np.int32))
    X, y, groups = np.vstack(x_blocks), np.concatenate(y_blocks), np.concatenate(group_blocks)
    digest = hashlib.sha256(X.tobytes() + y.tobytes() + json.dumps(configs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return Dataset(X, y, groups, {"seed_base": seed_base, "n_scenarios": n_scenarios, "horizon_steps": horizon_steps,
                                  "schema": schema, "kind": kind, "preset": preset, "sha256": digest,
                                  "generation_s": time.perf_counter() - started, "configs": configs,
                                  "fingerprints": fingerprints}, envs)


def suite(name: str, horizon_steps: int, *, schema: str, preset: str = "metro", label_noise_sigma: float = 0.0) -> Dataset:
    try:
        seed_base, n_scenarios, kind = SUITES[name]
    except KeyError as exc:
        raise ValueError("unknown evaluation suite") from exc
    key = (name, horizon_steps, schema, preset, label_noise_sigma)
    with _SUITE_LOCK:
        data = _SUITE_CACHE.get(key)
        if data is None:
            data = generate_dataset(seed_base, n_scenarios, horizon_steps, schema=schema, kind=kind,
                                     preset=preset, label_noise_sigma=label_noise_sigma)
            data.meta["suite"] = name
            _SUITE_CACHE[key] = data
        return data
