# EntangleOps Backend

EntangleOps is a FastAPI control plane for simulating a metro quantum network sharing fiber with classical traffic. Its analytic physical constants are illustrative and are not calibrated to any specific experiment.

## Run

Install Python 3.11+, then `pip install -r requirements-dev.txt`. Start with `uvicorn app.main:app --reload --port 8000`. The API documentation is at `/docs`.

Create a run with `POST /api/v1/simulations`, poll `/api/v1/simulations/{id}`, and retrieve its time series at `/api/v1/simulations/{id}/timeseries`. `POST /api/v1/benchmarks` compares the three policies on the same seeded environment and request set. Optional SeQUeNCe cross-check support is a safe unavailable stub until a verified adapter is implemented.

## Development

Use `make install`, `make test`, `make train`, `make bench`, and `make lint`. API routes require an `X-API-Key`; create an initial admin credential with `python scripts/manage_keys.py create --name admin --role admin` after setting `EO_API_KEY_PEPPER`. Review [docs/SECURITY.md](docs/SECURITY.md) for production secrets, roles, TLS setup, and known limits. Docker Compose serves the API through Caddy on ports 80 and 443.
