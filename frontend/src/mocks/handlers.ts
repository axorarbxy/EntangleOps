import type { StepRecord } from '../api/schemas';

const nodes = ['A', 'B', 'C', 'D', 'E', 'F'];
const metro = [
  ['A', 'B', 30, 1],
  ['B', 'C', 30, 1],
  ['C', 'D', 22, 0.4],
  ['D', 'E', 30, 1],
  ['E', 'F', 28, 0.6],
  ['A', 'F', 24, 0.35],
  ['B', 'E', 34, 0.8],
  ['C', 'F', 42, 0.2],
  ['A', 'D', 38, 0.45],
].map(([u, v, length_km, aerial_fraction], i) => ({
  link_id: `L${i + 1}`,
  u: String(u),
  v: String(v),
  length_km: Number(length_km),
  aerial_fraction: Number(aerial_fraction),
  modes: 4,
  channels: 3,
}));
const scenario = {
  traffic_base: 0.45,
  traffic_amp: 0.3,
  traffic_peak_hour: 20,
  traffic_spike_count: 4,
  traffic_spike_height: 0.3,
  temp_mean_c: 18,
  temp_amp_c: 8,
  temp_peak_hour: 15,
  wind_base_ms: 3,
  storm_enabled: true,
  storm_center_h: 15,
  storm_duration_h: 3,
  storm_wind_peak_ms: 18,
  storm_temp_drop_c: 6,
  arrival_rate_per_step: 0.25,
  min_fidelity_choices: [0.8, 0.85, 0.88],
  min_fidelity_weights: [0.4, 0.4, 0.2],
  demand_choices_pairs_s: [20, 50, 100, 200],
  mean_duration_steps: 20,
};
const summary = (policy: string) => ({
  policy,
  total_requests: 74,
  admitted: 61,
  blocked: 13,
  block_rate: 0.17567567567567569,
  sla_satisfied_pairs: 1283.4208,
  raw_pairs: 1390.128,
  sla_efficiency: 0.9232,
  violation_fraction: 0.041,
  mean_fidelity: 0.901,
  reroutes: 14,
  priority_weighted_useful_pairs: 1502,
  peak_active: 16,
});
const sampleStep = (step: number): StepRecord => ({
  step,
  t_s: step * 300,
  active: 8,
  arrivals: 2,
  admitted: 2,
  blocked: 0,
  reroutes: 1,
  mean_fidelity: 0.91 - (stormAt(step) ? 1 : 0) * 0.05,
  useful_rate_pairs_s: 18.3,
  raw_rate_pairs_s: 20.2,
  sla_violations: 0,
  links: Object.fromEntries(
    metro.map((l, i) => [
      l.link_id,
      {
        traffic: 0.4 + i * 0.025,
        temp_c: 18,
        wind_ms: stormAt(step) ? 18 : 3,
        dtemp_dt: 0,
        utilization: 0.36 + i * 0.04,
        best_band_true: i % 2 ? 'O' : 'C',
        fidelity_C: 0.87,
        fidelity_O: 0.94,
      },
    ]),
  ),
  allocations: [],
});
function stormAt(step: number) {
  return step > 45 && step < 55;
}
const runs = [
  {
    id: 'demo-run-001',
    status: 'done',
    created_at: new Date(Date.now() - 3600000).toISOString(),
    error: null,
    config: {
      policy: 'adaptive',
      seed: 42,
      duration_hours: 24,
      dt_s: 300,
      topology_preset: 'metro',
      scenario,
    },
    summary: summary('adaptive'),
  },
];
const benchmarks = {
  id: 'demo-benchmark-001',
  status: 'done',
  config: {
    seed: 42,
    duration_hours: 24,
    dt_s: 300,
    topology_preset: 'metro',
    scenario,
  },
  results: {
    static_c: summary('static_c'),
    static_o: { ...summary('static_o'), sla_satisfied_pairs: 1192.2 },
    adaptive: summary('adaptive'),
  },
  improvement: {
    static_c: {
      sla_satisfied_pairs_pct: 11.4,
      violation_fraction_delta: -0.02,
    },
    static_o: {
      sla_satisfied_pairs_pct: 7.65,
      violation_fraction_delta: -0.01,
    },
  },
};

