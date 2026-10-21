export const number = (n: number, digits = 0) =>
  new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(n);
export const fidelity = (n: number) => n.toFixed(3);
export const percent = (n: number) => `${(n * 100).toFixed(1)}%`;
export function duration(seconds: number) {
  const h = Math.floor(seconds / 3600),
    m = Math.floor((seconds % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m`;
}
