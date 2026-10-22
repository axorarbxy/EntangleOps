# Machine learning workbench

This folder holds standalone machine learning workflows, including training and evaluation CLIs, dataset tools, ML-specific tests, documentation, and generated model cards.

The production inference and API integration code remains in `backend/app/ml`, `backend/app/core`, `backend/app/services`, and `backend/app/api` because the running service imports those modules directly.

Run commands from `backend/`; the Makefile targets use the tools here. See [`docs/ML.md`](docs/ML.md) for workflows.

## SLATE-PTP delay model

The separate telemetry model predicts measured one-way PTP path delay in microseconds from the SLATE-PTP run conditions and the preceding five measurements of the same message type. Train it from the repository's `data/*.csv` tracks with:

```powershell
python machine_learning/scripts/train_slate_ptp_model.py
```

It writes the model to `machine_learning/models/` and the report and model card to `machine_learning/reports/`. It does not replace the simulator's Werner-fidelity predictor. Use `machine_learning.slate_ptp_model.predict_one_way_delay_us` to load and call the fitted model.

The **Models** page exposes this model as a PTP timing-run planner. Its authenticated `POST /api/v1/ml/ptp-delay` endpoint returns a one-way delay estimate for a selected run profile, with optional recent same-message measurements. The API container copies the artifact from `machine_learning/models/`; rebuild the backend image after retraining the model.
