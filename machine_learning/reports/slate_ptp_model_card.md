# SLATE-PTP one-way delay model

This model predicts measured one-way PTP path delay from the experiment conditions and normalized run progress. For `sync` rows, the target is `(t2 - t1)`; for `delay_req` rows, it is `(t4 - t3)`, converted from nanoseconds to microseconds.

It is a separate network telemetry model and does not replace EntangleOps' synthetic Werner-fidelity predictor. The target measurements come from the SLATE-PTP testbed; generalization beyond those captured configurations is not established. Validation holds out complete CSV runs.

- Training rows: 130,482 across 33 files
- Validation rows: 48,000 across 12 held-out files
- Validation MAE: 0.883114 µs (mean baseline 1.076462 µs)
- Validation RMSE: 1.243287 µs (mean baseline 1.518621 µs)
- Validation R²: 0.298313 (mean baseline -0.046887)
- Model artifact: `machine_learning/models/slate_ptp_delay_mlp.npz`
- Detailed report: `machine_learning/reports/slate_ptp_training_report.json`
