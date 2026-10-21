import { describe, expect, it } from 'vitest';
import { expectedRequests, nSteps } from './budget';
describe('simulation budget', () => {
  it('computes steps at backend cadence', () => {
    expect(nSteps(48, 30)).toBe(5760);
    expect(nSteps(48, 15)).toBe(11520);
  });
  it('computes expected request count', () => {
    expect(expectedRequests(0.1, 24, 60)).toBe(144);
  });
});
