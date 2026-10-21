import { describe, expect, it } from 'vitest';
import { normalizeTimeseries, normalizeTopology } from './adapters';
describe('contract adapters', () => {
  it('normalizes flat and wrapped timeseries arrays', () => {
    expect(normalizeTimeseries({ a: [1, 2], extra: 'ignored' })).toEqual({
      a: [1, 2],
    });
    expect(normalizeTimeseries({ fields: { a: [1, null] } })).toEqual({
      a: [1, null],
    });
  });
  it('normalizes node id and node object topology forms', () => {
    expect(
      normalizeTopology({
        nodes: ['A', { id: 'B' }],
        links: [
          {
            link_id: 'L',
            u: 'A',
            v: 'B',
            length_km: 3,
            aerial_fraction: 1,
            modes: 2,
            channels: 1,
          },
        ],
      } as never).nodes,
    ).toEqual(['A', 'B']);
  });
});
