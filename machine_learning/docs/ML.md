# EntangleOps machine learning workbench

The ML package forecasts link Werner fidelity inside the illustrative network simulator. Every training label and evaluation trace is synthetic physics output; results do not describe a physical deployment or provide a quantum-security guarantee.

## Layout and runtime

- `machine_learning/scripts/`, `machine_learning/tests/`, and `machine_learning/docs/` contain the standalone ML workflows, tests, and documentation. The production ML package remains in `backend/app/ml/`, with backend integration in `backend/app/`.
- `app/core/predictor.py` preserves the original `baseline_v1` row builder and prediction API. The serving model remains `EO_MODEL_PATH` (default `./data/predictor.joblib`); SHA-addressed signed candidates live under `EO_ML_MODELS_DIR` (default `./data/models`). Both locations must be on persistent storage.
- `model_artifacts` tracks candidates/champions/retired artifacts; `ml_experiments` stores append-only reproducibility evidence. `EO_MODEL_SIGNING_KEY` must be stable and at least 32 characters in production. Never rotate it without re-signing trusted artifacts.
- The active model is loaded at process startup. Promotion requires a restart; it does not hot-reload a running worker.

For a local first run, set a stable signing key before starting the API or running ML scripts (for example, generate one with `python -c "import secrets; print(secrets.token_hex(32))"` and put it in the untracked `backend/.env`). Development startup can create a legacy baseline model when `EO_MODEL_PATH` is absent; it signs and registers that model using the configured key. Keep `EO_MODEL_PATH`, `EO_ML_MODELS_DIR`, and the database on persistent storage. Trained candidate model binaries and signing sidecars are intentionally git-ignored.

## Reproducible workflow

From `backend/`, install `requirements-dev.txt`, copy `.env.example` to `.env`, and configure one stable `EO_MODEL_SIGNING_KEY` before training.

```powershell
python ../machine_learning/scripts/ml_train.py --profile hgb_residual_v1 --n-scenarios 24 --calibrate --evaluate
python ../machine_learning/scripts/ml_eval.py --model-id 2 --suites eval_v1,ood_v1 --store
python ../machine_learning/scripts/ml_tune.py --profile hgb_residual_v1 --n-iter 12 --store
python ../machine_learning/scripts/ml_ablation.py --n-scenarios 24 --store
python ../machine_learning/scripts/ml_policy_study.py --model-id 2 --workers 4 --gate-check
python ../machine_learning/scripts/ml_card.py --model-id 2 --suite eval_v1 --store --output ../machine_learning/docs/model_cards/model-2.md
python ../machine_learning/scripts/ml_promote.py --model-id 2
python ../machine_learning/scripts/ml_promote.py --model-id 2 --yes
python ../machine_learning/scripts/ml_promote.py --rollback --yes
```

Use a candidate ID reported by training. The policy study uses separate selection and report seeds by default; `--quick` is for iteration only and should not be used as promotion evidence. Candidate training never changes the active model. Promotion records gate results, verifies the signature and digest, stages the file, switches the champion, then requires an application restart.

## Gates and limits

Promotion requires (G1) signed, digest-matching format-v2 provenance; (G2) training `r2_test >= 0.85` and ID overall/aerial MAE no worse than the champion; (G3) positive ID skill against physics persistence; (G4) SLA 0.85 point-with-0.01-margin false-feasible rate no more than champion + 0.005; (G5) calibrated candidates have α=0.10 ID coverage in [0.86, 0.94]; (G6) batch-24 point p95 no greater than `max(50 ms, 2 × champion p95)`; (G7) the stored 100–104 selection / 42–46 report policy study meets the champion throughput/violation bounds; and (G8) a stored evaluation matches the model digest and current suite hashes. The first invocation prints a dry-run report; `--yes` applies a passing promotion or rollback and cannot override failed gates. Missing evidence fails closed.

The feature-schema v2 extras accepted by `/api/v1/predict` are imputed when omitted; the response marks `inputs_imputed`. Adaptive-risk simulation requires calibrated lower prediction bounds and stores its selected alpha in the run config. Risk-policy benchmarks are reported as distinct `adaptive_risk_0.05`, `adaptive_risk_0.1`, and `adaptive_risk_0.2` result rows. Existing run response shapes and baseline prediction output stay compatible.

`GET /api/v1/ml/model` and `/api/v1/ml/experiments[/{id}]` are viewer-readable. No training, reload, or promotion endpoint is exposed over HTTP. The browser Models page reports stored evidence; it does not invent results when evaluation has not run.

## Validation and reproducibility

Run `pytest -q ../machine_learning/tests/test_ml.py tests/test_api.py`, then the full backend suite. Run `npm run lint`, `npm run typecheck`, `npm test`, and `npm run build` in `frontend/`. `alembic check` should report no model/schema drift after upgrading to head. PostgreSQL role grants and migration behavior must be verified against a real PostgreSQL instance; local SQLite validation does not establish PostgreSQL readiness.

Evaluation reports include ID/OOD suite hashes, overall and feature-slice metrics, physics-persistence and constant-mean baselines, decision false-feasible/false-reject/path-MAE rates, 10-bin reliability, interval coverage/width, point and interval latency, permutation importance, and partial dependence. Policy-study paired differences are descriptive; no statistical-significance claim is made. Alert thresholds are provisional until `python scripts/measure_baseline.py --ml --store` is run and reviewed.

## Measured synthetic smoke result

An isolated smoke run trained `hgb_residual_v1` with 2 training scenarios, horizon 5 and seed 0, then evaluated `eval_v1` (8 scenarios, 36,736 rows). Training measured R² 0.96715 and held-out MAE 0.01350 Werner; the signed artifact loaded and its evaluation experiment was stored. A separate calibrated candidate also trained and registered successfully. This confirms workflow execution, not promotion readiness: OOD evaluation, the seeded adaptive-risk policy study, champion-relative gates, PostgreSQL behavior, and measured monitoring thresholds have not yet been verified in this environment. Do not treat this small synthetic training score as real-network performance.
