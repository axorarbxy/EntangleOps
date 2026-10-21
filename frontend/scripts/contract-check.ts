import { z } from 'zod';
import {
  Me,
  RunStatus,
  RunSummaryResp,
  SimRequest,
  Topology,
} from '../src/api/schemas';
import { normalizeTimeseries } from '../src/api/adapters';

const base = process.env.EO_API_BASE;
const key = process.env.EO_API_KEY;
if (!base || !key) {
  process.stderr.write(
    'Set EO_API_BASE and EO_API_KEY in the shell environment.\n',
  );
  process.exit(2);
}
async function call(
  path: string,
  options: { method?: string; body?: unknown } = {},
) {
  const response = await fetch(`${base}${path}`, {
    method: options.method ?? 'GET',
    headers: {
      'X-API-Key': key!,
      Accept: 'application/json',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
    cache: 'no-store',
  });
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json() as Promise<unknown>;
}
const get = async (path: string, schema: z.ZodTypeAny) =>
  schema.parse(await call(path));
await get('/api/v1/me', Me);
await get('/api/v1/topology?preset=tiny', Topology);
const input = SimRequest.parse({
  policy: 'adaptive',
  seed: 42,
  duration_hours: 1,
  dt_s: 600,
  topology_preset: 'tiny',
  scenario: { arrival_rate_per_step: 0 },
});
const created = RunStatus.parse(
  await call('/api/v1/simulations', { method: 'POST', body: input }),
);
let state = created;
for (
  let attempt = 0;
  attempt < 120 && state.status !== 'done' && state.status !== 'error';
  attempt++
) {
  await new Promise((resolve) => setTimeout(resolve, 1000));
  state = RunSummaryResp.parse(
    await call(`/api/v1/simulations/${encodeURIComponent(created.id)}`),
  );
}
const completed = RunSummaryResp.parse(
  await call(`/api/v1/simulations/${encodeURIComponent(created.id)}`),
);
if (completed.status !== 'done')
  throw new Error(`Short contract run ended with ${completed.status}`);
const series = normalizeTimeseries(
  await call(
    `/api/v1/simulations/${encodeURIComponent(created.id)}/timeseries`,
  ),
);
if (!series.step?.length)
  throw new Error('Timeseries response did not include step values.');
process.stdout.write(
  'Contract check passed: /me, tiny topology, short adaptive simulation, run summary and normalized timeseries.\n',
);
