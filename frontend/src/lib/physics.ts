export const ALPHA_DB_PER_KM = { C: 0.2, O: 0.35 } as const;
export const RAMAN_K = { C: 4e-3, O: 1.5e-4 } as const;
export const W0 = 0.97,
  A_TEMP = 0.02,
  A_WIND = 0.01,
  BURIED_LOSS_PER_KM = 0.0005,
  SWAP_W = 0.98,
  SWAP_P = 0.5;
export type Band = 'C' | 'O';
export interface Link {
  length_km: number;
  aerial_fraction: number;
  modes?: number;
  source_rate_hz?: number;
}
export interface Cond {
  traffic_load: number;
  dtemp_dt_c_per_h: number;
  wind_ms: number;
}
export const transmittance = (L: number, b: Band) =>
  10 ** ((-ALPHA_DB_PER_KM[b] * L) / 10);
export const snrFactor = (L: number, b: Band, load: number) => {
  const e = transmittance(L, b);
  return e / (e + RAMAN_K[b] * Math.max(load, 0) * L);
};
export function envVisibility(l: Link, c: Cond) {
  const aerial = l.length_km * l.aerial_fraction,
    buried = l.length_km - aerial;
  return Math.exp(
    -(
      ((A_TEMP * Math.abs(c.dtemp_dt_c_per_h) +
        A_WIND * Math.max(c.wind_ms, 0)) *
        aerial) /
        50 +
      BURIED_LOSS_PER_KM * buried
    ),
  );
}
export const linkWerner = (l: Link, b: Band, c: Cond) =>
  W0 * snrFactor(l.length_km, b, c.traffic_load) * envVisibility(l, c);
export const wernerToFidelity = (w: number) => 0.25 + 0.75 * w;
export const linkFidelity = (l: Link, b: Band, c: Cond) =>
  wernerToFidelity(linkWerner(l, b, c));
export const linkRate = (l: Link, b: Band) =>
  (l.source_rate_hz ?? 2000) * transmittance(l.length_km, b) * (l.modes ?? 4);
export function pathMetrics(hops: { link: Link; band: Band; cond: Cond }[]) {
  let w = 1,
    rate = Infinity;
  for (const hop of hops) {
    w *= linkWerner(hop.link, hop.band, hop.cond);
    rate = Math.min(rate, linkRate(hop.link, hop.band));
  }
  const n = hops.length;
  return {
    fidelity: wernerToFidelity(w * SWAP_W ** (n - 1)),
    rate: rate * SWAP_P ** (n - 1),
  };
}
