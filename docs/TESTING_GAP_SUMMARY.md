# Testing gap summary

This report separates existing coverage from proposed coverage. A test file existing does not mean it passed. Results from the current documentation pass are listed in [README accuracy summary](README_ACCURACY_SUMMARY.md).

## Priority gaps

### P0 — Resolve before relying on CI or database migration checks

- **Migration config resolution:** host ML tests fail in `backend/app/db/migrate.py::_config()` because its calculated path does not contain `database/alembic.ini`. Make root discovery work for both the repository checkout and the flattened Docker image, then run the database/ML/backend tests in both contexts.
- **Broken CI test target:** `.github/workflows/security.yml` calls `backend/tests/test_ml.py`, which is absent. Point CI at `machine_learning/tests/test_ml.py` and require it to complete.
- **PostgreSQL role/migration integration:** use a disposable fresh PostgreSQL volume to verify both Alembic revisions, `eo_app` table/sequence privileges, schema-version reads, audit triggers, app startup, persistence, and clean restart. A SQLite test does not establish these PostgreSQL properties.

### P1 — Improve functional and authorization confidence

- Add route-by-route tests for viewer/operator/admin permissions, especially benchmarks, PTP inference, key revocation, audit, health details, and WebSocket ticket issuance/replay.
- Add benchmark owner-scoping tests alongside the existing run ownership test.
- Add API tests for compute-budget rejection, queue exhaustion, duplicate/invalid inputs, response codes, and database-unavailable handling.
- Add PTP endpoint tests for valid profiles, recent-history bounds, malformed inputs, and missing/corrupt model artifact behavior.
- Add browser interaction tests for login, session expiration, role-filtered navigation, form validation, loading/empty/error states, and run replay.
- Add a real browser end-to-end test. The `npm run e2e` script exists, but no tracked Playwright config or test specs were found. The `npm run contract` script exercises the live API and is not browser E2E.
- Add migration-upgrade tests from supported prior revisions and PostgreSQL backup/restore drills.

### P2 — Operational and long-term assurance

- Add keyboard/accessibility and responsive viewport checks for the console.
- Add workload tests for long simulations, concurrent run quotas, SQL pool limits, slow clients, and process restart recovery.
- Add an end-to-end alert delivery test after replacing the placeholder Alertmanager receiver.
- Add model artifact provenance/data citation checks and broader out-of-domain validation before treating ML results as operational evidence.
- Add secret-rotation, dependency update, and documented recovery exercises.

## Existing suites

| Area               | Files/purpose                                                                  | Current documented command                                               |
| ------------------ | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------ |
| Backend            | API, persistence, physics, topology, policies, predictor, security, monitoring | From `backend/`: `pytest -q tests`                                       |
| ML                 | Feature/data determinism, calibration/cache, experiment/registry gate          | From `backend/`: `pytest -q ../machine_learning/tests/test_ml.py`        |
| Frontend           | API adapters/schemas, budget and physics helpers                               | From `frontend/`: `npm test`                                             |
| Static checks      | Ruff, Bandit, pip-audit, ESLint, TS compiler, npm audit, Gitleaks              | See `.github/workflows/*.yml`                                            |
| API contract smoke | Auth, topology, short run, summary and time series                             | From `frontend/`: `npm run contract` with `EO_API_BASE` and `EO_API_KEY` |
| Prometheus rules   | Alert rule syntax                                                              | CI uses `promtool check rules` in a Prometheus container                 |

## Commands recommended before release

Run backend and ML checks from `backend/` after fixing migration path discovery:

```bash
python -m pip install -r requirements-dev.txt
pytest -q tests
pytest -q ../machine_learning/tests/test_ml.py
ruff check .
python -m alembic -c ../database/alembic.ini upgrade head
python -m alembic -c ../database/alembic.ini check
```

Run frontend quality checks from `frontend/`:

```bash
npm ci
npm run lint
npm run typecheck
npm test
npm run build
npm audit --audit-level=high
```

Then, in an isolated environment with generated test-only secrets and a disposable database:

```bash
docker compose -f docker-compose.yml -f docker-compose.db.yml -f docker-compose.monitoring.yml up --build -d
```

Verify the migration job exits successfully, backend is healthy, create a temporary test API key, run the API contract check and browser journey, inspect Prometheus target/alerts, and perform a backup/restore drill. Do not run destructive database reset commands against a shared or production volume.
