# EntangleOps security

## Threat protections

The control plane uses expiring, revocable API keys stored as peppered HMAC digests; viewer, operator, and admin roles; per-owner result access; in-memory token-bucket limits and run quotas; strict input bounds; request body limits; signed model artifacts verified before deserialization; single-use WebSocket tickets; security headers; and a hash-chained audit log. Production startup rejects missing/short secrets, identical secrets, wildcard/empty CORS allowlists, and body limits over 1 MiB. Configure `EO_CORS_ORIGINS`, `EO_API_KEY_PEPPER`, and `EO_MODEL_SIGNING_KEY` independently before setting `EO_ENV=production`.

## API role matrix

| Endpoint | Minimum role |
|---|---|
| `GET /api/v1/me`, `GET /api/v1/topology`, `POST /api/v1/predict`, simulation and benchmark reads, `POST /api/v1/ws-ticket` | viewer |
| `POST /api/v1/simulations`, `POST /api/v1/benchmarks` | operator |
| `GET /api/v1/ml/model`, `GET /api/v1/ml/experiments`, `GET /api/v1/ml/experiments/{id}` | viewer |
| `GET/POST/DELETE /api/v1/admin/keys`, `GET /api/v1/admin/audit`, `GET /api/v1/admin/health/details`, `GET /api/v1/crosscheck` | admin |

## Deployment

Run the backend behind the supplied Caddy TLS proxy. Set `EO_TRUSTED_PROXY_COUNT=1` and `EO_BEHIND_TLS=true` when exactly one trusted proxy precedes the app. Manage credentials with `python scripts/manage_keys.py create --name operator --role operator`; the API key is printed once. Verify the audit chain with `python scripts/verify_audit.py`. The Docker image runs non-root, has a read-only root filesystem, drops capabilities, and does not bake model signing secrets into the image.

## Honest limits

- Rate limits, WebSocket counters, and used-ticket tracking are in-memory and per-process. Multiple instances require a shared store such as Redis; that is not included.
- API keys are shared secrets with roles, not user accounts. There is no SSO, MFA, or per-user identity beyond the key.
- The audit hash chain detects edits and reordered entries, but cannot prevent deleting the whole log. Ship it to external append-only storage in production.
- The model signature uses a symmetric key. Anyone holding it can sign a malicious model; protect and rotate it like a root credential.
- ML experiments are append-only in the database; model candidates are signed artifacts addressed by SHA-256. Promotion runs a fail-closed evaluation gate and requires an application restart so the serving process loads the new champion.
- The simulation uses illustrative physics. Nothing here provides a quantum-security guarantee; this protects the control plane software, not a quantum channel.
- This layer has not been penetration-tested and is a baseline, not a certification.

## TLS and post-quantum note

Caddy terminates TLS and renews certificates for a public domain. The deployment spec suggests hybrid X25519 and ML-KEM key exchange for recent Caddy/Go TLS releases; this environment has no installed Caddy binary or release notes, so that capability has not been verified and is not claimed here.

## Reporting a vulnerability

Contact: **[security contact to be supplied by the project team]**. Please include a clear reproduction and avoid public disclosure until the team has had a chance to respond.
