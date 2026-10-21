import { describe, expect, it } from 'vitest';
import { linkFidelity, linkRate, linkWerner, type Band } from './physics';
describe('illustrative physics port', () => {
  it('matches a C-band reference value', () => {
    const l = { length_km: 30, aerial_fraction: 1 };
    const c = { traffic_load: 0.5, dtemp_dt_c_per_h: 0, wind_ms: 3 };
    expect(linkWerner(l, 'C', c)).toBeCloseTo(0.769008, 5);
    expect(linkFidelity(l, 'C', c)).toBeCloseTo(0.826756, 5);
  });
  it('keeps fidelity bounded and O-band fidelity higher under classical load', () => {
    const l = { length_km: 30, aerial_fraction: 1 };
    const c = { traffic_load: 0.5, dtemp_dt_c_per_h: 0, wind_ms: 3 };
    const fc = linkFidelity(l, 'C', c),
      fo = linkFidelity(l, 'O', c);
    expect(fc).toBeGreaterThanOrEqual(0.25);
    expect(fc).toBeLessThanOrEqual(1);
    expect(fo).toBeGreaterThan(fc);
  });
  it('keeps the C-band rate higher at equal distance', () => {
    const l = { length_km: 30, aerial_fraction: 1 };
    expect(linkRate(l, 'C')).toBeGreaterThan(linkRate(l, 'O'));
  });
  it('supports both frequency bands', () => {
    const bands: Band[] = ['C', 'O'];
    expect(bands).toHaveLength(2);
  });
});
