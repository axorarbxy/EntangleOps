from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[2]
_backend_root = _repo_root / "backend"
for _path in (_repo_root, _backend_root):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from app.config import settings
from app.core.predictor import FidelityPredictor
from app.db.repos.ml_experiments import ExperimentRepo
from app.db.repos.model_registry import ModelRegistry
from app.ml.datagen import suite
from app.ml.evaluate import evaluate_dataset
from app.ml.payload import ModelIntegrityError, archive_model
from machine_learning.scripts._ml_cli import audit, candidate_path, dump_report, open_ml_db, require_signing_key


def _evaluation(model):
    id_data = suite("eval_v1", model.horizon_steps, schema=model.feature_schema)
    ood_data = suite("ood_v1", model.horizon_steps, schema=model.feature_schema)
    reports = {"eval_v1": evaluate_dataset(model, id_data), "ood_v1": evaluate_dataset(model, ood_data)}
    hashes = {"eval_v1": id_data.meta["sha256"], "ood_v1": ood_data.meta["sha256"]}
    return reports, hashes


def evaluate_gates(model, candidate_reports, champion_reports=None, *, g7=False, g8=False):
    candidate = candidate_reports["eval_v1"]
    champion = champion_reports["eval_v1"] if champion_reports else candidate
    candidate_aerial, champion_aerial = candidate["slices"].get("aerial"), champion["slices"].get("aerial")
    g2 = model.metrics.get("r2_test") is not None and model.metrics["r2_test"] >= .85
    if champion_reports:
        g2 = g2 and candidate["overall"]["mae_w"] <= champion["overall"]["mae_w"]
        g2 = g2 and candidate_aerial is not None and champion_aerial is not None and candidate_aerial["mae_w"] <= champion_aerial["mae_w"]
    point = candidate["decision"].get("0.85", {}).get("point_m0.01", {}).get("false_feasible_rate")
    champion_point = champion["decision"].get("0.85", {}).get("point_m0.01", {}).get("false_feasible_rate")
    coverage = candidate["calibration"].get("0.1", {}).get("empirical")
    p95 = candidate["latency_ms"].get("24", {}).get("p95")
    champion_p95 = champion["latency_ms"].get("24", {}).get("p95")
    gates = {
        "G1_provenance": model.format_version == 2 and bool(model.model),
        "G2_accuracy": bool(g2),
        "G3_baseline_skill": candidate["overall"].get("skill_vs_persistence", -1) > 0,
        "G4_decision_quality": point is not None and champion_point is not None and point <= champion_point + .005,
        "G5_calibration": (coverage is not None and .86 <= coverage <= .94) if model.calibration else True,
        "G6_latency": p95 is not None and champion_p95 is not None and p95 <= max(50.0, 2 * champion_p95),
        "G7_end_to_end": bool(g7), "G8_freshness": bool(g8),
    }
    return {"gates": gates, "pass": all(gates.values()), "candidate": candidate,
            "ood": candidate_reports["ood_v1"]}


