# EntangleOps database

The application now writes run state and per-step records to SQL. API keys (HMAC digests only), the append-only audit chain, benchmark results, WebSocket ticket nonces, model provenance, baselines, and reproducible datasets also have database tables. There is no in-memory run dictionary; only the worker semaphore, rate limiters, and WebSocket connection counters remain process-local.

## Layout

- `database/migrations/` is the Alembic schema history. Never create application tables with `Base.metadata.create_all()`.
- `backend/app/db/` contains the SQLAlchemy engine, models, migration runner, and repositories.
- SQLite is the development default: `EO_DATABASE_URL=sqlite:///./data/entangleops.db`. It uses WAL and foreign-key enforcement.
- Docker/production uses PostgreSQL 16 through `docker-compose.db.yml`. PostgreSQL is private to the internal `data` network; the API connects as `eo_app`, while the one-shot migration container alone receives `eo_owner` credentials.

## First run

From `backend/`, install `requirements.txt`, copy `.env.example` to `.env`, and run `python -m alembic -c ../database/alembic.ini upgrade head`. The app also upgrades automatically in development when `EO_DB_AUTO_MIGRATE=true`. In production, migrations are a separate job and startup fails if the schema is not at head.

For PostgreSQL, run `python backend/scripts/gen_db_secrets.py`, create `backend/.env` from the example, and start with `docker compose -f docker-compose.yml -f docker-compose.db.yml up --build`. Secret files are ignored by Git and are not committed. The compose flow has not been executed in this environment.

## Operations

- `python backend/scripts/manage_keys.py create --name ... --role ...` and `list`/`revoke` use the configured database.
- `python backend/scripts/verify_audit.py` verifies the full database audit chain.
- `python backend/scripts/build_dataset.py build --name <name>` creates a deterministic training dataset; `list`, `export`, `verify`, and `delete` operate on stored datasets.
- `python backend/scripts/train_predictor.py --from-dataset <id>` trains from a stored dataset and registers the signed model's metadata. Model bytes remain on disk at `EO_MODEL_PATH`.
- `python backend/scripts/backup_sqlite.py` uses SQLite's online backup API. PostgreSQL backups should use `pg_dump -Fc` from the database container.
- Legacy JSON files can be imported without deleting them with `python backend/scripts/import_legacy_files.py --data-dir ./data [--dry-run]`.

## Security and limits

The database stores only HMAC API-key hashes, never key secrets, peppers, signing keys, or ticket strings. Ticket nonces are persisted for single-use checks. The audit table has immutable update/delete triggers; the PostgreSQL runtime role gets SELECT/INSERT only. A database owner or superuser can still alter triggers and rows, so retain encrypted off-host backups.

Ownership is enforced in repository queries and returns the same not-found result for missing and foreign runs. A run's status and all its step rows commit atomically. On restart, stale queued/running jobs are marked `interrupted`. SQLite is for development/single-node use; shared PostgreSQL is the production path. Rate-limit buckets, worker semaphores, and per-key WebSocket connection counts remain process-local.

No PostgreSQL restore drill or storage-per-run measurement has been completed yet. These values should be recorded here after running against representative 24-hour runs before production rollout.
