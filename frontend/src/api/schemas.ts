import { z } from 'zod';

export const Role = z.enum(['viewer', 'operator', 'admin', 'unknown']);
export const Me = z
  .object({ key_id: z.string(), name: z.string(), role: Role })
  .passthrough();
export const PtpDelayEstimate = z.object({
  predicted_delay_us: z.number(),
  model: z.string(),
  validation_mae_us: z.number(),
  validation_r2: z.number(),
  validation_rows: z.number(),
  validation_scope: z.string(),
  target: z.string(),
  history_count: z.number(),
});
export const LinkInfo = z
  .object({
    link_id: z.string().optional(),
    id: z.string().optional(),
    u: z.string(),
    v: z.string(),
    length_km: z.number(),
    aerial_fraction: z.number(),
    modes: z.number(),
    channels: z.number(),
  })
  .passthrough();
export const Topology = z
  .object({
    nodes: z.array(
      z.union([z.string(), z.object({ id: z.string() }).passthrough()]),
    ),
    links: z.array(LinkInfo),
  })
  .passthrough();
export const RunStatus = z
  .object({
    id: z.string(),
    status: z.enum(['queued', 'running', 'done', 'error']),
    created_at: z.string().optional(),
    error: z.string().nullable().optional(),
  })
  .passthrough();
export const Summary = z
  .object({
    policy: z.string(),
    total_requests: z.number(),
    admitted: z.number(),
    blocked: z.number(),
    block_rate: z.number(),
    sla_satisfied_pairs: z.number(),
    raw_pairs: z.number(),
    sla_efficiency: z.number(),
    violation_fraction: z.number(),
    mean_fidelity: z.number(),
    reroutes: z.number(),
    priority_weighted_useful_pairs: z.number(),
    peak_active: z.number(),
  })
  .passthrough();
export const Scenario = z
  .object({
    traffic_base: z.number().min(0).max(1).default(0.45),
    traffic_amp: z.number().min(0).max(0.5).default(0.3),
    traffic_peak_hour: z.number().min(0).lt(24).default(20),
    traffic_spike_count: z.number().int().min(0).max(20).default(4),
    traffic_spike_height: z.number().min(0).max(0.6).default(0.3),
    temp_mean_c: z.number().min(-30).max(45).default(18),
    temp_amp_c: z.number().min(0).max(20).default(8),
    temp_peak_hour: z.number().min(0).lt(24).default(15),
    wind_base_ms: z.number().min(0).max(20).default(3),
    storm_enabled: z.boolean().default(true),
    storm_center_h: z.number().min(0).max(48).default(15),
    storm_duration_h: z.number().gt(0).max(12).default(3),
    storm_wind_peak_ms: z.number().min(0).max(45).default(18),
    storm_temp_drop_c: z.number().min(0).max(20).default(6),
    arrival_rate_per_step: z.number().min(0).max(2).default(0.25),
    min_fidelity_choices: z
      .array(z.number().min(0.5).max(0.999))
      .min(1)
      .max(8)
      .default([0.8, 0.85, 0.88]),
    min_fidelity_weights: z
      .array(z.number().min(0).max(1))
      .min(1)
      .max(8)
      .default([0.4, 0.4, 0.2]),
    demand_choices_pairs_s: z
      .array(z.number().gt(0).max(1000))
      .min(1)
      .max(8)
      .default([20, 50, 100, 200]),
    mean_duration_steps: z.number().min(1).max(500).default(20),
  })
  .strict()
  .superRefine((s, ctx) => {
    if (
      s.min_fidelity_choices.length !== s.min_fidelity_weights.length ||
      s.min_fidelity_weights.reduce((a, b) => a + b, 0) <= 0
    )
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message:
          'Fidelity choices and weights must have the same length and a positive weight total',
      });
  });
export const SimRequest = z
  .object({
    policy: z.enum(['static_c', 'static_o', 'adaptive', 'adaptive_risk']).default('adaptive'),
    risk_alpha: z.union([z.literal(0.05), z.literal(0.1), z.literal(0.2)]).nullable().optional(),
    seed: z.number().int().min(0).max(2147483647).default(42),
    duration_hours: z.number().gt(0).max(48).default(24),
    dt_s: z.number().int().min(15).max(600).default(60),
    topology_preset: z.enum(['metro', 'tiny']).default('metro'),
    scenario: Scenario.default({}),
  })
  .strict();
export const BenchmarkRequest = z
  .object({
    seed: z.number().int().min(0).max(2147483647).default(42),
    duration_hours: z.number().gt(0).max(48).default(24),
    dt_s: z.number().int().min(15).max(600).default(60),
    topology_preset: z.enum(['metro', 'tiny']).default('metro'),
    scenario: Scenario.default({}),
  })
  .strict();
export const PredictRequest = z
  .object({
    length_km: z.number().min(0.1).max(200),
    aerial_fraction: z.number().min(0).max(1),
    band: z.enum(['C', 'O']),
    traffic_now: z.number().min(0).max(1),
    traffic_trend: z.number().min(-1).max(1),
    temp_now: z.number().min(-40).max(60),
    dtemp_dt_now: z.number().min(-50).max(50),
    wind_now: z.number().min(0).max(60),
    wind_trend: z.number().min(-60).max(60),
    hour: z.number().min(0).max(24),
    alpha: z.union([z.literal(0.05), z.literal(0.1), z.literal(0.2)]).optional(),
    wind_trend_15: z.number().min(-60).max(60).optional(),
    traffic_trend_15: z.number().min(-1).max(1).optional(),
    dtemp_trend_5: z.number().min(-100).max(100).optional(),
    wind_max_30: z.number().min(0).max(60).optional(),
    traffic_mean_30: z.number().min(0).max(1).optional(),
  })
  .strict();
