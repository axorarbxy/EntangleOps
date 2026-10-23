const raw = import.meta.env;
export const env = {
  apiBase: String(raw.VITE_API_BASE ?? '').replace(/\/$/, ''),
  wsBase: String(raw.VITE_WS_BASE ?? ''),
  grafanaUrl: String(raw.VITE_GRAFANA_URL ?? ''),
  idleMinutes: Number(raw.VITE_IDLE_MINUTES ?? 30),
  demo: raw.VITE_DEMO_MODE === 'true',
  demoFixtures: raw.VITE_DEMO_FIXTURES === 'true',
};
export function wsUrl(path: string): string {
  if (env.wsBase) return env.wsBase.replace(/\/$/, '') + path;
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}${path}`;
}
