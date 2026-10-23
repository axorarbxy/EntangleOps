# EntangleOps Console

## Run locally

Use Node 20 or newer. From this directory run `npm ci` and `npm run dev`. Vite serves the console on port 5173 and proxies `/api`, `/health`, and `/ws` to the backend at `http://localhost:8000`.

The backend development environment must allow the Vite origin:

```dotenv
EO_CORS_ORIGINS=["http://localhost:5173"]
EO_WS_ALLOWED_ORIGINS=["http://localhost:5173"]
```

Copy `.env.example` to `.env` only if overriding public frontend settings. `VITE_*` values are bundled into the browser and must never contain secrets. The API key is requested at login and kept in memory unless “Keep me signed in for this tab” is selected.

## Demo and deployment

`npm run dev:demo` enables a demo banner while using the real API and WebSocket through the Vite proxy. Start the local backend and persistent SQLite demo database first with `backend/scripts/demo.ps1` (see the root README), then create a local operator key with `backend/scripts/demo.ps1 -Action create-key` and enter it in the UI. The database is kept at `backend/data/demo/entangleops.db` and survives restarts. `npm run dev:fixtures` explicitly selects offline synthetic frontend fixtures and does not use the backend or database.

Demo fixtures can be captured with `EO_API_BASE` and `EO_API_KEY` supplied as shell environment variables using `npm run capture-fixtures`. `npm run contract` validates selected API responses against a live backend. Build with `npm run build`; production deployment is through the root Docker Compose stack, where Caddy serves the frontend and proxies API and WebSocket paths to the backend. The Caddy `/metrics` route remains private.

Configure `VITE_GRAFANA_URL` at build time if admins should see a Grafana dashboard link. For production, configure exact `EO_CORS_ORIGINS` and `EO_WS_ALLOWED_ORIGINS` values for the deployed origin.

## Honest limits

- API keys are bearer secrets held in browser memory. A cross-site-scripting bug would expose them; the strict CSP, no third-party code and no HTML injection are mitigations. A backend-for-frontend with `HttpOnly` sessions would be stronger and is not included.
- UI role gating is a convenience; only the backend enforces access. Keys are shared secrets, not user accounts (no SSO/MFA).
- Everything displayed comes from a **simulated digital twin with illustrative physics**. It is not a measurement of real hardware, not a performance guarantee, and not a quantum-security guarantee.
- Replay buffers run records in browser memory. Closing the tab discards it; reopening re-streams (one WebSocket ticket per attempt, max 3 streams per key).
- Benchmark history is stored by the backend database and loaded from `GET /api/v1/benchmarks`; the selected benchmark id is kept per browser tab for convenience.
- Compare lab and seed sweeps use several runs; with default quotas they execute partly sequentially and can take minutes.
- Fixture mode shows synthetic frontend-only data. Connected demo mode uses the local backend and persistent database, but its simulated network results are still illustrative and are not live hardware measurements.
- This frontend has not been penetration-tested or accessibility-audited by an external party; treat it as a strong baseline, not a certification.