export async function demoResponse(
  path: string,
  method: string,
  body: unknown,
): Promise<unknown> {
  if (path === '/health/ready') return { status: 'ready' };
  if (path === '/api/v1/me')
    return { key_id: '0123456789ab', name: 'Demo operator', role: 'operator' };
  if (path.startsWith('/api/v1/topology'))
    return { nodes, links: path.includes('tiny') ? metro.slice(0, 3) : metro };
  if (path === '/api/v1/simulations' && method === 'GET')
    return runs.map(({ id, status, created_at, error }) => ({
      id,
      status,
      created_at,
      error,
    }));
  if (path === '/api/v1/simulations' && method === 'POST')
    return {
      id: 'demo-run-001',
      status: 'done',
      created_at: runs[0].created_at,
      error: null,
    };
  if (path === '/api/v1/simulations/demo-run-001') return runs[0];
  if (path === '/api/v1/simulations/demo-run-001/timeseries')
    return {
      step: Array.from({ length: 96 }, (_, i) => i),
      t_s: Array.from({ length: 96 }, (_, i) => i * 900),
      useful_rate_pairs_s: Array.from(
        { length: 96 },
        (_, i) => 18.3 - (stormAt(i) ? 1 : 0) * 2,
      ),
      mean_fidelity: Array.from(
        { length: 96 },
        (_, i) => 0.91 - (stormAt(i) ? 1 : 0) * 0.05,
      ),
    };
  if (path === '/api/v1/benchmarks' && method === 'GET') return [benchmarks];
  if (path === '/api/v1/benchmarks' && method === 'POST')
    return { id: benchmarks.id, status: 'done' };
  if (path === '/api/v1/benchmarks/demo-benchmark-001') return benchmarks;
  if (path === '/api/v1/predict') return { werner: 0.92, fidelity: 0.94 };
  if (path === '/api/v1/ml/model') return { id: 1, profile: 'baseline_v1', status: 'champion', feature_schema: 'v1', target_mode: 'direct', horizon_steps: 5, sha256: 'demo-model-digest', sklearn_version: '1.x', trained_at: new Date().toISOString(), metrics: { r2_test: 0.9, mae_test: 0.01 }, calibration: null, card: null };
  if (path === '/api/v1/ml/ptp-delay') return { predicted_delay_us: 8.14, model: 'SLATE-PTP one-way delay MLP', validation_mae_us: 0.8831137, validation_r2: 0.298313, validation_rows: 48000, validation_scope: '12 held-out SLATE-PTP CSV runs', target: 'sync: t2 − t1; delay_req: t4 − t3', history_count: (body as { recent_same_message_delays_us?: number[] } | undefined)?.recent_same_message_delays_us?.length ?? 0 };
  if (path === '/api/v1/ml/experiments') return [];
  if (path.startsWith('/api/v1/ml/experiments/')) return { id: path.split('/').at(-1), kind: 'evaluation', name: 'Demo evaluation', profile: 'baseline_v1', model_id: 1, created_at: new Date().toISOString(), code_version: 'demo', config: {}, metrics: {}, slices: {} };
  if (path === '/api/v1/ws-ticket')
    return { ticket: 'demo-single-use-ticket', expires_in: 30 };
  if (path === '/api/v1/admin/keys' && method === 'GET') return [];
  if (path === '/api/v1/admin/keys' && method === 'POST')
    return {
      key: 'eo_0123456789ab.abcdefghijklmnopqrstuvwx',
      key_id: '0123456789ab',
      warning: 'Demo key',
    };
  if (path.startsWith('/api/v1/admin/keys/')) return { status: 'revoked' };
  if (path.startsWith('/api/v1/admin/audit')) return [];
  if (path === '/api/v1/admin/health/details')
    return {
      status: 'ok',
      uptime_s: 3600,
      version: 'demo',
      queue: { capacity: 10, depth: 0 },
      checks: {
        predictor_loaded: true,
        data_dir_writable: true,
        audit_chain_ok: true,
      },
    };
  if (path.startsWith('/api/v1/crosscheck'))
    return { available: false, note: 'SeQUeNCe not available in demo data' };
  if (path === '/api/v1/simulations/demo-run-001/steps')
    return Array.from({ length: 96 }, (_, i) => sampleStep(i));
  if (method === 'POST' && path === '/api/v1/simulations')
    return {
      id: 'demo-run-001',
      status: 'done',
      created_at: new Date().toISOString(),
    };
  void body;
  throw new Error('This endpoint is not included in the demo fixture set');
}
