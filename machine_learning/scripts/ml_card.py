from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[2]
_backend_root = _repo_root / "backend"
for _path in (_repo_root, _backend_root):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from app.core.predictor import FidelityPredictor
from app.db.repos.ml_experiments import ExperimentRepo
from app.db.repos.model_registry import ModelRegistry
from app.ml.datagen import suite
from app.ml.evaluate import evaluate_dataset
from app.ml.explain import model_card
from machine_learning.scripts._ml_cli import candidate_path, dump_report, open_ml_db, require_signing_key


def main():
    parser = argparse.ArgumentParser(description="Generate an evaluation-backed model card.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--model-id", type=int)
    group.add_argument("--file")
    parser.add_argument("--suite", choices=("eval_v1", "ood_v1"), default="eval_v1")
    parser.add_argument("--output")
    parser.add_argument("--store", action="store_true")
    args = parser.parse_args()
    require_signing_key()
    engine, sf = open_ml_db()
    try:
        row = None
        if args.model_id is not None:
            row = ModelRegistry(sf).get(args.model_id)
            if row is None: raise SystemExit("model id not found")
            path = candidate_path(row["sha256"])
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
                raise SystemExit("model digest mismatch")
        else:
            path = Path(args.file)
        predictor = FidelityPredictor.load(path)
        data = suite(args.suite, predictor.horizon_steps, schema=predictor.feature_schema)
        evaluation = evaluate_dataset(predictor, data)
        card = model_card(predictor, data={"source": "synthetic", "suite": args.suite,
            "suite_sha256": data.meta["sha256"], "n_scenarios": data.meta["n_scenarios"]},
            importance=evaluation["importance"], evaluation=evaluation)
        card["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        if args.store and row:
            exp_id = ExperimentRepo(sf).record("evaluation", f"model card {row['profile']}",
                {"suite": args.suite, "suite_sha256": data.meta["sha256"], "sha256": card["sha256"]},
                {"model_card": card}, slices=evaluation["slices"], profile=predictor.profile, model_id=row["id"])
            card["experiment_id"] = exp_id
            ModelRegistry(sf).update_card(row["id"], card)
        markdown = "# Model card: " + predictor.profile + "\n\n" + card["statement"] + "\n\n"
        markdown += "## Intended use\n\n" + card["intended_use"] + "\n\n## Evaluation\n\n```json\n"
        markdown += json.dumps(evaluation, indent=2, sort_keys=True, allow_nan=False) + "\n```\n\n## Limitations\n\n"
        markdown += "\n".join(f"- {item}" for item in card["limitations"]) + "\n"
        output = Path(args.output) if args.output else Path(__file__).resolve().parents[1] / "docs" / "model_cards" / f"MODEL_CARD_{predictor.profile}_{card['sha256'][:8]}.md"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown, encoding="utf-8")
        dump_report({"model_card": card, "markdown": str(output)})
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
