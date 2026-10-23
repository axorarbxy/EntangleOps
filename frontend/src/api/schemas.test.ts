import { describe, expect, it } from 'vitest';
import { KeyRow, LinkSnap, RunSummaryResp, Summary } from './schemas';
describe('verified backend response shapes', () => {
  it('normalizes backend link wind field to the UI field', () => {
    expect(
      LinkSnap.parse({
        traffic: 0.5,
        temp_c: 18,
        wind: 9,
        dtemp_dt: 1,
        utilization: 0.3,
        best_band_true: 'O',
        fidelity_C: 0.8,
        fidelity_O: 0.9,
      }).wind_ms,
    ).toBe(9);
  });
  it('accepts numeric key timestamps and extra response fields', () => {
    expect(
      KeyRow.parse({
        key_id: '0123456789ab',
        name: 'viewer',
        role: 'viewer',
        created_at: 1,
        expires_at: null,
        hash: 'ignored',
      }).created_at,
    ).toBe(1);
  });
  it('parses the documented summary keys and preserves added backend fields', () => {
    const result = Summary.parse({
      policy: 'adaptive',
      total_requests: 0,
      admitted: 0,
      blocked: 0,
      block_rate: 0,
      sla_satisfied_pairs: 0,
      raw_pairs: 0,
      sla_efficiency: 0,
      violation_fraction: 0,
      mean_fidelity: 0,
      reroutes: 0,
      priority_weighted_useful_pairs: 0,
      peak_active: 0,
      extension: 'safe',
    });
    expect(result.policy).toBe('adaptive');
  });
  it('accepts persisted run metadata returned by the backend detail route', () => {
    const result = RunSummaryResp.parse({
      id: 'STG4hSg8C2v7uPLc',
      status: 'done',
      created_at: new Date().toISOString(),
      owner: 'local-demo',
      n_steps: 12,
      dt_s: 300,
      error: null,
      config: {
        policy: 'static_c',
        seed: 42,
        duration_hours: 1,
        dt_s: 300,
        topology_preset: 'metro',
        scenario: {},
      },
      summary: {
        policy: 'static_c',
        total_requests: 0,
        admitted: 0,
        blocked: 0,
        block_rate: 0,
        sla_satisfied_pairs: 0,
        raw_pairs: 0,
        sla_efficiency: 0,
        violation_fraction: 0,
        mean_fidelity: 0,
        reroutes: 0,
        priority_weighted_useful_pairs: 0,
        peak_active: 0,
      },
    });
    expect(result.status).toBe('done');
  });
  it('accepts the backend’s explicit null for a disabled risk threshold', () => {
    const result = RunSummaryResp.parse({
      id: 'STG4hSg8C2v7uPLc',
      status: 'queued',
      config: {
        policy: 'adaptive',
        risk_alpha: null,
        seed: 42,
        duration_hours: 1,
        dt_s: 60,
        topology_preset: 'metro',
        scenario: {},
      },
      summary: null,
    });
    expect(result.config.risk_alpha).toBeNull();
  });
});
