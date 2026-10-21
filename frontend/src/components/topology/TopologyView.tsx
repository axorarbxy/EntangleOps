import type { LinkInfo, LinkSnap } from '../../api/schemas';
export function TopologyView({
  nodes,
  links,
  select,
  snapshot,
}: {
  nodes: string[];
  links: LinkInfo[];
  select?: (id: string) => void;
  snapshot?: Record<string, LinkSnap>;
}) {
  const positions: Record<string, [number, number]> = {
    A: [18, 28],
    B: [50, 12],
    C: [82, 28],
    D: [82, 72],
    E: [50, 88],
    F: [18, 72],
  };
  const point = (n: string): [number, number] => positions[n] ?? [50, 50];
  return (
    <svg
      className="topology"
      viewBox="0 0 100 100"
      role="img"
      aria-label="Network topology"
    >
      {links.map((l, i) => {
        const [x1, y1] = point(l.u),
          [x2, y2] = point(l.v),
          id = l.link_id ?? l.id ?? `${l.u}-${l.v}`,
          snap = snapshot?.[id],
          value = snap?.fidelity_C ?? 0;
        return (
          <g
            key={id}
            onClick={() => select?.(id)}
            tabIndex={0}
            role="button"
            aria-label={`Link ${l.u} to ${l.v}, fidelity ${snap ? value.toFixed(3) : 'not loaded'}, utilization ${snap ? Math.round(snap.utilization * 100) : 0} percent`}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') select?.(id);
            }}
          >
            <line
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              className={`topology-link fidelity-${snap ? Math.min(4, Math.max(1, Math.floor((value - 0.6) / 0.1) + 1)) : 0} width-${i % 4}`}
            />
            <text
              x={(x1 + x2) / 2}
              y={(y1 + y2) / 2 - 2}
              className="link-label"
            >
              {snap ? value.toFixed(3) : `${l.length_km} km`}
            </text>
            <text
              x={(x1 + x2) / 2}
              y={(y1 + y2) / 2 + 2}
              className="band-label"
            >
              {snap?.best_band_true ?? ''}
            </text>
          </g>
        );
      })}
      {nodes.map((n) => {
        const [cx, cy] = point(n);
        return (
          <g key={n}>
            <circle cx={cx} cy={cy} r="4.7" className="topology-node" />
            <text x={cx} y={cy + 0.9} className="node-label">
              {n}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
