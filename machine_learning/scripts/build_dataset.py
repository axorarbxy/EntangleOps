from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[2]
_backend_root = _repo_root / "backend"
for _path in (_repo_root, _backend_root):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
from app.config import settings
from app.core.environment import generate_env
from app.core.predictor import generate_training_data
from app.core.topology import get_preset, link_lookup
from app.db.repos.datasets import DatasetStore, FEATURE_COLUMNS, canonical_training_csv, json_bytes
from app.db.runtime import open_database


def main():
    parser = argparse.ArgumentParser(description="Create, list, export, verify, or delete persistent simulator datasets")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build"); build.add_argument("--name", required=True); build.add_argument("--kind", choices=("training", "env_trace"), default="training")
    build.add_argument("--seed", type=int, default=settings.default_seed); build.add_argument("--scenarios", type=int, default=24)
    build.add_argument("--preset", choices=("metro", "tiny"), default="metro")
    sub.add_parser("list")
    export = sub.add_parser("export"); export.add_argument("dataset_id")
    verify = sub.add_parser("verify"); verify.add_argument("dataset_id")
    delete = sub.add_parser("delete"); delete.add_argument("dataset_id")
    args = parser.parse_args()
    engine, sf = open_database(migrate_development=True); store = DatasetStore(sf)
    try:
        if args.command == "build":
            if args.kind == "training":
                X, y, groups = generate_training_data(args.scenarios, settings.forecast_horizon_steps, args.seed, args.preset)
                split_at = int(args.scenarios * .8)
                rows = [{"scenario": int(group), "split": "train" if int(group) < split_at else "test",
                         **dict(zip(FEATURE_COLUMNS, map(float, features))), "label_w": float(label)}
                        for features, label, group in zip(X, y, groups)]
                result = store.create_training(args.name, args.seed,
                    {"n_scenarios": args.scenarios, "horizon_steps": settings.forecast_horizon_steps}, rows, args.preset)
            else:
                _nodes, links = get_preset(args.preset); lookup = link_lookup(links)
                env = generate_env(list(lookup), 24, 60, args.seed)
                rows = []
                for link_id in sorted(lookup):
                    for step in range(env.n_steps):
                        rows.append({"link_id": link_id, "step": step,
                            "traffic": float(env.traffic[link_id][step]), "temp_c": float(env.temp_c[link_id][step]),
                            "dtemp_dt": float(env.dtemp_dt[link_id][step]), "wind_ms": float(env.wind_ms[link_id][step])})
                result = store.create_env_trace(args.name, args.seed, {"duration_hours": 24, "dt_s": 60}, rows, args.preset)
            print(result)
        elif args.command == "list":
            for row in store.list(): print(row)
        elif args.command == "export":
            if not re.fullmatch(r"ds_[A-Za-z0-9_-]{8,32}", args.dataset_id): raise SystemExit("invalid dataset id")
            details = store.get(args.dataset_id)
            if not details: raise SystemExit("dataset not found")
            if details["kind"] == "training": payload = canonical_training_csv(store.training_rows(args.dataset_id)); suffix = "csv"
            else: payload = json_bytes(store.env_trace_rows(args.dataset_id)); suffix = "json"
            output = Path(settings.data_dir) / "exports" / f"{args.dataset_id}.{suffix}"
            output.parent.mkdir(parents=True, exist_ok=True); output.write_bytes(payload); print(output)
        elif args.command == "verify":
            valid, digest = store.verify(args.dataset_id); print(f"{'OK' if valid else 'FAIL'} {digest}")
            if not valid: raise SystemExit(1)
        elif args.command == "delete":
            if not store.delete(args.dataset_id): raise SystemExit("dataset not found")
            print("deleted")
    finally: engine.dispose()


if __name__ == "__main__": main()