export const PredictResult = z
  .object({ werner: z.number(), fidelity: z.number(), werner_lo: z.number().optional(), werner_hi: z.number().optional(), fidelity_lo: z.number().optional(), fidelity_hi: z.number().optional(), alpha: z.number().optional(), model_id: z.number().nullable().optional(), inputs_imputed: z.boolean().optional() })
  .passthrough();
export const RunSummaryResp = RunStatus.extend({
  config: SimRequest,
  summary: Summary.nullable(),
  error: z.string().nullable().optional(),
  owner: z.string().optional(),
  n_steps: z.number().int().optional(),
  dt_s: z.number().int().optional(),
}).passthrough();
export const LinkSnap = z
  .object({
    traffic: z.number(),
    temp_c: z.number(),
    wind: z.number().optional(),
    wind_ms: z.number().optional(),
    dtemp_dt: z.number(),
    utilization: z.number(),
    best_band_true: z.enum(['C', 'O']),
    fidelity_C: z.number(),
    fidelity_O: z.number(),
  })
  .passthrough()
  .transform((value) => ({
    ...value,
    wind_ms: value.wind_ms ?? value.wind ?? 0,
  }));
export const AllocSnap = z
  .object({
    request_id: z.number(),
    path: z.array(z.string()),
    bands: z.array(z.enum(['C', 'O'])),
    fidelity: z.number(),
    rate: z.number(),
    min_fidelity: z.number(),
    sla_ok: z.boolean(),
    priority: z.number().int(),
  })
  .passthrough();
export const StepRecord = z
  .object({
    step: z.number().int(),
    t_s: z.number(),
    active: z.number().int(),
    arrivals: z.number().int(),
    admitted: z.number().int(),
    blocked: z.number().int(),
    reroutes: z.number().int(),
    mean_fidelity: z.number().nullable(),
    useful_rate_pairs_s: z.number(),
    raw_rate_pairs_s: z.number(),
    sla_violations: z.number().int(),
    links: z.record(LinkSnap),
    allocations: z.array(AllocSnap),
  })
  .passthrough();
export const WsMessage = z.discriminatedUnion('type', [
  z
    .object({
      type: z.literal('hello'),
      run_id: z.string(),
      n_steps: z.number().int(),
      dt_s: z.number().int(),
    })
    .passthrough(),
  z.object({ type: z.literal('step'), data: StepRecord }).passthrough(),
  z.object({ type: z.literal('summary'), data: Summary }).passthrough(),
]);
export const Ticket = z
  .object({ ticket: z.string(), expires_in: z.number() })
  .passthrough();
export const KeyRow = z
  .object({
    key_id: z.string(),
    name: z.string(),
    role: Role,
    created_at: z.union([z.string(), z.number()]).optional(),
    expires_at: z.union([z.string(), z.number()]).nullable().optional(),
    revoked: z.boolean().optional(),
  })
  .passthrough();
export const AuditRow = z
  .object({
    ts: z.union([z.string(), z.number()]).optional(),
    event: z.string().optional(),
    kind: z.string().optional(),
    action: z.string().optional(),
    key_id: z.string().optional(),
  })
  .passthrough();
export const HealthDetails = z
  .object({
    status: z.string().optional(),
    checks: z.record(
      z.union([
        z.boolean(),
        z
          .object({ ok: z.boolean().optional(), detail: z.string().optional() })
          .passthrough(),
      ]),
    ),
    uptime_s: z.number().optional(),
    version: z.string().optional(),
    queue: z.unknown().optional(),
    audit_chain_ok: z.boolean().optional(),
  })
  .passthrough();
export const Crosscheck = z
  .object({ available: z.boolean().optional() })
  .passthrough();
export const Benchmark = z
  .object({
    id: z.string(),
    status: z.string(),
    created_at: z.string().optional(),
    config: z.unknown().optional(),
    results: z.record(z.unknown()).optional(),
    improvement: z.record(z.unknown()).optional(),
    error: z.string().nullable().optional(),
  })
  .passthrough();
export const MlModel = z.object({
  id: z.number(), profile: z.string(), status: z.string(), feature_schema: z.string(), target_mode: z.string(),
  horizon_steps: z.number(), sha256: z.string(), sklearn_version: z.string().nullable().optional(), trained_at: z.string(),
  metrics: z.record(z.number()), calibration: z.object({ method: z.string().optional(), alphas: z.array(z.string()), groups: z.array(z.string()), suite_sha256: z.string().nullable().optional(), n: z.record(z.number()) }).nullable(),
  card: z.unknown().nullable().optional(),
}).passthrough();
export const ExperimentRow = z.object({ id: z.string(), kind: z.string(), name: z.string(), profile: z.string().nullable(), model_id: z.number().nullable(), created_at: z.string(), code_version: z.string() }).passthrough();
export const ExperimentDetail = ExperimentRow.extend({ config: z.record(z.unknown()), metrics: z.record(z.unknown()), slices: z.record(z.unknown()).nullable() }).passthrough();
export type Role = z.infer<typeof Role>;
export type Me = z.infer<typeof Me>;
export type LinkInfo = z.infer<typeof LinkInfo>;
export type Topology = z.infer<typeof Topology>;
export type RunStatus = z.infer<typeof RunStatus>;
export type Summary = z.infer<typeof Summary>;
export type SimRequest = z.infer<typeof SimRequest>;
export type BenchmarkRequest = z.infer<typeof BenchmarkRequest>;
export type PredictRequest = z.infer<typeof PredictRequest>;
export type StepRecord = z.infer<typeof StepRecord>;
export type LinkSnap = z.infer<typeof LinkSnap>;