def _install_artifact(source: Path, model: FidelityPredictor) -> None:
    target = Path(settings.model_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.with_suffix(target.suffix + ".staged")
    staged_sig = staged.with_suffix(staged.suffix + ".sig")
    shutil.copy2(source, staged)
    shutil.copy2(source.with_suffix(source.suffix + ".sig"), staged_sig)
    try:
        staged.chmod(0o600); staged_sig.chmod(0o600)
    except OSError:
        pass
    loaded = FidelityPredictor.load(staged)
    if loaded.profile != model.profile or hashlib.sha256(staged.read_bytes()).hexdigest() != hashlib.sha256(source.read_bytes()).hexdigest():
        staged.unlink(missing_ok=True); staged_sig.unlink(missing_ok=True)
        raise ModelIntegrityError("staged model verification failed")
    backup = target.with_suffix(target.suffix + ".previous")
    backup_sig = backup.with_suffix(backup.suffix + ".sig")
    prior_sig = target.with_suffix(target.suffix + ".sig")
    archive_model(target, settings.ml_models_dir)
    backup.unlink(missing_ok=True); backup_sig.unlink(missing_ok=True)
    if target.exists(): os.replace(target, backup)
    if prior_sig.exists(): os.replace(prior_sig, backup_sig)
    try:
        os.replace(staged, target)
        os.replace(staged_sig, prior_sig)
    except Exception:
        target.unlink(missing_ok=True); prior_sig.unlink(missing_ok=True)
        if backup.exists(): os.replace(backup, target)
        if backup_sig.exists(): os.replace(backup_sig, prior_sig)
        raise
    backup.unlink(missing_ok=True); backup_sig.unlink(missing_ok=True)


def _rollback(registry, sf):
    retired = registry.rollback_candidate()
    if retired is None: raise SystemExit("no previous champion is available")
    source = candidate_path(retired["sha256"])
    if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != retired["sha256"]:
        raise SystemExit("previous champion artifact is missing or invalid")
    model = FidelityPredictor.load(source)
    _install_artifact(source, model)
    restored = registry.rollback()
    if restored != retired["id"]: raise RuntimeError("registry rollback did not restore the staged champion")
    audit(sf, "model.rollback", model_id=restored)
    return restored


def main():
    parser = argparse.ArgumentParser(description="Promote an ML candidate after G1–G8, or roll back to the previous champion.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--model-id", type=int)
    group.add_argument("--rollback", action="store_true")
    parser.add_argument("--yes", action="store_true", help="apply the verified promotion or rollback; without it, print a dry-run report")
    args = parser.parse_args()
    require_signing_key()
    engine, sf = open_ml_db()
    try:
        registry = ModelRegistry(sf)
        if args.rollback:
            if not args.yes:
                retired = registry.rollback_candidate()
                dump_report({"rolled_back": False, "dry_run": True,
                    "previous_champion_available": retired is not None,
                    "model_id": retired["id"] if retired else None,
                    "sha256": retired["sha256"] if retired else None})
                return
            restored = _rollback(registry, sf)
            dump_report({"rolled_back": True, "model_id": restored, "restart_required": True})
            return
        row = registry.get(args.model_id)
        if row is None: raise SystemExit("candidate model not found")
        source = candidate_path(row["sha256"])
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != row["sha256"]:
            raise SystemExit("candidate artifact digest is missing or invalid")
        model = FidelityPredictor.load(source)
        if model.format_version != 2 or row.get("format_version") != model.format_version or model.horizon_steps != settings.forecast_horizon_steps:
            raise SystemExit("candidate format or forecast horizon does not match serving requirements")
        if model.sklearn_version is None or ".".join(model.sklearn_version.split(".")[:2]) != ".".join(__import__("sklearn").__version__.split(".")[:2]):
            raise SystemExit("candidate scikit-learn version does not match the runtime")
        if row.get("sklearn_version") != model.sklearn_version or row.get("profile") != model.profile:
            raise SystemExit("candidate registry provenance does not match its signed payload")
        active_id = registry.active_id()
        active = registry.get(active_id) if active_id and active_id != args.model_id else None
        champion_reports = None
        if active:
            champion_path = candidate_path(active["sha256"])
            if not champion_path.is_file() or hashlib.sha256(champion_path.read_bytes()).hexdigest() != active["sha256"]:
                raise SystemExit("current champion artifact is missing or invalid")
            champion_model = FidelityPredictor.load(champion_path)
            champion_reports, champion_hashes = _evaluation(champion_model)
            ExperimentRepo(sf).record("evaluation", f"promotion baseline {active['profile']}",
                {"sha256": active["sha256"], "suite_hashes": champion_hashes},
                {"reports": champion_reports}, profile=champion_model.profile, model_id=active["id"])
        reports, hashes = _evaluation(model)
        exp_repo = ExperimentRepo(sf)
        exp_repo.record("evaluation", f"promotion evaluation {row['profile']}",
            {"sha256": row["sha256"], "suite_hashes": hashes}, {"reports": reports},
            profile=model.profile, model_id=args.model_id)
        studies = exp_repo.list("policy_study", limit=200)
        passing_study = next((item for item in studies if item["model_id"] == args.model_id
            and item["config"].get("select_seeds") == [100, 101, 102, 103, 104]
            and item["config"].get("report_seeds") == [42, 43, 44, 45, 46]
            and item["config"].get("quick") is False
            and item["metrics"].get("gates", {}).get("G7") is True), None)
        evaluations = exp_repo.list("evaluation", limit=200)
        fresh = any(item["model_id"] == args.model_id and item["config"].get("sha256") == row["sha256"]
            and item["config"].get("suite_hashes") == hashes for item in evaluations)
        result = evaluate_gates(model, reports, champion_reports, g7=passing_study is not None, g8=fresh)
        result["reasons"] = {
            "G1": "signed format-v2 candidate; digest, signature, and sklearn version verified",
            "G2": "training r2_test >= 0.85 and eval overall/aerial MAE no worse than champion",
            "G3": "eval_v1 skill_vs_persistence > 0",
            "G4": "SLA 0.85 point_m0.01 false-feasible rate <= champion + 0.005",
            "G5": "calibrated models require alpha-0.10 eval coverage within [0.86, 0.94]",
            "G6": "batch-24 point p95 <= max(50 ms, 2 x champion p95)",
            "G7": "stored non-quick policy study with selection seeds 100–104 and report seeds 42–46 passes the champion comparison",
            "G8": "fresh stored evaluation has candidate SHA-256 and current ID/OOD suite hashes"}
        exp_id = exp_repo.record("evaluation", f"promotion gates for model {args.model_id}",
            {"sha256": row["sha256"], "suite_hashes": hashes}, result, profile=model.profile, model_id=args.model_id)
        if not result["pass"]:
            audit(sf, "model.promote", model_id=args.model_id, promoted=False, experiment_id=exp_id,
                failed_gates=[key for key, value in result["gates"].items() if not value])
            dump_report({"promoted": False, "experiment_id": exp_id, **result})
            raise SystemExit(2)
        if not args.yes:
            dump_report({"promoted": False, "dry_run": True, "model_id": args.model_id,
                "experiment_id": exp_id, "restart_required_after_apply": True, **result})
            return
        _install_artifact(source, model)
        previous = registry.promote(args.model_id, expected_sha256=row["sha256"])
        audit(sf, "model.promote", model_id=args.model_id, previous_id=previous,
            gates="G1..G8 ok", experiment_id=exp_id, promoted=True)
        dump_report({"promoted": True, "model_id": args.model_id, "previous_id": previous,
            "restart_required": True, "experiment_id": exp_id, **result})
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
