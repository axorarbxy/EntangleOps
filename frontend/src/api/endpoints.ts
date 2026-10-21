import { z } from 'zod';
import { request } from './client';
import * as S from './schemas';
import { normalizeTimeseries } from './adapters';
export const me = () => request('/api/v1/me', { schema: S.Me });
export const topology = (preset = 'metro') =>
  request(`/api/v1/topology?preset=${encodeURIComponent(preset)}`, {
    schema: S.Topology,
  });
export const predict = (body: S.PredictRequest) =>
  request('/api/v1/predict', { method: 'POST', body, schema: S.PredictResult });
export const createRun = (body: z.input<typeof S.SimRequest>) =>
  request('/api/v1/simulations', {
    method: 'POST',
    body: S.SimRequest.parse(body),
    schema: S.RunStatus,
  });
export const runs = () =>
  request('/api/v1/simulations', { schema: z.array(S.RunStatus) });
export const run = (id: string) =>
  request(`/api/v1/simulations/${encodeURIComponent(id)}`, {
    schema: S.RunSummaryResp,
  });
export async function timeseries(id: string) {
  const raw = await request(
    `/api/v1/simulations/${encodeURIComponent(id)}/timeseries`,
    { schema: z.unknown() },
  );
  return z
    .record(z.array(z.union([z.number(), z.null()])))
    .parse(normalizeTimeseries(raw));
}
export const createBenchmark = (body: z.input<typeof S.BenchmarkRequest>) =>
  request('/api/v1/benchmarks', {
    method: 'POST',
    body: S.BenchmarkRequest.parse(body),
    schema: z.object({ id: z.string(), status: z.string() }).passthrough(),
  });
export const benchmarks = () =>
  request('/api/v1/benchmarks', { schema: z.array(S.Benchmark) });
export const benchmark = (id: string) =>
  request(`/api/v1/benchmarks/${encodeURIComponent(id)}`, {
    schema: S.Benchmark,
  });
export const readiness = () =>
  request('/health/ready', {
    schema: z.object({ status: z.string() }).passthrough(),
    auth: false,
  });
export const keys = () =>
  request('/api/v1/admin/keys', { schema: z.array(S.KeyRow) });
export const createKey = (body: {
  name: string;
  role: 'viewer' | 'operator' | 'admin';
  ttl_days?: number;
}) =>
  request('/api/v1/admin/keys', {
    method: 'POST',
    body,
    schema: z
      .object({ key: z.string(), key_id: z.string(), warning: z.string() })
      .passthrough(),
  });
export const revokeKey = (id: string) =>
  request(`/api/v1/admin/keys/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    schema: z.object({ status: z.string() }).passthrough(),
  });
export const audit = (limit = 100) =>
  request(`/api/v1/admin/audit?limit=${limit}`, {
    schema: z.array(S.AuditRow),
  });
export const adminHealth = () =>
  request('/api/v1/admin/health/details', { schema: S.HealthDetails });
export const crosscheck = (length = 30, band = 'O') =>
  request(`/api/v1/crosscheck?length_km=${length}&band=${band}`, {
    schema: S.Crosscheck,
  });
