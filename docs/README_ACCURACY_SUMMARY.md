# README accuracy summary

## Evidence inspected

The README was based on the repository tree and source, not only the existing module READMEs. Inspected dependency manifests and lockfiles; backend config, entrypoint, API routes and schemas; frontend navigation, API client, login and build/test configuration; SQLAlchemy models and Alembic migrations; ML scripts/docs/reports/artifact; security and monitoring code/config; Dockerfiles and Compose overlays; tests; GitHub Actions workflows; `.gitignore`; and Git's tracked-file list for license/screenshots.

## Features confirmed in code

| Feature                                                                                       | Evidence                                                                                   | Status                                                                                  |
| --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------- |
| Metro/tiny topology, analytic C/O link physics, seeded simulator and allocation policies      | `backend/app/core/`, schemas, routes, and tests                                            | Implemented; physical constants remain illustrative                                     |
| Simulation/benchmark API, owner-scoped reads, SQL persistence and replay                      | `backend/app/api/`, `backend/app/services/runner.py`, `backend/app/db/`                    | Implemented in code; runs execute in-process                                            |
| API-key roles and security controls                                                           | `security/`, route dependencies, security tests                                            | Implemented; shared keys, no SSO/MFA                                                    |
| Werner-fidelity ML features, train/evaluate/governance CLI, registry and calibrated risk mode | `backend/app/ml/`, `machine_learning/scripts/`, migrations, API                            | Mixed: runtime and CLI exist; browser page is read-only; no HTTP promotion/training     |
| SLATE-PTP one-way delay estimate                                                              | `machine_learning/slate_ptp_model.py`, `.npz` artifact, ML route, Models page, report/card | Implemented endpoint; generalization is limited to available held-out runs              |
| PostgreSQL/SQLite schema and database-backed repositories                                     | `database/migrations/`, `backend/app/db/`                                                  | Implemented; host path bug noted below                                                  |
| Prometheus metrics, dashboards, health checks, periodic checks and alerts                     | `monitoring/`, FastAPI lifespan and Compose overlay                                        | Implemented configuration; alert receiver is placeholder and thresholds are provisional |
| SeQUeNCe adapter                                                                              | `backend/app/core/sequence_adapter.py`                                                     | Not implemented; stub always returns unavailable                                        |

## Important unknowns and inconsistencies

- No root README existed before this deliverable. The backend/database/ML READMEs are useful but contain stale setup/environment notes; for example, the database README says Compose has not been executed, while a Compose stack was started and health checked during earlier work in this workspace.
- `backend/app/db/migrate.py::_config()` uses `Path(__file__).resolve().parents[2]`. In the current host checkout this points to `backend/`, so the ML SQLite tests fail with `No 'script_location' key found in configuration.` In the container image the copied layout makes the same index point to `/app`, so the Compose migration job can find `/app/database/alembic.ini`. This is an actual code portability inconsistency, not a README claim.
- `.github/workflows/security.yml` invokes `pytest -q backend/tests/test_ml.py`; that path does not exist. The ML test file is `machine_learning/tests/test_ml.py`.
- Backend docs refer to `backend/.env.example`, but that file is not tracked. Frontend has no `.env.example` either.
- `backend/docs/MONITORING.md` says `GRAFANA_ADMIN_PASSWORD` belongs in `backend/.env`; the Compose variable interpolation is rooted at the repository `.env` unless a different `--env-file` is passed.
- The PTP report/card documents metrics and held-out runs, but no provenance citation/contact information is present in the inspected repository.
- No tracked screenshots, root license, live demo, release metadata, or maintainer contact endpoint was found.

## Test execution results observed during this documentation pass

- Frontend ESLint: passed.
- Frontend TypeScript check: passed.
- Frontend Vitest: 4 files, 11 tests passed.
- Frontend production build: passed.
- Backend physics unit tests: 2 passed.
- ML tests: 5 passed, 2 failed on host due the migration config path bug above.
- Full backend test run: attempted but did not produce a final result before interruption; do not treat it as passed.
- Earlier runtime check of the current Compose configuration: migration reported head `0002`, backend health was `healthy`, and app root plus `/health/live` returned 200. This is a local smoke check, not a CI or production readiness result.
- Full security CI, npm audit, browser E2E, PostgreSQL restore drill, penetration/load tests: not run in this pass.

## Documentation improvements still recommended

1. Add tracked `backend/.env.example` and frontend configuration examples that contain placeholders only.
2. Correct the host/container migration path resolution and use one canonical migration command in docs and CI.
3. Correct the ML test path in the security workflow.
4. Reconcile the database and monitoring READMEs with the current Compose env-file and migration flow.
5. Add project-approved licensing, data/model citations, security contact, and authentic screenshots when maintainers provide them.
