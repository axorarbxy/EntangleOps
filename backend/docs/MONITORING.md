# EntangleOps monitoring

The monitoring package and stack live in `../monitoring`, beside `backend` and `security`. The FastAPI application exposes token-protected Prometheus metrics, JSON request logs, health endpoints, simulation and predictor telemetry, and audit-chain checks. Metrics describe the simulated digital twin; they are not physical network measurements.

## Start the stack

1. From `R:\QCN`, run `python backend/scripts/gen_monitoring_secrets.py` and put the printed `EO_METRICS_TOKEN=...` line in `backend/.env`.
2. Set `GRAFANA_ADMIN_PASSWORD` in `backend/.env`.
3. Start with `docker compose --env-file backend/.env -f docker-compose.yml -f docker-compose.monitoring.yml up --build -d`.

Prometheus is at `http://127.0.0.1:9090`, Alertmanager at `http://127.0.0.1:9093`, and Grafana at `http://127.0.0.1:3000` (user `admin`). The Caddy listener returns 404 for `/metrics`; Prometheus reaches it over the internal Compose network. Regenerate the provisioned dashboard with `python backend/scripts/gen_dashboard.py`.

## Health

`GET /health/live` and legacy `GET /health` report liveness. `GET /health/ready` returns only a ready/not-ready status and HTTP 200/503. Admins can inspect checks at `GET /api/v1/admin/health/details`. The Docker health check uses `/health/live`.

## Metric catalog

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `eo_build_info` | gauge | version, env | Build identity |
| `eo_http_requests_total` | counter | method, route, status_class | Requests by route template and status family |
| `eo_http_request_duration_seconds` | histogram | method, route | Request latency |
| `eo_http_in_flight` | gauge | — | Active HTTP requests |
| `eo_event_loop_lag_seconds` | histogram | — | Event-loop scheduling delay |
| `eo_runs_total` | counter | kind, policy, status | Finished simulations and benchmarks |
| `eo_run_duration_seconds` | histogram | kind, policy | Run wall time |
| `eo_runs_active` | gauge | state | Queued and running work |
| `eo_queue_depth` | gauge | — | Waiting run count |
| `eo_queue_capacity` | gauge | — | Configured queue capacity |
| `eo_runs_stored` | gauge | — | Stored run records |
| `eo_sim_steps_total` | counter | policy | Steps executed |
| `eo_sim_requests_total` | counter | policy, outcome | Admitted or blocked requests |
| `eo_sim_reroutes_total` | counter | policy | Rerouted allocations |
| `eo_sim_sla_violations_total` | counter | policy | Allocation-steps below requested fidelity |
| `eo_sim_useful_pairs_total` | counter | policy | SLA-satisfied pairs |
| `eo_sim_raw_pairs_total` | counter | policy | All delivered pairs |
| `eo_sim_active_allocations` | gauge | policy | Active allocations at latest step |
| `eo_sim_sla_efficiency` | gauge | policy | Useful/raw pairs for latest completed run |
| `eo_benchmark_improvement_pct` | gauge | baseline | Adaptive service improvement over baseline |
| `eo_link_fidelity` | gauge | policy, link_id, band | Latest simulated link fidelity |
| `eo_link_utilization` | gauge | policy, link_id | Latest simulated channel utilization |
| `eo_predictor_mae` | gauge | — | EWMA shadow prediction error |
| `eo_predictor_abs_error` | histogram | — | Shadow prediction error distribution |
| `eo_predictor_out_of_range_ratio` | gauge | — | Sampled features outside training range |
| `eo_predictor_loads_total` | counter | result | Predictor load/retrain outcomes |
| `eo_auth_failures_total` | counter | reason | Authentication failures |
| `eo_rate_limited_total` | counter | scope | Rate-limit rejections |
| `eo_run_denied_total` | counter | reason | Denied run operations |
| `eo_ws_connections` | gauge | — | Active WebSocket connections |
| `eo_ws_denied_total` | counter | reason | WebSocket denials |
| `eo_model_verify_failures_total` | counter | — | Model signature failures |
| `eo_audit_events_total` | counter | kind | Allowlisted audit event types |
| `eo_audit_chain_ok` | gauge | — | 1 valid, 0 broken, -1 not yet checked |
| `eo_audit_entries` | gauge | — | Entry count at last chain verification |

Process, platform, and GC collectors are also registered. Labels are bounded to fixed allowlists, route templates, and known topology link IDs. IDs, API keys, addresses, paths, request bodies, and secrets are never metric labels.

## Alerts and operations

Prometheus loads `monitoring/alerts.yml`; placeholder predictor thresholds are `0.03` MAE and `0.2` out-of-range ratio. They are not measured baselines. Run `python backend/scripts/measure_baseline.py` after dependencies are installed and review the results before setting alert thresholds. Do not interpret a placeholder as a service-level guarantee. Alertmanager currently uses a no-op receiver; alerts display in the UI, but no notification is delivered until a real receiver is configured.

For scrape failures, check backend readiness, the metrics token match between `backend/.env` and `monitoring/secrets/metrics_token`, and Prometheus target status. For audit-chain alerts, preserve the audit log and investigate before replacing it. For predictor drift, inspect out-of-range ratio and compare with a newly measured baseline before retraining.

## SLO starting points

The bundled rules provide initial operational signals only: request p95 under two seconds, server error ratio under five percent, and a queue below configured capacity. These are not measured commitments. Establish workload-specific objectives from production observations before treating them as SLOs.

## Honest limits

- The registry is per process. Multiple workers or replicas need multiprocess mode or per-instance scraping; this deployment assumes one process.
- Link and active-allocation gauges are last-writer-wins when same-policy runs overlap; counters and histograms are unaffected.
- Entanglement telemetry describes the simulated digital twin, not physical hardware.
- Predictor drift is shadow evaluation against simulated environments; real deployments need ground truth from actual link telemetry.
- Audit verification re-reads the whole log each interval; very large logs need incremental verification.
- Prometheus keeps 15 days of local data without backup. The default Alertmanager receiver sends nothing until configured.
- The generated token file uses mode 0644 so Prometheus can read it; tighten permissions on shared hosts.
- Access logs contain client IPs and key IDs; define an appropriate retention policy.
- Grafana's admin password comes from `backend/.env`; change it before use and consider SSO before exposing Grafana beyond localhost.
- Monitoring detects and reports problems; it does not prevent them and has not been load-tested at scale.

## Configuration

Monitoring settings use the `EO_` environment prefix: `EO_METRICS_ENABLED`, `EO_METRICS_TOKEN`, `EO_LOG_LEVEL`, `EO_LOG_JSON`, `EO_SLOW_REQUEST_S`, `EO_DRIFT_SAMPLE_EVERY_STEPS`, `EO_DRIFT_EWMA_ALPHA`, `EO_AUDIT_VERIFY_INTERVAL_S`, `EO_LOOP_LAG_INTERVAL_S`, `EO_OTEL_ENABLED`, and `EO_OTEL_ENDPOINT`. OpenTelemetry is optional and not installed by this package.
