install:
	pip install -r requirements-dev.txt
train:
	python scripts/train_predictor.py
run:
	uvicorn app.main:app --reload --port 8000 --no-access-log
test:
	pytest -q
bench:
	python scripts/run_benchmark.py
lint:
	ruff check .
monitoring-dashboard:
	python scripts/gen_dashboard.py
monitoring-secrets:
	python scripts/gen_monitoring_secrets.py
db-upgrade:
	python -m alembic -c ../database/alembic.ini upgrade head
db-check:
	python -m alembic -c ../database/alembic.ini check
db-backup:
	python scripts/backup_sqlite.py
db-keys:
	python scripts/manage_keys.py list
db-audit-verify:
	python scripts/verify_audit.py
db-dataset-build:
	python scripts/build_dataset.py build --name $(name)
ml-train:
	python scripts/ml_train.py $(ARGS)
ml-eval:
	python scripts/ml_eval.py $(ARGS)
ml-tune:
	python scripts/ml_tune.py $(ARGS)
ml-ablation:
	python scripts/ml_ablation.py $(ARGS)
ml-policy-study:
	python scripts/ml_policy_study.py $(ARGS)
ml-card:
	python scripts/ml_card.py $(ARGS)
ml-promote:
	python scripts/ml_promote.py $(ARGS)
test-ml:
	pytest -q tests/test_ml.py
monitoring-up:
	cd .. && docker compose --env-file backend/.env -f docker-compose.yml -f docker-compose.monitoring.yml up --build -d
monitoring-down:
	cd .. && docker compose --env-file backend/.env -f docker-compose.yml -f docker-compose.monitoring.yml down
