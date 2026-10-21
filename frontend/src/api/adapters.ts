import { LinkInfo, Topology } from './schemas';
export function normalizeTopology(value: Topology) {
  return {
    nodes: value.nodes.map((n) => (typeof n === 'string' ? n : n.id)),
    links: value.links.map((l) => ({
      ...l,
      id: l.link_id ?? l.id ?? `${l.u}-${l.v}`,
    })),
  };
}
export function normalizeTimeseries(
  value: unknown,
): Record<string, (number | null)[]> {
  if (typeof value !== 'object' || value === null) return {};
  const raw = value as Record<string, unknown>;
  const source =
    typeof raw.fields === 'object' && raw.fields !== null
      ? (raw.fields as Record<string, unknown>)
      : raw;
  return Object.fromEntries(
    Object.entries(source)
      .filter(([, v]) => Array.isArray(v))
      .map(([k, v]) => [
        k,
        (v as unknown[]).map((x) =>
          typeof x === 'number' && Number.isFinite(x) ? x : null,
        ),
      ]),
  );
}
export function linkName(link: LinkInfo): string {
  return link.link_id ?? link.id ?? `${link.u}-${link.v}`;
}
