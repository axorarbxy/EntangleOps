# Machine learning workbench

This folder holds standalone machine learning workflows, including training and evaluation CLIs, dataset tools, ML-specific tests, documentation, and generated model cards.

The production inference and API integration code remains in `backend/app/ml`, `backend/app/core`, `backend/app/services`, and `backend/app/api` because the running service imports those modules directly.

Run commands from `backend/`; the Makefile targets use the tools here. See [`docs/ML.md`](docs/ML.md) for workflows.
