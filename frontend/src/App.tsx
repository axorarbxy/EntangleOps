import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Boxes,
  CircleHelp,
  Cloud,
  Command,
  Cpu,
  FileClock,
  FlaskConical,
  Gauge,
  GitCompareArrows,
  KeyRound,
  LogOut,
  Menu,
  Network,
  Play,
  Radio,
  ShieldCheck,
  Sun,
  Waves,
  X,
  Zap,
} from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  adminHealth,
  audit,
  benchmark,
  benchmarks,
  createBenchmark,
  createKey,
  createRun,
  crosscheck,
  keys,
  mlModel,
  predict,
  readiness,
  revokeKey,
  run,
  runs,
  timeseries,
  topology,
} from './api/endpoints';
import { ApiError } from './api/client';
import { useSession } from './auth/store';
import { env } from './env';
import { linkFidelity, linkRate } from './lib/physics';
import { TopologyView } from './components/topology/TopologyView';
import { expectedRequests, nSteps } from './lib/budget';
import { fidelity, number, percent } from './lib/format';
import { queryClient } from './queryClient';
import { useReplay } from './replay/store';
import { usePlayback } from './replay/usePlayback';
import { useRunStream } from './replay/useRunStream';
const TimeSeriesChart = lazy(() =>
  import('./components/charts/TimeSeriesChart').then((module) => ({
    default: module.TimeSeriesChart,
  })),
);
const ModelsPage = lazy(() =>
  import('./pages/ModelsPage').then((module) => ({ default: module.ModelsPage })),
);
const ScalePlannerPage = lazy(() =>
  import('./pages/ScalePlannerPage').then((module) => ({ default: module.ScalePlannerPage })),
);

type PageKey =
  | 'overview'
  | 'network'
  | 'scale'
  | 'simulate'
  | 'runs'
  | 'run'
  | 'compare'
  | 'benchmarks'
  | 'lab'
  | 'models'
  | 'admin'
  | 'about'
  | 'login';
const iconMap = {
  overview: Gauge,
  network: Network,
  scale: Boxes,
  simulate: Play,
  runs: FileClock,
  compare: GitCompareArrows,
  benchmarks: BarChart3,
  lab: FlaskConical,
  models: Cpu,
  admin: ShieldCheck,
  about: CircleHelp,
};
const nav: { id: PageKey; label: string; role?: 'operator' | 'admin' }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'network', label: 'Network' },
  { id: 'scale', label: 'Scale planner' },
  { id: 'simulate', label: 'Simulate', role: 'operator' },
  { id: 'runs', label: 'Runs' },
  { id: 'compare', label: 'Compare', role: 'operator' },
  { id: 'benchmarks', label: 'Benchmarks', role: 'operator' },
  { id: 'lab', label: 'Physics & predictor' },
  { id: 'models', label: 'Models' },
  { id: 'admin', label: 'Admin', role: 'admin' },
  { id: 'about', label: 'About' },
];
const navLabel = (p: PageKey) =>
  nav.find((n) => n.id === p)?.label ?? 'Run detail';
function can(role: string | undefined, required: 'operator' | 'admin') {
  return required === 'operator'
    ? role === 'operator' || role === 'admin'
    : role === 'admin';
}
function pageFromPath(path: string): PageKey {
  if (path === '/') return 'overview';
  if (path.startsWith('/runs/')) return 'run';
  const p = path.split('/')[1] as PageKey;
  return nav.some((x) => x.id === p) ? p : 'overview';
}

export function App() {
  const location = useLocation(),
    navigate = useNavigate(),
    [page, setPage] = useState<PageKey>(pageFromPath(location.pathname));
  const [theme, setTheme] = useState(
      () => localStorage.getItem('eo.theme') ?? 'dark',
    ),
    [mobileOpen, setMobileOpen] = useState(false);
  const session = useSession(),
    qc = useQueryClient();
  const principal = session.principal;
  const setSession = useSession((s) => s.setSession);
  const expire = useSession((s) => s.expire);
  useEffect(() => {
    setPage(pageFromPath(location.pathname));
  }, [location.pathname]);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('eo.theme', theme);
  }, [theme]);
  useEffect(() => {
    const saved = sessionStorage.getItem('eo.session');
    if (!session.apiKey && saved) {
      try {
        const parsed = JSON.parse(saved) as {
          apiKey: string;
          principal: typeof principal;
        };
        setSession(parsed.apiKey, parsed.principal!, true);
      } catch {
        sessionStorage.removeItem('eo.session');
      }
    }
  }, [session.apiKey, setSession]);
  useEffect(() => {
    const expire = () => navigate('/login', { replace: true });
    window.addEventListener('eo:expired', expire);
    return () => window.removeEventListener('eo:expired', expire);
  }, [navigate]);
  const ready = useQuery({
    queryKey: ['health'],
    queryFn: readiness,
    refetchInterval: 30000,
    retry: false,
  });
  useEffect(() => {
    if (!session.apiKey) return;
    const time = env.idleMinutes * 60_000;
    let timer = window.setTimeout(() => expire(), time);
    const reset = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => expire(), time);
    };
    ['pointerdown', 'keydown', 'mousemove', 'touchstart'].forEach((e) =>
      window.addEventListener(e, reset, { passive: true }),
    );
    return () => {
      window.clearTimeout(timer);
      ['pointerdown', 'keydown', 'mousemove', 'touchstart'].forEach((e) =>
        window.removeEventListener(e, reset),
      );
    };
  }, [session.apiKey, expire]);
  const signOut = () => {
    expire();
    qc.clear();
    navigate('/login');
  };
  if (page === 'login')
    return (
      <Login
        onSuccess={() =>
          navigate((location.state as { from?: string } | null)?.from ?? '/')
        }
        demo={env.demo && env.demoFixtures}
      />
    );
  if (!session.apiKey || !principal)
    return (
      <Login
        onSuccess={() =>
          navigate(location.pathname === '/' ? '/' : location.pathname)
        }
        demo={env.demo && env.demoFixtures}
      />
    );
  const items = nav.filter((n) => !n.role || can(principal.role, n.role));
  return (
    <div className="app-shell">
      {env.demo && (
        <div className="demo-banner">
          {env.demoFixtures
            ? 'Fixture demo — synthetic sample data, not live'
            : 'Demo environment — connected to the local API and persistent database'}
        </div>
      )}
      <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}>
        <div className="brand">
          <span className="brand-mark">
            <Waves size={21} />
          </span>
          <span>
            <strong>entangleops</strong>
            <small>NETWORK CONTROL PLANE</small>
          </span>
          <button
            className="icon-button mobile-close"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation"
          >
            <X size={18} />
          </button>
        </div>
        <div className="workspace-label">
          WORKSPACE <span>METRO · DIGITAL TWIN</span>
        </div>
        <nav aria-label="Main navigation">
          {items.map((item) => {
            const Icon = iconMap[item.id as keyof typeof iconMap];
            return (
              <NavLink
                key={item.id}
                to={item.id === 'overview' ? '/' : `/${item.id}`}
                onClick={() => setMobileOpen(false)}
                className={({ isActive }) =>
                  `nav-link ${isActive ? 'active' : ''}`
                }
              >
                <Icon size={17} />
                {item.label}
                {item.id === 'runs' && <span className="nav-live-dot" />}
              </NavLink>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="security-card">
            <div className="secure-icon">
              <ShieldCheck size={15} />
            </div>
            <span>
              <b>Control plane secure</b>
              <small>API key protected session</small>
            </span>
          </div>
          <button className="profile-button" onClick={signOut}>
            <span className="avatar">
              {principal.name.slice(0, 1).toUpperCase()}
            </span>
            <span className="profile-text">
              <b>{principal.name}</b>
              <small>
                {principal.role} key · {principal.keyId}
              </small>
            </span>
            <LogOut size={16} />
          </button>
        </div>
      </aside>
      {mobileOpen && (
        <button
          className="scrim"
          onClick={() => setMobileOpen(false)}
          aria-label="Close menu"
        />
      )}
      <main className="main-area">
        <header className="topbar">
          <button
            className="icon-button menu-button"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
          >
            <Menu size={19} />
          </button>
          <div className="breadcrumbs">
            <span>Console</span>
            <span className="crumb-sep">/</span>
            <strong>{page === 'run' ? 'Run detail' : navLabel(page)}</strong>
          </div>
          <div className="top-actions">
            <span
              className={`health-pill ${ready.isError || ready.data?.status !== 'ready' ? 'down' : ''}`}
            >
              <span className="health-dot" />
              {ready.isError
                ? 'Backend unreachable'
                : ready.data?.status === 'ready'
                  ? 'Systems operational'
                  : 'Systems checking'}
            </span>
            <span className={`role-pill ${principal.role}`}>
              {principal.role}
            </span>
            <button
              className="icon-button theme-toggle"
              aria-label="Toggle theme"
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            >
              <Sun size={17} />
            </button>
          </div>
        </header>
        <div className="page-wrap">
          <ErrorNotice ready={ready.isError} />
          {page === 'overview' ? (
            <Overview />
          ) : page === 'network' ? (
            <NetworkPage />
          ) : page === 'scale' ? (
            <Suspense fallback={<div className="panel ml-empty">Loading scale planner…</div>}><ScalePlannerPage /></Suspense>
          ) : page === 'simulate' ? (
            <Simulate />
          ) : page === 'runs' ? (
            <Runs />
          ) : page === 'run' ? (
            <RunDetail id={location.pathname.split('/')[2] ?? ''} />
          ) : page === 'compare' ? (
            <Compare />
          ) : page === 'benchmarks' ? (
            <Benchmarks />
          ) : page === 'lab' ? (
            <Lab />
          ) : page === 'models' ? (
            <Suspense fallback={<div className="panel ml-empty">Loading model workspace…</div>}><ModelsPage /></Suspense>
          ) : page === 'admin' ? (
            <Admin role={principal.role} />
          ) : (
            <About />
          )}
        </div>
        <footer className="disclaimer">
          <span>SIMULATED DIGITAL TWIN</span> Physical constants are
          illustrative, not calibrated to a specific experiment. Nothing here is
          a quantum-security guarantee.
        </footer>
      </main>
    </div>
  );
}

function Login({ onSuccess, demo }: { onSuccess: () => void; demo: boolean }) {
  const setSession = useSession((s) => s.setSession),
    [key, setKey] = useState(''),
    [visible, setVisible] = useState(false),
    [remember, setRemember] = useState(false),
    [error, setError] = useState(''),
    [wait, setWait] = useState(0),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    if (wait <= 0) return;
    const timer = window.setTimeout(() => setWait(wait - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [wait]);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError('');
    if (
      !/^eo_[0-9a-f]{12}\.[A-Za-z0-9_-]{20,150}$/.test(key) ||
      key.length > 200
    ) {
      setError('Enter a valid API key in the format eo_<key_id>.<secret>.');
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(`${env.apiBase}/api/v1/me`, {
        headers: { Accept: 'application/json', 'X-API-Key': key },
        credentials: 'omit',
        cache: 'no-store',
      });
      if (!response.ok) {
        if (response.status === 429) {
          const seconds = Number(response.headers.get('Retry-After')) || 60;
          setWait(seconds);
          setError(`Too many attempts. Try again in ${seconds} seconds.`);
        } else if (response.status === 401)
          setError('That key was not accepted.');
        else setError('The EntangleOps backend could not validate this key.');
        return;
      }
      const data = (await response.json()) as {
        key_id: string;
        name: string;
        role: 'viewer' | 'operator' | 'admin';
      };
      setSession(
        key,
        { keyId: data.key_id, name: data.name, role: data.role },
        remember,
      );
      setKey('');
      onSuccess();
    } catch {
      setError(
        'Cannot reach the EntangleOps backend. Check that the backend is running.',
      );
    } finally {
      setBusy(false);
    }
  }
  function enterDemo() {
    const fake = 'eo_0123456789ab.abcdefghijklmnopqrstuvwx';
    sessionStorage.setItem('eo.bench', JSON.stringify(['demo-benchmark-001']));
    setSession(
      fake,
      { keyId: '0123456789ab', name: 'demo operator', role: 'operator' },
      false,
    );
    onSuccess();
  }
  return (
    <div className="login-screen">
      <div className="login-orbit orbit-one" />
      <div className="login-orbit orbit-two" />
      <div className="login-card">
        <div className="login-brand">
          <div className="brand-mark large">
            <Waves size={26} />
          </div>
          <div>
            <div className="login-word">entangleops</div>
            <div className="login-sub">NETWORK CONTROL PLANE</div>
          </div>
        </div>
        <div className="login-heading">
          <div className="eyebrow">QUANTUM NETWORK OPERATIONS</div>
          <h1>Welcome back</h1>
          <p>Connect to your network control plane.</p>
        </div>
        <form onSubmit={submit}>
          <label htmlFor="api-key">API key</label>
          <div className="password-input">
            <KeyRound size={17} />
            <input
              id="api-key"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              type={visible ? 'text' : 'password'}
              autoComplete="off"
              spellCheck={false}
              placeholder="eo_••••••••••••.••••••••••••"
            />
            <button type="button" onClick={() => setVisible(!visible)}>
              {visible ? 'Hide' : 'Show'}
            </button>
          </div>
          <label className="remember">
            <input
              type="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
            />
            <span>Keep me signed in for this tab</span>
          </label>
          {error && (
            <div className="form-alert" role="alert">
              {error}
            </div>
          )}
          <button className="primary-button full" disabled={busy || wait > 0}>
            {busy ? (
              <>
                <span className="spinner" /> Connecting…
              </>
            ) : wait > 0 ? (
              `Try again in ${wait}s`
            ) : (
              'Connect to console'
            )}
            <ArrowUpRight size={16} />
          </button>
        </form>
        <div className="login-divider">
          <span>SECURE ACCESS</span>
        </div>
        <p className="login-help">
          Keys are provided by your administrator (
          <code>scripts/manage_keys.py</code>).
        </p>
        {demo && (
          <button className="secondary-button full" onClick={enterDemo}>
            <Command size={16} /> Enter demo · no backend
          </button>
        )}
        <div className="login-foot">
          <span>
            <span className="health-dot green" /> ENCRYPTED API SESSION
          </span>
          <span>v1.0.0</span>
        </div>
      </div>
      <div className="login-caption">
        EntangleOps Console <span>·</span> Digital twin environment
      </div>
    </div>
  );
}

function ErrorNotice({ ready }: { ready: boolean }) {
  return ready ? (
    <div className="backend-banner">
      <span className="health-dot red" />
      <div>
        <b>Cannot reach the EntangleOps backend</b>
        <small>
          Network data may be unavailable. Check the backend and retry.
        </small>
      </div>
      <button className="text-button" onClick={() => window.location.reload()}>
        Retry
      </button>
    </div>
  ) : null;
}
function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action && <div className="heading-action">{action}</div>}
    </div>
  );
}
function Panel({
  title,
  sub,
  children,
  action,
}: {
  title: string;
  sub?: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          {sub && <p>{sub}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
function Skeleton({ height = 90 }: { height?: number }) {
  const size = height < 130 ? 'short' : height < 300 ? 'medium' : 'tall';
  return <div className={`skeleton skeleton-${size}`} />;
}
function Status({ status }: { status: string }) {
  return (
    <span className={`status-chip ${status}`}>
      <i />
      {status}
    </span>
  );
}
function Metric({
  label,
  value,
  change,
  icon: Icon,
}: {
  label: string;
  value: string;
  change?: string;
  icon: typeof Activity;
}) {
  return (
    <div className="metric-card">
      <div className="metric-top">
        <span>{label}</span>
        <span className="metric-icon">
          <Icon size={17} />
        </span>
      </div>
      <div className="metric-value">{value}</div>
      {change && (
        <div className="metric-change">
          <ArrowUpRight size={13} />
          {change}
        </div>
      )}
    </div>
  );
}
function Empty({
  title,
  description,
  to,
  label,
}: {
  title: string;
  description: string;
  to?: string;
  label?: string;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">
        <Boxes size={22} />
      </span>
      <b>{title}</b>
      <p>{description}</p>
      {to && (
        <Link className="text-link" to={to}>
          {label ?? 'Get started'} <ArrowUpRight size={14} />
        </Link>
      )}
    </div>
  );
}
function Table({
  heads,
  children,
}: {
  heads: string[];
  children: React.ReactNode;
}) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {heads.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function Overview() {
  const r = useQuery({
    queryKey: ['runs'],
    queryFn: runs,
    refetchInterval: (q) =>
      q.state.data?.some((x) => x.status === 'queued' || x.status === 'running')
        ? 3000
        : false,
  });
  const benchmarkId = storedBenchmarkId();
  const b = useQuery({
    queryKey: ['bench', benchmarkId],
    queryFn: () => benchmark(benchmarkId ?? ''),
    enabled: Boolean(benchmarkId),
  });
  const data = r.data ?? [];
  const done = data.filter((x) => x.status === 'done');
  const top = done.slice(0, 5);
  return (
    <>
      <PageHeading
        eyebrow="OPERATIONS OVERVIEW"
        title="Good morning"
        description="A live view of your quantum network digital twin."
        action={
          <Link className="primary-button" to="/simulate">
            <Play size={16} /> New simulation
          </Link>
        }
      />
      <div className="metric-grid">
        <Metric
          icon={Activity}
          label="Active runs"
          value={number(
            data.filter((x) => x.status === 'queued' || x.status === 'running')
              .length,
          )}
          change="Across your workspace"
        />
        <Metric
          icon={Waves}
          label="Completed runs"
          value={number(done.length)}
          change="Available to replay"
        />
        <Metric
          icon={Zap}
          label="Latest SLA throughput"
          value={
            b.data?.results?.adaptive &&
            typeof (b.data.results.adaptive as Record<string, unknown>)
              .sla_satisfied_pairs === 'number'
              ? number(
                  (b.data.results.adaptive as Record<string, number>)
                    .sla_satisfied_pairs,
                  2,
                )
              : '—'
          }
          change="Backend benchmark · simulated"
        />
        <Metric
          icon={ShieldCheck}
          label="Control plane"
          value="Healthy"
          change="Auth · rate limits · audit"
        />
      </div>
      <div className="content-grid overview-grid">
        <Panel
          title="Recent runs"
          sub="Your latest simulation activity"
          action={
            <Link to="/runs" className="text-link">
              All runs <ArrowUpRight size={14} />
            </Link>
          }
        >
          {r.isLoading ? (
            <Skeleton height={220} />
          ) : r.isError ? (
            <ErrorBlock error={r.error} />
          ) : data.length === 0 ? (
            <Empty
              title="Your network is ready"
              description="Launch a simulation to explore routing performance."
              to="/simulate"
              label="Start a simulation"
            />
          ) : (
            <Table heads={['Run', 'Policy', 'Created', 'Status', 'SLA pairs']}>
              {top.map((x) => (
                <tr key={x.id} onClick={() => location.assign(`/runs/${x.id}`)}>
                  <td className="mono">{x.id.slice(0, 12)}</td>
                  <td>
                    <span className={`policy-tag ${x.status}`}>●</span>{' '}
                    {x.status === 'done' ? 'Simulation' : 'Queued'}
                  </td>
                  <td>
                    {x.created_at
                      ? new Date(x.created_at).toLocaleString()
                      : '—'}
                  </td>
                  <td>
                    <Status status={x.status} />
                  </td>
                  <td>—</td>
                </tr>
              ))}
            </Table>
          )}
        </Panel>
        <Panel
          title="Network at a glance"
          sub="Metro topology · 6 nodes · 9 links"
          action={
            <Link to="/network" className="text-link">
              Explore <ArrowUpRight size={14} />
            </Link>
          }
        >
          <MiniTopology />
          <div className="topology-legend">
            <span>
              <i className="legend-dot classical" /> Classical traffic
            </span>
            <span>
              <i className="legend-dot quantum" /> Quantum links
            </span>
          </div>
        </Panel>
      </div>
      <div className="content-grid overview-insights">
        <Panel title="Run activity" sub="Runs created in the last 7 days">
          <RunActivityChart runs={data} />
        </Panel>
        <Panel title="Run status mix" sub="Current workspace run states">
          <RunStatusChart runs={data} />
        </Panel>
      </div>
      <Panel
        title="Explore the console"
        sub="Move from network conditions to policy comparison."
      >
        <div className="quick-grid">
          <Quick
            to="/network"
            icon={Network}
            title="Inspect network"
            text="Explore link paths and channel conditions"
          />
          <Quick
            to="/simulate"
            icon={Play}
            title="Run a simulation"
            text="Shape a scenario and launch the digital twin"
          />
          <Quick
            to="/compare"
            icon={GitCompareArrows}
            title="Compare policies"
            text="Compare adaptive routing against baselines"
          />
        </div>
      </Panel>
    </>
  );
}
type DashboardRun = { id: string; status: string; created_at?: string | null };
function RunActivityChart({ runs: items }: { runs: DashboardRun[] }) {
  const now = new Date();
  const days = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(now);
    date.setDate(now.getDate() - (6 - index));
    date.setHours(0, 0, 0, 0);
    return { date, day: date.toLocaleDateString(undefined, { weekday: 'short' }), runs: 0 };
  });
  items.forEach((item) => {
    if (!item.created_at) return;
    const created = new Date(item.created_at);
    const bucket = days.find((day) => day.date.toDateString() === created.toDateString());
    if (bucket) bucket.runs += 1;
  });
  return (
    <div className="insight-chart" role="img" aria-label="Run activity by day for the last seven days">
      <ResponsiveContainer width="100%" height={210}>
        <AreaChart data={days} margin={{ top: 12, right: 12, bottom: 0, left: -18 }}>
          <defs><linearGradient id="runGlow" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#43f5d0" stopOpacity={0.34} /><stop offset="95%" stopColor="#43f5d0" stopOpacity={0.01} /></linearGradient></defs>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 5" vertical={false} />
          <XAxis dataKey="day" tick={{ fill: 'var(--muted)', fontSize: 10 }} tickLine={false} axisLine={false} />
          <YAxis allowDecimals={false} width={32} tick={{ fill: 'var(--muted)', fontSize: 9 }} tickLine={false} axisLine={false} />
          <Tooltip contentStyle={{ background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 10, color: 'var(--text)', fontSize: 11 }} labelStyle={{ color: 'var(--muted)' }} />
          <Area type="monotone" dataKey="runs" name="Runs" stroke="#43f5d0" strokeWidth={2.5} fill="url(#runGlow)" activeDot={{ r: 5, stroke: 'var(--surface)', strokeWidth: 2 }} />
        </AreaChart>
      </ResponsiveContainer>
      <div className="chart-caption"><span className="chart-live-dot" /> Based on run creation timestamps</div>
    </div>
  );
}
function RunStatusChart({ runs: items }: { runs: DashboardRun[] }) {
  const palette: Record<string, string> = { done: '#43f5d0', running: '#9b8cff', queued: '#43b9ff', failed: '#ff668c', cancelled: '#71809d' };
  const labels: Record<string, string> = { done: 'Completed', running: 'Running', queued: 'Queued', failed: 'Failed', cancelled: 'Cancelled' };
  const counts = items.reduce<Record<string, number>>((all, item) => { all[item.status] = (all[item.status] ?? 0) + 1; return all; }, {});
  const chartData = Object.entries(counts).map(([status, value]) => ({ status, name: labels[status] ?? status, value }));
  return items.length ? (
    <div className="status-chart-layout">
      <div className="status-donut" role="img" aria-label={`Run statuses: ${chartData.map((item) => `${item.name} ${item.value}`).join(', ')}`}>
        <ResponsiveContainer width="100%" height={190}>
          <PieChart><Pie data={chartData} dataKey="value" nameKey="name" innerRadius={58} outerRadius={78} paddingAngle={4} stroke="none">{chartData.map((item) => <Cell key={item.status} fill={palette[item.status] ?? '#43b9ff'} />)}</Pie><Tooltip contentStyle={{ background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 10, color: 'var(--text)', fontSize: 11 }} /></PieChart>
        </ResponsiveContainer>
        <div className="donut-total"><b>{items.length}</b><small>Total runs</small></div>
      </div>
      <div className="status-legend">{chartData.map((item) => <div key={item.status}><i style={{ background: palette[item.status] ?? '#43b9ff' }} /><span>{item.name}</span><b>{item.value}</b></div>)}</div>
    </div>
  ) : <div className="chart-empty">Run a simulation to see status analytics.</div>;
}
function storedBenchmarkId(): string | null {
  try {
    const value: unknown = JSON.parse(
      sessionStorage.getItem('eo.bench') ?? '[]',
    );
    return Array.isArray(value) && typeof value[0] === 'string'
      ? value[0]
      : null;
  } catch {
    return null;
  }
}
function Quick({
  to,
  icon: Icon,
  title,
  text,
}: {
  to: string;
  icon: typeof Activity;
  title: string;
  text: string;
}) {
  return (
    <Link to={to} className="quick-card">
      <span className="quick-icon">
        <Icon size={18} />
      </span>
      <span>
        <b>{title}</b>
        <small>{text}</small>
      </span>
      <ArrowUpRight size={15} />
    </Link>
  );
}
function MiniTopology() {
  const q = useQuery({
    queryKey: ['topology', 'metro'],
    queryFn: () => topology('metro'),
  });
  if (!q.data) return <Skeleton height={190} />;
  return (
    <TopologyView
      nodes={q.data.nodes.map((n) => (typeof n === 'string' ? n : n.id))}
      links={q.data.links}
    />
  );
}
function ErrorBlock({ error }: { error: unknown }) {
  const e = error instanceof ApiError ? error : null;
  return (
    <div className="error-block">
      <b>{error instanceof Error ? error.message : 'Something went wrong'}</b>
      {e?.requestId && <small>Request ID: {e.requestId}</small>}
      <button className="text-button" onClick={() => window.location.reload()}>
        Retry
      </button>
    </div>
  );
}

function NetworkPage() {
  const [preset, setPreset] = useState('metro'),
    [selected, setSelected] = useState(''),
    [load, setLoad] = useState(0.45),
    [wind, setWind] = useState(3),
    [rate, setRate] = useState(0);
  const q = useQuery({
    queryKey: ['topology', preset],
    queryFn: () => topology(preset),
  });
  const shape = q.data
    ? {
        nodes: q.data.nodes.map((n) => (typeof n === 'string' ? n : n.id)),
        links: q.data.links,
      }
    : null;
  const link =
    shape?.links.find(
      (l) => (l.link_id ?? l.id ?? `${l.u}-${l.v}`) === selected,
    ) ?? shape?.links[0];
  return (
    <>
      <PageHeading
        eyebrow="NETWORK INTELLIGENCE"
        title="Network topology"
        description="Inspect your fiber network and the physical conditions affecting each quantum link."
        action={
          <select
            className="select-control"
            value={preset}
            onChange={(e) => setPreset(e.target.value)}
          >
            <option value="metro">Metro network</option>
            <option value="tiny">Tiny network</option>
          </select>
        }
      />
      <div className="network-grid">
        <Panel
          title={`${preset === 'metro' ? 'Metro' : 'Tiny'} network`}
          sub="Analytic preview · illustrative model"
        >
          <div className="topology-box">
            {q.isLoading ? (
              <Skeleton height={336} />
            ) : q.isError ? (
              <ErrorBlock error={q.error} />
            ) : (
              shape && (
                <TopologyView
                  nodes={shape.nodes}
                  links={shape.links}
                  select={setSelected}
                />
              )
            )}
          </div>
          <div className="topology-legend">
            <span>
              <i className="legend-dot classical" /> Shared classical fiber
            </span>
            <span>
              <i className="legend-dot quantum" /> Quantum channel
            </span>
            <span>Aerial share shown per link</span>
          </div>
        </Panel>
        <div className="network-overview">
          <Panel title="Analytic conditions" sub="Illustrative physics preview">
            <div className="network-range-grid">
              <Range
                label="Classical traffic"
                value={load}
                min={0}
                max={1}
                step={0.05}
                unit=""
                onChange={setLoad}
              />
              <Range
                label="Wind speed"
                value={wind}
                min={0}
                max={30}
                step={1}
                unit="m/s"
                onChange={setWind}
              />
              <Range
                label="Temperature trend"
                value={rate}
                min={0}
                max={20}
                step={1}
                unit="°C/h"
                onChange={setRate}
              />
            </div>
            <div className="notice small-notice">
              This analytic preview uses the illustrative physics model. It is
              not a simulation result.
            </div>
          </Panel>
          {link && (
            <Panel
              title={`Link ${link.u}–${link.v}`}
              sub={`${link.length_km} km · ${(link.aerial_fraction * 100).toFixed(0)}% aerial · ${link.modes} modes · ${link.channels} channels`}
            >
              <div className="band-comparison">
                {(['C', 'O'] as const).map((b) => {
                  const f = linkFidelity(
                    {
                      length_km: link.length_km,
                      aerial_fraction: link.aerial_fraction,
                    },
                    b,
                    {
                      traffic_load: load,
                      dtemp_dt_c_per_h: rate,
                      wind_ms: wind,
                    },
                  );
                  const r = linkRate(
                    {
                      length_km: link.length_km,
                      aerial_fraction: link.aerial_fraction,
                    },
                    b,
                  );
                  return (
                    <div className={`band-row band-${b.toLowerCase()}`} key={b}>
                      <span className="band-pill">{b}</span>
                      <div>
                        <b>{fidelity(f)}</b>
                        <small>Fidelity · {number(r, 1)} pairs/s rate</small>
                      </div>
                      <div className="bar-track">
                        <span
                          className={`fidelity-fill-${Math.min(4, Math.max(1, Math.floor((f - 0.6) / 0.1) + 1))}`}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </Panel>
          )}
        </div>
      </div>
      <div className="network-tools-grid">
        {link && <TransitionWavelengthPlanner link={link} load={load} wind={wind} rate={rate} />}
        {link && <TtlOverFiberPlanner lengthKm={link.length_km} />}
        <FecBandwidthPlanner />
        <Panel
          title="Link inventory"
          sub={`${shape?.links.length ?? 0} links in preset`}
        >
          <div className="link-list">
            {shape?.links.map((l) => (
              <button
                key={l.link_id ?? l.id ?? `${l.u}-${l.v}`}
                onClick={() => setSelected(l.link_id ?? l.id ?? `${l.u}-${l.v}`)}
                className={`link-row ${(l.link_id ?? l.id ?? `${l.u}-${l.v}`) === selected ? 'selected' : ''}`}
              >
                <span className="link-status" />
                <span className="link-route">
                  {l.u}—{l.v}
                </span>
                <span>{l.length_km} km</span>
                <span>{Math.round(l.aerial_fraction * 100)}% aerial</span>
              </button>
            ))}
          </div>
        </Panel>
      </div>
    </>
  );
}

function TransitionWavelengthPlanner({
  link,
  load,
  wind,
  rate,
}: {
  link: { length_km: number; aerial_fraction: number };
  load: number;
  wind: number;
  rate: number;
}) {
  const [targetBand, setTargetBand] = useState<'C' | 'O'>('O');
  const [conversionEfficiency, setConversionEfficiency] = useState(0.85);
  const [fidelityRetention, setFidelityRetention] = useState(0.97);
  const conditions = { traffic_load: load, wind_ms: wind, dtemp_dt_c_per_h: rate };
  const transitionMatchedFidelity = linkFidelity(link, targetBand, conditions);
  const convertedFidelity = 0.25 + (transitionMatchedFidelity - 0.25) * fidelityRetention;
  const transitionMatchedRate = linkRate(link, targetBand);
  const convertedRate = transitionMatchedRate * conversionEfficiency;
  const centerWavelength = targetBand === 'C' ? 1550 : 1310;
  const gain = Math.max(0, Math.round((transitionMatchedRate - convertedRate) / Math.max(convertedRate, 1e-9) * 100));
  return (
    <Panel title="Transition wavelength design" sub="Plan a telecom matched emitter transition vs. frequency conversion">
      <div className="transition-controls">
        <label className="transition-select-label" htmlFor="transition-target-band">Fiber target band</label>
        <select id="transition-target-band" className="select-control" value={targetBand} onChange={(event) => setTargetBand(event.target.value as 'C' | 'O')}>
          <option value="O">O-band · ~1310 nm</option>
          <option value="C">C-band · ~1550 nm</option>
        </select>
      </div>
      <div className="transition-assumption-grid">
        <Range label="Frequency conversion efficiency" value={conversionEfficiency} min={0.5} max={1} step={0.01} unit="%" displayScale={100} onChange={setConversionEfficiency} />
        <Range label="State fidelity retention" value={fidelityRetention} min={0.8} max={1} step={0.005} unit="%" displayScale={100} onChange={setFidelityRetention} />
      </div>
      <div className="transition-flow">
        <div className="transition-option recommended">
          <span className="transition-option-tag">TRANSITION MATCHED</span>
          <b>Emitter transition → {centerWavelength} nm fiber</b>
          <small>No frequency-conversion stage in this link model</small>
          <div className="transition-result-row"><span>Estimated fidelity</span><strong>{fidelity(transitionMatchedFidelity)}</strong></div>
          <div className="transition-result-row"><span>Estimated pair rate</span><strong>{number(transitionMatchedRate, 1)} pairs/s</strong></div>
          <div className="transition-result-row"><span>Conversion modules</span><strong>0</strong></div>
        </div>
        <div className="transition-option">
          <span className="transition-option-tag secondary">NATIVE + CONVERSION</span>
          <b>Emitter transition → converter → {targetBand}-band fiber</b>
          <small>Conversion assumptions applied to the same link estimate</small>
          <div className="transition-result-row"><span>Estimated fidelity</span><strong>{fidelity(convertedFidelity)}</strong></div>
          <div className="transition-result-row"><span>Estimated pair rate</span><strong>{number(convertedRate, 1)} pairs/s</strong></div>
          <div className="transition-result-row"><span>Conversion modules</span><strong>1 per link</strong></div>
        </div>
      </div>
      <div className="transition-takeaway">
        <Zap size={15} />
        <span>With these assumptions, matching the emitter to {centerWavelength} nm avoids the converter loss and fidelity-retention penalty{gain ? `, yielding about ${gain}% more estimated pairs/s` : ''} on this link.</span>
      </div>
      <div className="notice small-notice transition-caveat">Illustrative architecture comparison. It assumes direct transition engineering preserves the selected band’s modeled link behavior; it does not model emitter availability, coupling, detector response, fabrication, or measured conversion noise. Confirm the trade-off with platform-specific data.</div>
    </Panel>
  );
}

function TtlOverFiberPlanner({ lengthKm }: { lengthKm: number }) {
  const [enabled, setEnabled] = useState(true);
  const [confirmSent, setConfirmSent] = useState(false);
  const [receiverPowerMw, setReceiverPowerMw] = useState(1.3);
  const propagationUs = lengthKm * 5;
  const receiverPowerDbm = 10 * Math.log10(receiverPowerMw);
  return (
    <Panel title="Single deployed fiber" sub="Quantum transmitter and receiver share one strand with the TTL-over-fiber control signal">
      <div className="ttl-planner-toggle">
        <div><b>Confirm TTL lane</b><small>Notify the receiver to commence polarization correction.</small></div>
        <label className="toggle-switch" aria-label="Enable TTL trigger lane on the shared fiber">
          <input type="checkbox" checked={enabled} onChange={(event) => { const next = event.target.checked; setEnabled(next); if (!next) setConfirmSent(false); }} />
          <span />
        </label>
      </div>
      <div className="single-fiber-architecture" role="img" aria-label={`Quantum transmitter and receiver share one ${lengthKm} kilometer fiber; Confirm TTL at 1470 nanometers travels to the receiver`}>
        <div className="fiber-site">
          <div className="fiber-device"><Radio size={17} /><b>Confirm TTL</b><small>1470 nm · control</small></div>
          <div className="fiber-device ttl-endpoint"><Boxes size={16} /><b>OZ TTL TX</b><small>TTL → optical</small></div>
          <div className="fiber-device"><Zap size={17} /><b>Quantum TX</b><small>Emitter</small></div>
        </div>
        <div className="shared-strand">
          <div className="shared-strand-label"><i /> <b>ONE DEPLOYED FIBER · {lengthKm} km</b> <i /></div>
          <div className="fiber-lane quantum-lane"><span>Quantum channel</span><b>──────────────→</b></div>
          <div className={`fiber-lane ttl-lane ${enabled ? '' : 'disabled'}`}><span>Confirm TTL · 1470 nm</span><b>──────────────→</b></div>
        </div>
        <div className="fiber-site">
          <div className="pre-wdm-reading"><Activity size={14} /><b>{number(receiverPowerMw, 2)} mW</b><small>Receiver ingress</small></div>
          <div className="fiber-device first-wdm"><Boxes size={17} /><b>WDM 1</b><small>First demux</small></div>
          <div className="fiber-device ttl-endpoint"><Boxes size={16} /><b>OZ TTL RX</b><small>Optical → TTL</small></div>
          <div className="fiber-device"><Network size={17} /><b>Quantum RX</b><small>Detector</small></div>
        </div>
      </div>
      <div className="receiver-power-measurement">
        <label htmlFor="receiver-ingress-power">Total telecom optical power · measured before receiver WDM 1</label>
        <div className="power-reading-input"><input id="receiver-ingress-power" type="number" min="0.001" max="1000" step="0.01" value={receiverPowerMw} onChange={(event) => setReceiverPowerMw(Math.min(1000, Math.max(0.001, Number(event.target.value) || 0.001)))} /><span>mW</span></div>
        <div className="power-reading-dbm"><small>Equivalent optical level</small><b>{number(receiverPowerDbm, 2)} dBm</b></div>
      </div>
      <div className="polarization-handshake">
        <div className={`handshake-state ${confirmSent ? 'received' : ''}`}>
          <span className="handshake-indicator" />
          <div><b>{confirmSent ? 'Preview: receiver notified' : 'Awaiting confirmation'}</b><small>{confirmSent ? 'Piezoelectric fiber squeezer correction staged in this UI preview' : 'Confirm TTL instructs the receiver to start polarization correction'}</small></div>
        </div>
        <div className="handshake-actions">
          <button className="primary-button small-button" disabled={!enabled || confirmSent} onClick={() => setConfirmSent(true)}>
            Preview Confirm TTL · 1470 nm
            <ArrowUpRight size={14} />
          </button>
          {confirmSent && <button className="text-button" onClick={() => setConfirmSent(false)}>Reset preview</button>}
        </div>
      </div>
      <div className="ttl-metrics">
        <div><small>Estimated one-way fiber delay</small><b>{enabled ? `${number(propagationUs, 1)} μs` : 'Path disabled'}</b></div>
        <div><small>Deployed fiber strands</small><b>1 shared</b></div>
        <div><small>TTL converter endpoints</small><b>{enabled ? '2 · TX + RX' : 'Inactive'}</b></div>
      </div>
      <div className="notice small-notice ttl-caveat">1.3 mW is the provided pre-WDM receiver measurement reference; update it with the current meter reading. The button previews the handshake in the UI; it does not send a hardware signal or verify polarization lock. Confirm power-meter calibration, wavelength range, pulse timing, filtering, and coexistence against the installed equipment. Power is displayed for monitoring only and is not yet coupled to the quantum-fidelity model.</div>
    </Panel>
  );
}

function FecBandwidthPlanner() {
  const [lineRateMbps, setLineRateMbps] = useState(1000);
  const [codeRate, setCodeRate] = useState(0.8);
  const [enabled, setEnabled] = useState(true);
  const effectiveRate = enabled ? codeRate : 1;
  const payloadMbps = lineRateMbps * effectiveRate;
  const redundantMbps = lineRateMbps - payloadMbps;
  const overheadPct = payloadMbps > 0 ? (redundantMbps / payloadMbps) * 100 : 0;
  const neededMbps = payloadMbps > 0 ? lineRateMbps / effectiveRate : 0;
  return (
    <Panel title="Forward error correction · bandwidth budget" sub="Trade redundant bits for protected classical payload capacity">
      <div className="fec-controls">
        <label className="form-field">
          FEC encoding
          <select value={enabled ? 'on' : 'off'} onChange={(event) => setEnabled(event.target.value === 'on')}>
            <option value="on">Enabled</option>
            <option value="off">Disabled · raw line rate</option>
          </select>
        </label>
        <label className="form-field">
          Available line capacity (Mbps)
          <input type="number" min={1} max={100000} step={10} value={lineRateMbps} onChange={(event) => setLineRateMbps(Math.max(1, Number(event.target.value) || 1))} />
        </label>
        <label className="form-field">
          FEC code rate
          <select value={codeRate} onChange={(event) => setCodeRate(Number(event.target.value))} disabled={!enabled}>
            <option value={0.5}>1/2 · robust, 100% overhead</option>
            <option value={0.6667}>2/3 · 50% overhead</option>
            <option value={0.75}>3/4 · 33% overhead</option>
            <option value={0.8}>4/5 · 25% overhead</option>
            <option value={0.8333}>5/6 · 20% overhead</option>
            <option value={0.9}>9/10 · 11% overhead</option>
          </select>
          <small>Code rate = payload bits / encoded bits</small>
        </label>
      </div>
      <div className="fec-budget-bar" role="img" aria-label={`${number(payloadMbps, 1)} megabits per second payload and ${number(redundantMbps, 1)} megabits per second FEC redundancy`}>
        <div className="fec-payload" style={{ width: `${effectiveRate * 100}%` }}><span>Payload</span><b>{number(payloadMbps, 1)} Mbps</b></div>
        {enabled && <div className="fec-redundancy" style={{ width: `${(1 - effectiveRate) * 100}%` }}><span>FEC</span><b>{number(redundantMbps, 1)}</b></div>}
      </div>
      <div className="fec-metrics">
        <div><small>Payload goodput budget</small><b>{number(payloadMbps, 1)} Mbps</b></div>
        <div><small>Redundancy bandwidth</small><b>{number(redundantMbps, 1)} Mbps</b></div>
        <div><small>Overhead vs. payload</small><b>{number(overheadPct, 1)}%</b></div>
      </div>
      <div className="fec-takeaway"><Radio size={15} /><span>At this setting, {number(payloadMbps, 1)} Mbps of classical payload occupies {number(lineRateMbps, 1)} Mbps of line capacity. Delivering the same payload with FEC requires about {number(neededMbps, 1)} Mbps before framing and other protocol overhead.</span></div>
      <div className="notice small-notice fec-caveat">This is a bandwidth accounting tool, not a codec/decoder simulation. Correction strength and post-FEC error rate depend on the selected code, block size, interleaving, and measured channel error statistics. Classical FEC does not directly alter the modeled quantum-state fidelity.</div>
    </Panel>
  );
}

function Range({
  label,
  value,
  min,
  max,
  step,
  unit,
  displayScale = 1,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit: string;
  displayScale?: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="range-field">
      <span>
        {label}
        <b>
          {number(value * displayScale, 2)} {unit}
        </b>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <small>
        {min * displayScale}–{max * displayScale} {unit}
      </small>
    </label>
  );
}

function Simulate() {
  const navigate = useNavigate(),
    principal = useSession((s) => s.principal),
    [policy, setPolicy] = useState<'adaptive' | 'static_c' | 'static_o' | 'adaptive_risk'>(
      'adaptive',
    ),
    [riskAlpha, setRiskAlpha] = useState(0.1),
    [preset, setPreset] = useState<'metro' | 'tiny'>('metro'),
    [seed, setSeed] = useState(42),
    [hours, setHours] = useState(24),
    [dt, setDt] = useState(60),
    [storm, setStorm] = useState(true),
    [wind, setWind] = useState(18),
    [traffic, setTraffic] = useState(0.45),
    [arrival, setArrival] = useState(0.25),
    [error, setError] = useState('');
  const mutation = useMutation({
    mutationFn: createRun,
    onSuccess: (r) => {
      void queryClient.invalidateQueries({ queryKey: ['runs'] });
      navigate(`/runs/${r.id}`);
    },
    onError: (e) =>
      setError(
        e instanceof ApiError
          ? e.status === 409 && e.message === 'model_not_calibrated'
            ? 'Risk-aware routing is unavailable because the active model has no calibration for that α.'
            : `${e.message}${e.retryAfterS ? ` — retry in ${e.retryAfterS}s` : ''}${e.requestId ? ` (request ${e.requestId})` : ''}`
          : 'Run could not be started',
      ),
  });
  const model = useQuery({ queryKey: ['ml-model'], queryFn: mlModel, retry: false });
  const riskAlphas = model.data?.calibration?.alphas.map(Number).filter((x): x is 0.05 | 0.1 | 0.2 => x === 0.05 || x === 0.1 || x === 0.2) ?? [];
  const riskEnabled = riskAlphas.length > 0;
  const steps = nSteps(hours, dt),
    requests = expectedRequests(arrival, hours, dt),
    invalid = steps > 5760 || requests > 20000;
  const roleAllowed =
    principal?.role === 'operator' || principal?.role === 'admin';
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    const body = {
      policy,
      risk_alpha: policy === 'adaptive_risk' ? riskAlpha : undefined,
      seed,
      duration_hours: hours,
      dt_s: dt,
      topology_preset: preset,
      scenario: {
        traffic_base: traffic,
        storm_enabled: storm,
        storm_wind_peak_ms: wind,
        arrival_rate_per_step: arrival,
      },
    };
    mutation.mutate(body as Parameters<typeof createRun>[0]);
  };
  return (
    <>
      <PageHeading
        eyebrow="SIMULATION WORKSPACE"
        title="Build a scenario"
        description="Configure a simulated network day and run it against a routing policy."
        action={
          <span className="run-quota">
            <span className="health-dot green" /> Quota available
          </span>
        }
      />
      <form onSubmit={submit} className="simulate-layout">
        <div className="simulate-main">
          <Panel
            title="Simulation setup"
            sub="Choose a policy and shape your run."
          >
            <div className="form-grid">
              <label className="form-field span-2">
                Routing policy
                <select
                  value={policy}
                  onChange={(e) => setPolicy(e.target.value as typeof policy)}
                >
                  <option value="adaptive">
                    Adaptive · predictive routing
                  </option>
                  <option value="static_c">Static C-band</option>
                  <option value="static_o">Static O-band</option>
                  <option value="adaptive_risk" disabled={!riskEnabled} title={!riskEnabled ? 'The active model is not calibrated' : undefined}>
                    Adaptive risk · lower confidence bound
                  </option>
                </select>
                <small>
                  Adaptive combines predictive routing, band selection and
                  admission control.
                </small>
              </label>
              {policy === 'adaptive_risk' && (
                <label className="form-field">
                  Risk level α
                  <select value={riskAlpha} onChange={(e) => setRiskAlpha(Number(e.target.value))} disabled={!riskEnabled} title={!riskEnabled ? 'The active model is not calibrated' : undefined}>
                    {(riskAlphas.length ? riskAlphas : [0.05, 0.1, 0.2]).map((alpha) => <option key={alpha} value={alpha}>{alpha}</option>)}
                  </select>
                  <small>{riskEnabled ? 'Admits only when the lower confidence estimate meets the SLA.' : 'Unavailable: the active model has no calibrated intervals.'}</small>
                </label>
              )}
              <label className="form-field">
                Topology preset
                <select
                  value={preset}
                  onChange={(e) => setPreset(e.target.value as typeof preset)}
                >
                  <option value="metro">Metro · 6 nodes</option>
                  <option value="tiny">Tiny · 3 nodes</option>
                </select>
              </label>
              <label className="form-field">
                Random seed
                <div className="input-with-action">
                  <input
                    type="number"
                    min={0}
                    max={2147483647}
                    value={seed}
                    onChange={(e) => setSeed(Number(e.target.value))}
                  />
                  <button
                    type="button"
                    className="icon-button"
                    title="Randomize seed"
                    onClick={() => setSeed(Math.floor(Math.random() * 1000000))}
                  >
                    🎲
                  </button>
                </div>
              </label>
              <label className="form-field">
                Duration (hours)
                <input
                  type="number"
                  min={1}
                  max={48}
                  step={1}
                  value={hours}
                  onChange={(e) => setHours(Number(e.target.value))}
                />
              </label>
              <label className="form-field">
                Step interval (seconds)
                <select
                  value={dt}
                  onChange={(e) => setDt(Number(e.target.value))}
                >
                  {[15, 30, 60, 120, 300, 600].map((n) => (
                    <option key={n}>{n}</option>
                  ))}
                </select>
              </label>
            </div>
          </Panel>
          <Panel
            title="Scenario conditions"
            sub="Weather and traffic influence link fidelity across the day."
          >
            <div className="scenario-heading">
              <div className="eyebrow">WEATHER & CLASSICAL TRAFFIC</div>
              <label className="switch-label">
                <input
                  type="checkbox"
                  checked={storm}
                  onChange={(e) => setStorm(e.target.checked)}
                />
                <span>Storm event enabled</span>
              </label>
            </div>
            <div className="scenario-ranges">
              <Range
                label="Classical traffic base"
                value={traffic}
                min={0}
                max={1}
                step={0.05}
                unit=""
                onChange={setTraffic}
              />
              <Range
                label="Storm wind peak"
                value={wind}
                min={0}
                max={45}
                step={1}
                unit="m/s"
                onChange={setWind}
              />
              <Range
                label="Request arrival rate"
                value={arrival}
                min={0}
                max={2}
                step={0.05}
                unit="per step"
                onChange={setArrival}
              />
            </div>
            <div className="preset-row">
              <span>SCENARIO PRESETS</span>
              {[
                ['Default day', 0.45, true, 18],
                ['Calm day', 0.45, false, 18],
                ['Severe storm', 0.45, true, 30],
                ['Heavy traffic', 0.6, true, 18],
              ].map(([name, t, s, w]) => (
                <button
                  type="button"
                  key={String(name)}
                  className="preset-chip"
                  onClick={() => {
                    setTraffic(Number(t));
                    setStorm(Boolean(s));
                    setWind(Number(w));
                  }}
                >
                  {String(name)}
                </button>
              ))}
            </div>
          </Panel>
          <div className={`budget-panel ${invalid ? 'over' : ''}`}>
            <span className="budget-icon">
              <Gauge size={19} />
            </span>
            <div className="budget-title">
              <b>Compute budget</b>
              <small>Run limits are enforced by the backend.</small>
            </div>
            <div className="budget-stat">
              <b>
                {number(steps)} <small>/ 5,760</small>
              </b>
              <span>steps</span>
            </div>
            <div className="budget-stat">
              <b>
                {number(requests, 1)} <small>/ 20,000</small>
              </b>
              <span>expected requests</span>
            </div>
          </div>
          {error && (
            <div className="form-alert" role="alert">
              {error}
            </div>
          )}
          {!roleAllowed && (
            <div className="notice">
              Your key has viewer access. Simulation controls require an
              operator key.
            </div>
          )}
          <div className="form-footer">
            <button
              type="button"
              className="secondary-button"
              onClick={() =>
                navigator.clipboard.writeText(
                  JSON.stringify(
                    {
                      policy,
                      seed,
                      duration_hours: hours,
                      dt_s: dt,
                      topology_preset: preset,
                    },
                    null,
                    2,
                  ),
                )
              }
            >
              Copy configuration JSON
            </button>
            <button
              className="primary-button"
              disabled={!roleAllowed || invalid || mutation.isPending}
            >
              {mutation.isPending ? (
                <>
                  <span className="spinner" /> Starting…
                </>
              ) : (
                <>
                  Launch simulation <ArrowUpRight size={16} />
                </>
              )}
            </button>
          </div>
        </div>
        <aside className="simulate-side">
          <Panel title="Scenario preview" sub="Metro topology · 9 shared links">
            <MiniTopology />
            <div className="preview-stats">
              <div>
                <small>ROUTING POLICY</small>
                <b>{policy.replace('_', ' ').toUpperCase()}</b>
              </div>
              <div>
                <small>STORM CONDITIONS</small>
                <b>{storm ? `${wind} m/s peak wind` : 'Disabled'}</b>
              </div>
              <div>
                <small>SIMULATION WINDOW</small>
                <b>
                  {hours}h · {dt}s intervals
                </b>
              </div>
            </div>
          </Panel>
          <div className="notice">
            <Cloud size={17} />
            <span>
              <b>Simulated digital twin</b>
              <small>
                Physical constants are illustrative, not calibrated to a
                specific experiment.
              </small>
            </span>
          </div>
        </aside>
      </form>
    </>
  );
}

function Runs() {
  const q = useQuery({
    queryKey: ['runs'],
    queryFn: runs,
    refetchInterval: (q) =>
      q.state.data?.some((x) => x.status === 'queued' || x.status === 'running')
        ? 3000
        : false,
  });
  return (
    <>
      <PageHeading
        eyebrow="RUN HISTORY"
        title="Simulation runs"
        description="Inspect previous runs, monitor in-flight work and replay completed simulations."
        action={
          <Link to="/simulate" className="primary-button">
            <Play size={16} /> New simulation
          </Link>
        }
      />
      <Panel
        title="All runs"
        sub={`${q.data?.length ?? 0} simulations in your workspace`}
        action={
          <button
            className="secondary-button small-button"
            onClick={() => void q.refetch()}
          >
            Refresh
          </button>
        }
      >
        {q.isLoading ? (
          <Skeleton height={260} />
        ) : q.isError ? (
          <ErrorBlock error={q.error} />
        ) : !q.data?.length ? (
          <Empty
            title="No simulations yet"
            description="Create a run to see it here."
            to="/simulate"
            label="Build a scenario"
          />
        ) : (
          <Table heads={['Run ID', 'Created', 'Policy', 'Status', 'Results']}>
            <>
              {q.data.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link className="mono text-link" to={`/runs/${r.id}`}>
                      {r.id}
                    </Link>
                  </td>
                  <td>
                    {r.created_at
                      ? new Date(r.created_at).toLocaleString()
                      : '—'}
                  </td>
                  <td>Network simulation</td>
                  <td>
                    <Status status={r.status} />
                  </td>
                  <td>
                    {r.status === 'done' ? (
                      <Link className="text-link" to={`/runs/${r.id}`}>
                        View run <ArrowUpRight size={13} />
                      </Link>
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              ))}
            </>
          </Table>
        )}
      </Panel>
    </>
  );
}

function RunDetail({ id }: { id: string }) {
  const statusList = useQuery({
    queryKey: ['runs'],
    queryFn: runs,
    refetchInterval: (q) =>
      q.state.data?.some(
        (item) => item.status === 'queued' || item.status === 'running',
      )
        ? 3000
        : false,
  });
  const currentStatus = statusList.data?.find((item) => item.id === id)?.status;
  const q = useQuery({
    queryKey: ['run', id],
    queryFn: () => run(id),
    enabled: Boolean(id),
  });
  const refetchRun = q.refetch;
  useEffect(() => {
    if (currentStatus === 'done' || currentStatus === 'error')
      void refetchRun();
  }, [currentStatus, refetchRun]);
  const [tab, setTab] = useState('Summary'),
    [streaming, setStreaming] = useState(false);
  useRunStream(id, streaming);
  usePlayback();
  useEffect(() => () => useReplay.getState().clear(), [id]);
  const replay = useReplay();
  return (
    <>
      <PageHeading
        eyebrow="SIMULATION REPLAY"
        title={`Run ${id.slice(0, 12)}`}
        description="Inspect the backend's simulated run summary and replay link conditions."
        action={
          <>
            <Status status={q.data?.status ?? 'loading'} />
            <button
              className="secondary-button"
              onClick={() => {
                if (q.data)
                  void navigator.clipboard.writeText(
                    JSON.stringify(q.data.summary, null, 2),
                  );
              }}
            >
              Download summary JSON
            </button>
          </>
        }
      />
      {q.isLoading ? (
        <Skeleton height={320} />
      ) : q.isError ? (
        <ErrorBlock error={q.error} />
      ) : (
        q.data && (
          <>
            <div className="run-meta">
              <span>
                Created{' '}
                <b>
                  {q.data.created_at
                    ? new Date(q.data.created_at).toLocaleString()
                    : '—'}
                </b>
              </span>
              <span>
                Duration{' '}
                <b>
                  {q.data.config.duration_hours}h at {q.data.config.dt_s}s
                </b>
              </span>
              <span>
                Policy <b>{q.data.config.policy}</b>
              </span>
              <span>
                Preset <b>{q.data.config.topology_preset}</b>
              </span>
            </div>
            {q.data.status === 'queued' || q.data.status === 'running' ? (
              <div className="notice">
                <span className="spinner" /> Simulation {q.data.status}; status
                refreshes every few seconds.
              </div>
            ) : q.data.status === 'error' ? (
              <div className="form-alert">
                {q.data.error ?? 'Simulation failed.'} Try reducing the duration
                or increasing the step interval.
              </div>
            ) : (
              q.data.summary && (
                <>
                  <div className="metric-grid run-kpis">
                    <Metric
                      icon={Zap}
                      label="SLA-satisfied pairs"
                      value={number(q.data.summary.sla_satisfied_pairs, 2)}
                    />
                    <Metric
                      icon={Activity}
                      label="Mean fidelity"
                      value={fidelity(q.data.summary.mean_fidelity)}
                    />
                    <Metric
                      icon={Radio}
                      label="Total requests"
                      value={number(q.data.summary.total_requests)}
                    />
                    <Metric
                      icon={ArrowDownRight}
                      label="Violation fraction"
                      value={percent(q.data.summary.violation_fraction)}
                    />
                  </div>
                  <Panel
                    title="Run results"
                    sub="Values reported directly by the backend simulation."
                  >
                    <div className="tabs">
                      {['Summary', 'Topology', 'Timeseries'].map((t) => (
                        <button
                          className={tab === t ? 'selected' : ''}
                          onClick={() => setTab(t)}
                          key={t}
                        >
                          {t}
                        </button>
                      ))}
                    </div>
                    {tab === 'Summary' ? (
                      <Table heads={['Metric', 'Value', 'Definition']}>
                        {Object.entries(q.data.summary).map(([k, v]) => (
                          <tr key={k}>
                            <td>{k.replaceAll('_', ' ')}</td>
                            <td className="mono">
                              {typeof v === 'number' ? number(v, 4) : String(v)}
                            </td>
                            <td>Backend-reported simulation output</td>
                          </tr>
                        ))}
                      </Table>
                    ) : tab === 'Topology' ? (
                      <RunTopology
                        preset={q.data.config.topology_preset ?? 'metro'}
                      />
                    ) : (
                      <RunSeries id={id} />
                    )}
                  </Panel>
                  <Panel
                    title="Replay"
                    sub={
                      replay.status === 'ready'
                        ? `${replay.records.length} steps streamed from the backend`
                        : 'Stream recorded step conditions using a single-use WebSocket ticket.'
                    }
                  >
                    <div className="replay-toolbar">
                      <button
                        className="secondary-button"
                        onClick={() => setStreaming(true)}
                        disabled={streaming || replay.status === 'loading'}
                      >
                        {streaming ? (
                          <>
                            <span className="spinner" /> Loading stream…
                          </>
                        ) : (
                          <>
                            Load replay records <Play size={14} />
                          </>
                        )}
                      </button>
                      {replay.status === 'loading' && (
                        <span className="muted-text">
                          {number(replay.records.length)} /{' '}
                          {number(replay.nSteps)} steps received
                        </span>
                      )}
                      {replay.error && (
                        <span className="form-alert">{replay.error}</span>
                      )}
                    </div>
                    {replay.records.length > 0 && (
                      <>
                        <div className="player-controls">
                          <button
                            className="icon-button"
                            aria-label="Previous step"
                            onClick={() => replay.step(-1)}
                          >
                            ‹
                          </button>
                          <button
                            className="primary-button"
                            onClick={() =>
                              replay.playing ? replay.pause() : replay.play()
                            }
                          >
                            {replay.playing ? 'Pause' : 'Play'}
                          </button>
                          <button
                            className="icon-button"
                            aria-label="Next step"
                            onClick={() => replay.step(1)}
                          >
                            ›
                          </button>
                          <input
                            aria-label="Replay position"
                            type="range"
                            min={0}
                            max={replay.records.length - 1}
                            value={replay.cursor}
                            onChange={(e) =>
                              replay.seek(Number(e.target.value))
                            }
                          />
                          <span className="mono">
                            {number(Math.floor(replay.cursor) + 1)} /{' '}
                            {number(replay.records.length)}
                          </span>
                          <select
                            aria-label="Playback rate"
                            value={replay.rate}
                            onChange={(e) =>
                              replay.setRate(Number(e.target.value))
                            }
                          >
                            {[1, 5, 10, 25, 50, 100, 250].map((n) => (
                              <option key={n} value={n}>
                                {n}×
                              </option>
                            ))}
                          </select>
                        </div>
                        <ReplaySnapshot
                          record={replay.records[Math.floor(replay.cursor)]}
                        />
                      </>
                    )}
                  </Panel>
                </>
              )
            )}
          </>
        )
      )}
    </>
  );
}
function RunTopology({ preset }: { preset: string }) {
  const q = useQuery({
    queryKey: ['topology', preset],
    queryFn: () => topology(preset),
  });
  if (!q.data) return <Skeleton height={300} />;
  return (
    <div className="topology-box">
      <TopologyView
        nodes={q.data.nodes.map((n) => (typeof n === 'string' ? n : n.id))}
        links={q.data.links}
      />
    </div>
  );
}
function RunSeries({ id }: { id: string }) {
  const q = useQuery({
    queryKey: ['timeseries', id],
    queryFn: () => timeseries(id),
  });
  if (q.isLoading) return <Skeleton height={240} />;
  if (q.isError) return <ErrorBlock error={q.error} />;
  const key =
    Object.keys(q.data ?? {}).find((name) => name === 'useful_rate_pairs_s') ??
    Object.keys(q.data ?? {}).find((name) => name === 'mean_fidelity');
  const values = key ? (q.data?.[key] ?? []) : [];
  const rows = values.map((value, index) => ({ time: index, value }));
  return (
    <>
      <h3 className="chart-title">
        {key?.replaceAll('_', ' ') ?? 'Timeseries'}{' '}
        <small>backend values by sample index</small>
      </h3>
      <Suspense fallback={<Skeleton height={240} />}>
        <TimeSeriesChart data={rows} />
      </Suspense>
      <Table heads={['Field', 'Samples', 'First value', 'Last value']}>
        {Object.entries(q.data ?? {}).map(([k, v]) => (
          <tr key={k}>
            <td>{k}</td>
            <td>{v.length}</td>
            <td>{String(v[0] ?? '—')}</td>
            <td>{String(v[v.length - 1] ?? '—')}</td>
          </tr>
        ))}
      </Table>
    </>
  );
}
function ReplaySnapshot({
  record,
}: {
  record: import('./api/schemas').StepRecord | undefined;
}) {
  if (!record) return null;
  return (
    <>
      <ReplayTopology record={record} />
      <div className="replay-snapshot">
        <div>
          <small>SIMULATED TIME</small>
          <b>
            Day {Math.floor(record.t_s / 86400) + 1} ·{' '}
            {new Date(record.t_s * 1000).toISOString().slice(11, 16)}
          </b>
        </div>
        <div>
          <small>ACTIVE REQUESTS</small>
          <b>{number(record.active)}</b>
        </div>
        <div>
          <small>MEAN FIDELITY</small>
          <b>
            {record.mean_fidelity === null
              ? '—'
              : fidelity(record.mean_fidelity)}
          </b>
        </div>
        <div>
          <small>LINKS IN RECORD</small>
          <b>{Object.keys(record.links).length}</b>
        </div>
      </div>
    </>
  );
}
function ReplayTopology({
  record,
}: {
  record: import('./api/schemas').StepRecord;
}) {
  const q = useQuery({
    queryKey: ['topology', 'metro'],
    queryFn: () => topology('metro'),
  });
  if (!q.data) return <Skeleton height={180} />;
  return (
    <div className="topology-box replay-topology">
      <TopologyView
        nodes={q.data.nodes.map((n) => (typeof n === 'string' ? n : n.id))}
        links={q.data.links}
        snapshot={record.links}
      />
    </div>
  );
}

function Compare() {
  const [id, setId] = useState(''),
    [message, setMessage] = useState('');
  const role = useSession((s) => s.principal?.role);
  const canCompare = role === 'operator' || role === 'admin';
  const create = useMutation({
    mutationFn: createBenchmark,
    onSuccess: (b) => {
      setId(b.id);
      setMessage(
        'Benchmark started. This comparison runs each policy against the same seeded scenario.',
      );
    },
    onError: (e) =>
      setMessage(e instanceof Error ? e.message : 'Could not start benchmark'),
  });
  const q = useQuery({
    queryKey: ['bench', id],
    queryFn: () => benchmark(id),
    enabled: Boolean(id),
    refetchInterval: (q) =>
      q.state.data?.status === 'queued' || q.state.data?.status === 'running'
        ? 3000
        : false,
  });
  return (
    <>
      <PageHeading
        eyebrow="POLICY ANALYSIS"
        title="Compare policies"
        description="Evaluate static C, static O and adaptive routing on a shared seed and scenario."
        action={
          <button
            className="primary-button"
            onClick={() =>
              create.mutate({
                seed: 42,
                duration_hours: 24,
                dt_s: 300,
                topology_preset: 'metro',
                scenario: {},
              })
            }
            disabled={create.isPending || !canCompare}
            title={!canCompare ? 'Operator key required' : undefined}
          >
            <GitCompareArrows size={16} /> Run comparison
          </button>
        }
      />
      {message && <div className="notice">{message}</div>}
      <div className="metric-grid compare-intro">
        <Metric icon={Radio} label="Static C-band" value="Baseline" />
        <Metric icon={Waves} label="Static O-band" value="Baseline" />
        <Metric icon={Zap} label="Adaptive" value="Predictive" />
        <Metric icon={Activity} label="Headline metric" value="SLA pairs" />
      </div>
      <Panel
        title="Benchmark results"
        sub="SLA-satisfied entanglement throughput · backend values, no client-side adjustment"
      >
        {!id ? (
          <Empty
            title="No comparison yet"
            description="Run a seeded benchmark to compare all three policies."
          />
        ) : q.isLoading ? (
          <Skeleton height={180} />
        ) : q.isError ? (
          <ErrorBlock error={q.error} />
        ) : q.data?.status !== 'done' ? (
          <div className="notice">
            <span className="spinner" /> Benchmark {q.data?.status ?? 'queued'}{' '}
            · polling every 3 seconds.
          </div>
        ) : (
          <BenchmarkResults result={q.data} />
        )}
      </Panel>
      <div className="notice">
        <CircleHelp size={16} />
        <span>
          <b>How to read this comparison</b>
          <small>
            SLA-satisfied pairs are delivered pairs that meet the requested
            fidelity. Results describe a simulated digital twin.
          </small>
        </span>
      </div>
    </>
  );
}
function BenchmarkResults({
  result,
}: {
  result: Awaited<ReturnType<typeof benchmark>>;
}) {
  const rows = Object.entries(result.results ?? {});
  return (
    <>
      <Table
        heads={[
          'Policy',
          'SLA-satisfied pairs',
          'Mean fidelity',
          'Violation fraction',
        ]}
      >
        {rows.map(([policy, v]) => {
          const r = (typeof v === 'object' && v !== null ? v : {}) as Record<
            string,
            unknown
          >;
          return (
            <tr key={policy}>
              <td>
                <span className={`policy-tag ${policy}`}>●</span> {policy}
              </td>
              <td>
                {typeof r.sla_satisfied_pairs === 'number'
                  ? number(r.sla_satisfied_pairs, 2)
                  : '—'}
              </td>
              <td>
                {typeof r.mean_fidelity === 'number'
                  ? fidelity(r.mean_fidelity)
                  : '—'}
              </td>
              <td>
                {typeof r.violation_fraction === 'number'
                  ? percent(r.violation_fraction)
                  : '—'}
              </td>
            </tr>
          );
        })}
      </Table>
      <p className="derived-note">
        Improvement percentages below are reported by the backend benchmark.
      </p>
      <pre className="json-view">
        {JSON.stringify(result.improvement ?? {}, null, 2)}
      </pre>
    </>
  );
}

function Benchmarks() {
  const queryClient = useQueryClient();
  const role = useSession((s) => s.principal?.role);
  const canCompare = role === 'operator' || role === 'admin';
  const [id, setId] = useState(storedBenchmarkId() ?? '');
  const history = useQuery({ queryKey: ['benchmarks'], queryFn: benchmarks });
  const create = useMutation({
    mutationFn: createBenchmark,
    onSuccess: (b) => {
      setId(b.id);
      void queryClient.invalidateQueries({ queryKey: ['benchmarks'] });
      const entries = [
        b.id,
        ...(JSON.parse(sessionStorage.getItem('eo.bench') ?? '[]') as string[]),
      ].slice(0, 20);
      sessionStorage.setItem('eo.bench', JSON.stringify(entries));
    },
  });
  useEffect(() => {
    if (!id && history.data?.length) setId(history.data[0].id);
  }, [history.data, id]);
  const q = useQuery({
    queryKey: ['bench', id],
    queryFn: () => benchmark(id),
    enabled: Boolean(id),
    refetchInterval: (q) =>
      q.state.data?.status === 'queued' || q.state.data?.status === 'running'
        ? 3000
        : false,
  });
  return (
    <>
      <PageHeading
        eyebrow="BENCHMARKS"
        title="Benchmark runs"
        description="Compare policies using the backend's seeded evaluation and reported improvement metrics."
        action={
          <button
            className="primary-button"
            onClick={() =>
              create.mutate({
                seed: 42,
                duration_hours: 24,
                dt_s: 300,
                topology_preset: 'metro',
                scenario: {},
              })
            }
            disabled={!canCompare}
            title={!canCompare ? 'Operator key required' : undefined}
          >
            <BarChart3 size={16} /> New benchmark
          </button>
        }
      />
      <Panel
        title="Recent benchmark"
        sub={id ? `Benchmark ${id}` : 'No benchmark selected'}
      >
        {create.error && <ErrorBlock error={create.error} />}{' '}
        {!id ? (
          <Empty
            title="Benchmark history starts here"
            description="Run a benchmark to see its progress and results."
          />
        ) : q.isLoading ? (
          <Skeleton height={190} />
        ) : q.isError ? (
          <ErrorBlock error={q.error} />
        ) : q.data?.status !== 'done' ? (
          <div className="notice">
            <span className="spinner" /> Benchmark {q.data?.status}
          </div>
        ) : (
          <BenchmarkResults result={q.data} />
        )}
      </Panel>
      <Panel title="Persistent history" sub="Stored by the backend">
        {history.isLoading ? <Skeleton height={88} /> : history.isError ? <ErrorBlock error={history.error} /> :
          history.data?.length ? <div className="table-wrap"><table><thead><tr><th>Benchmark</th><th>Status</th><th>Created</th></tr></thead><tbody>
            {history.data.map((item) => <tr key={item.id}><td><button className="text-button" onClick={() => { setId(item.id); sessionStorage.setItem('eo.bench', JSON.stringify([item.id])); }}>{item.id}</button></td><td>{item.status}</td><td>{item.created_at ?? '—'}</td></tr>)}
          </tbody></table></div> : <Empty title="No stored benchmarks" description="Completed and queued benchmarks will appear here." />}
      </Panel>
    </>
  );
}

function Lab() {
  const model = useQuery({ queryKey: ['ml-model'], queryFn: mlModel, retry: false });
  const calibratedAlphas = model.data?.calibration?.alphas.map(Number).filter((x): x is 0.05 | 0.1 | 0.2 => x === 0.05 || x === 0.1 || x === 0.2) ?? [];
  const [alpha, setAlpha] = useState(0.1);
  const selectedAlphaCalibrated = calibratedAlphas.includes(alpha as 0.05 | 0.1 | 0.2);
  const [form, setForm] = useState({
    length_km: 30,
    aerial_fraction: 1,
    band: 'O' as 'C' | 'O',
    traffic_now: 0.5,
    traffic_trend: 0,
    temp_now: 18,
    dtemp_dt_now: 0,
    wind_now: 3,
    wind_trend: 0,
    wind_trend_15: undefined as number | undefined,
    traffic_trend_15: undefined as number | undefined,
    dtemp_trend_5: undefined as number | undefined,
    wind_max_30: undefined as number | undefined,
    traffic_mean_30: undefined as number | undefined,
    hour: 15,
  });
  const [output, setOutput] = useState<{
    werner: number;
    fidelity: number;
    werner_lo?: number;
    werner_hi?: number;
    fidelity_lo?: number;
    fidelity_hi?: number;
    inputs_imputed?: boolean;
  } | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const analytic = useMemo(
    () =>
      linkFidelity(
        { length_km: form.length_km, aerial_fraction: form.aerial_fraction },
        form.band,
        {
          traffic_load: form.traffic_now,
          dtemp_dt_c_per_h: form.dtemp_dt_now,
          wind_ms: form.wind_now,
        },
      ),
    [form],
  );
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setBusy(true);
      setError('');
      void predict({ ...form, alpha: selectedAlphaCalibrated ? alpha as 0.05 | 0.1 | 0.2 : undefined })
        .then(setOutput)
        .catch((e) =>
          setError(e instanceof ApiError && e.message === 'model_not_calibrated' ? 'This model has no calibrated interval for the selected α.' : e instanceof Error ? e.message : 'Predictor request failed'),
        )
        .finally(() => setBusy(false));
    }, 500);
    return () => window.clearTimeout(timer);
  }, [form, alpha, selectedAlphaCalibrated]);
  const update = (name: keyof typeof form, value: number | string) =>
    setForm((old) => ({ ...old, [name]: value }));
  return (
    <>
      <PageHeading
        eyebrow="MODEL EXPLORER"
        title="Physics & predictor"
        description="Explore the illustrative link model and request a prediction from the backend predictor."
      />
      <div className="content-grid lab-grid">
        <Panel
          title="Predictor playground"
          sub="Calls POST /api/v1/predict · debounced 500 ms"
        >
          <div className="form-grid">
            <label className="form-field">
              Link length (km)
              <input
                type="number"
                min={0.1}
                max={200}
                value={form.length_km}
                onChange={(e) => update('length_km', Number(e.target.value))}
              />
            </label>
            <label className="form-field">
              Band
              <select
                value={form.band}
                onChange={(e) => update('band', e.target.value)}
              >
                <option>C</option>
                <option>O</option>
              </select>
            </label>
            <label className="form-field">
              Aerial fraction
              <input
                type="number"
                min={0}
                max={1}
                step={0.1}
                value={form.aerial_fraction}
                onChange={(e) =>
                  update('aerial_fraction', Number(e.target.value))
                }
              />
            </label>
            <label className="form-field">
              Traffic load
              <input
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={form.traffic_now}
                onChange={(e) => update('traffic_now', Number(e.target.value))}
              />
            </label>
            <label className="form-field">
              Temperature (°C)
              <input
                type="number"
                min={-40}
                max={60}
                value={form.temp_now}
                onChange={(e) => update('temp_now', Number(e.target.value))}
              />
            </label>
            <label className="form-field">
              Wind (m/s)
              <input
                type="number"
                min={0}
                max={60}
                value={form.wind_now}
                onChange={(e) => update('wind_now', Number(e.target.value))}
              />
            </label>
            <label className="form-field">
              Interval α
              <select value={alpha} disabled={!calibratedAlphas.length} onChange={(e) => setAlpha(Number(e.target.value))} title={!calibratedAlphas.length ? 'The active model is not calibrated' : undefined}>
                {(calibratedAlphas.length ? calibratedAlphas : [0.05, 0.1, 0.2]).map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
              <small>{calibratedAlphas.length ? 'Intervals are calibrated on simulated data.' : 'No calibrated interval is available.'}</small>
            </label>
          </div>
          <details className="advanced-inputs"><summary>Advanced inputs · v2 feature schema</summary><div className="form-grid">
            {([
              ['wind_trend_15', 'Wind trend · 15 steps', -60, 60],
              ['traffic_trend_15', 'Traffic trend · 15 steps', -1, 1],
              ['dtemp_trend_5', 'Cooling trend · 5 steps', -100, 100],
              ['wind_max_30', 'Maximum wind · 30 steps', 0, 60],
              ['traffic_mean_30', 'Mean traffic · 30 steps', 0, 1],
            ] as const).map(([key, title, min, max]) => <label className="form-field" key={key}>{title}<input type="number" min={min} max={max} value={form[key] ?? ''} onChange={(e) => update(key, e.target.value === '' ? undefined as never : Number(e.target.value))} /></label>)}
          </div></details>
          {error && <div className="form-alert">{error}</div>}
          <div className="predictor-output">
            <div>
              <small>BACKEND PREDICTOR</small>
              <b>
                {busy ? 'Updating…' : output ? fidelity(output.fidelity) : '—'}
              </b>
              <span>Predicted fidelity</span>
            </div>
            <div>
              <small>ANALYTIC PREVIEW</small>
              <b>{fidelity(analytic)}</b>
              <span>Illustrative model · not simulation output</span>
            </div>
          </div>
          {output?.fidelity_lo !== undefined && output.fidelity_hi !== undefined && <div className="interval-result"><span>Calibrated on simulated data · {alpha}</span><div className="interval-track" role="img" aria-label={`Fidelity interval from ${output.fidelity_lo.toFixed(3)} to ${output.fidelity_hi.toFixed(3)}`}><i style={{ left: `${Math.max(0,Math.min(100,(output.fidelity_lo-0.25)/0.75*100))}%`, width: `${Math.max(0,Math.min(100,(output.fidelity_hi-output.fidelity_lo)/0.75*100))}%` }} /></div><small>{fidelity(output.fidelity_lo)} – {fidelity(output.fidelity_hi)}</small></div>}
          {output?.inputs_imputed && <div className="notice small-notice">Some v2 advanced inputs were imputed from the supplied values.</div>}
        </Panel>
        <Panel
          title="Physics explorer"
          sub="Backend physics model · illustrative, not calibrated"
        >
          <div className="physics-cards">
            <div>
              <span className="band-pill c">C</span>
              <b>Higher throughput</b>
              <p>
                Lower attenuation at equal distance. Classical traffic can add
                Raman noise.
              </p>
            </div>
            <div>
              <span className="band-pill o">O</span>
              <b>Quieter band</b>
              <p>
                Lower Raman noise under classical load, often improving fidelity
                at distance.
              </p>
            </div>
          </div>
          <div className="notice small-notice">
            Analytic preview shown here is a client-side port of backend physics
            formulas; all operational results come from the backend.
          </div>
        </Panel>
      </div>
    </>
  );
}

function Admin({ role }: { role: string }) {
  const isAdmin = role === 'admin';
  const k = useQuery({
    queryKey: ['admin', 'keys'],
    queryFn: keys,
    enabled: isAdmin,
  });
  const a = useQuery({
    queryKey: ['admin', 'audit'],
    queryFn: () => audit(100),
    enabled: isAdmin,
  });
  const h = useQuery({
    queryKey: ['admin', 'health'],
    queryFn: adminHealth,
    enabled: isAdmin,
  });
  const [name, setName] = useState(''),
    [newRole, setNewRole] = useState<'viewer' | 'operator' | 'admin'>('viewer'),
    [created, setCreated] = useState(''),
    [showKey, setShowKey] = useState(false),
    [notice, setNotice] = useState(''),
    [checkStarted, setCheckStarted] = useState(false);
  const cc = useQuery({
    queryKey: ['admin', 'crosscheck'],
    queryFn: () => crosscheck(),
    enabled: isAdmin && checkStarted,
  });
  const make = useMutation({
    mutationFn: createKey,
    onSuccess: (r) => {
      setCreated(r.key);
      setShowKey(true);
      setNotice(
        `Created key ${r.key_id}. Copy it now; it will not be shown again.`,
      );
      void k.refetch();
    },
  });
  const revoke = useMutation({
    mutationFn: revokeKey,
    onSuccess: () => {
      setNotice('Key revoked.');
      void k.refetch();
    },
  });
  if (!isAdmin)
    return (
      <>
        <PageHeading
          eyebrow="ADMINISTRATION"
          title="Access restricted"
          description="Your key does not have access to this page."
        />
        <div className="notice">
          <ShieldCheck size={18} />
          <span>
            Admin permissions are required for keys, audit logs and detailed
            health.
          </span>
        </div>
      </>
    );
  return (
    <>
      <PageHeading
        eyebrow="CONTROL PLANE"
        title="Admin console"
        description="Manage API keys, inspect the audit trail and monitor system health."
      />
      <div className="admin-grid">
        <Panel title="API keys" sub="Keys are shown only once at creation.">
          <form
            className="inline-form"
            onSubmit={(e) => {
              e.preventDefault();
              make.mutate({ name, role: newRole });
            }}
          >
            <label className="form-field">
              Key name
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={64}
                required
              />
            </label>
            <label className="form-field">
              Role
              <select
                value={newRole}
                onChange={(e) => setNewRole(e.target.value as typeof newRole)}
              >
                <option value="viewer">Viewer</option>
                <option value="operator">Operator</option>
                <option value="admin">Admin</option>
              </select>
            </label>
            <button className="primary-button" disabled={make.isPending}>
              <KeyRound size={15} /> Create key
            </button>
          </form>
          {notice && <div className="notice small-notice">{notice}</div>}
          {k.isLoading ? (
            <Skeleton height={150} />
          ) : k.isError ? (
            <ErrorBlock error={k.error} />
          ) : (
            <Table heads={['Key ID', 'Name', 'Role', 'Created', 'Status']}>
              {(k.data ?? []).map((row) => (
                <tr key={row.key_id}>
                  <td className="mono">{row.key_id}</td>
                  <td>{row.name}</td>
                  <td>
                    <span className={`role-pill ${row.role}`}>{row.role}</span>
                  </td>
                  <td>
                    {row.created_at
                      ? new Date(row.created_at).toLocaleDateString()
                      : '—'}
                  </td>
                  <td>
                    {row.revoked ? (
                      'Revoked'
                    ) : (
                      <button
                        className="text-button danger-text"
                        onClick={() => {
                          const confirmId = window.prompt(
                            `Type key ID ${row.key_id} to revoke`,
                          );
                          if (confirmId === row.key_id)
                            revoke.mutate(row.key_id);
                        }}
                      >
                        Revoke
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </Table>
          )}
          {showKey && (
            <div
              className="modal-backdrop"
              role="presentation"
              onClick={() => {
                setShowKey(false);
                setCreated('');
              }}
            >
              <div
                className="modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="key-title"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="modal-icon">
                  <KeyRound size={20} />
                </div>
                <h2 id="key-title">Copy your new API key</h2>
                <p>This key is shown once. Store it securely before closing.</p>
                <code className="secret-key">{created}</code>
                <button
                  className="primary-button full"
                  onClick={() => {
                    void navigator.clipboard.writeText(created);
                    setShowKey(false);
                    setCreated('');
                  }}
                >
                  Copy key and close
                </button>
                <button
                  className="text-button modal-close"
                  onClick={() => {
                    setShowKey(false);
                    setCreated('');
                  }}
                >
                  Close and scrub key
                </button>
              </div>
            </div>
          )}
        </Panel>
        <div className="admin-side">
          <Panel title="System health" sub="Backend monitoring checks">
            {h.isLoading ? (
              <Skeleton height={140} />
            ) : h.isError ? (
              <ErrorBlock error={h.error} />
            ) : (
              <>
                {h.data?.checks.audit_chain_ok === false && (
                  <div className="form-alert">
                    Audit chain verification failed. Review the backend audit
                    log immediately.
                  </div>
                )}
                <div className="health-checks">
                  {Object.entries(h.data?.checks ?? {}).map(
                    ([label, value]) => {
                      const ok =
                        typeof value === 'boolean'
                          ? value
                          : (value.ok ?? false);
                      return (
                        <div key={label}>
                          <span
                            className={`health-dot ${ok ? 'green' : 'red'}`}
                          />
                          <span>{label.replaceAll('_', ' ')}</span>
                          <b>{ok ? 'OK' : 'Attention'}</b>
                        </div>
                      );
                    },
                  )}
                  <div>
                    <span className="health-dot green" />
                    <span>Uptime</span>
                    <b>{h.data?.uptime_s ?? 0}s</b>
                  </div>
                </div>
              </>
            )}
          </Panel>
          <Panel
            title="Audit trail"
            sub="Latest 100 records · backend hash-chained log"
          >
            {a.isLoading ? (
              <Skeleton height={130} />
            ) : a.isError ? (
              <ErrorBlock error={a.error} />
            ) : (
              <div className="audit-list">
                {(a.data ?? []).slice(0, 12).map((row, i) => (
                  <div key={i}>
                    <span className="audit-mark" />
                    <span>
                      <b>
                        {row.kind ?? row.event ?? row.action ?? 'Audit event'}
                      </b>
                      <small>
                        {row.ts ?? ''} {row.key_id ? `· ${row.key_id}` : ''}
                      </small>
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Panel>
          <Panel
            title="SeQUeNCe cross-check"
            sub="Optional quantum network simulator integration"
          >
            {!checkStarted ? (
              <button
                className="secondary-button"
                onClick={() => setCheckStarted(true)}
              >
                Check availability <ArrowUpRight size={13} />
              </button>
            ) : cc.isLoading ? (
              <span className="muted-text">Checking…</span>
            ) : cc.isError ? (
              <ErrorBlock error={cc.error} />
            ) : cc.data?.available ? (
              <pre className="json-view">
                {JSON.stringify(cc.data, null, 2)}
              </pre>
            ) : (
              <div className="notice small-notice">
                SeQUeNCe not available. Core simulation remains available.
              </div>
            )}
          </Panel>
          <Panel
            title="Monitoring dashboards"
            sub="Metrics are exposed internally to Prometheus."
          >
            {env.grafanaUrl ? (
              <a
                className="secondary-button"
                href={env.grafanaUrl}
                target="_blank"
                rel="noreferrer"
              >
                Open Grafana <ArrowUpRight size={14} />
              </a>
            ) : (
              <p className="muted-text">
                Set VITE_GRAFANA_URL to link your Grafana instance.
              </p>
            )}
            <div className="notice small-notice">
              Public access to <code>/metrics</code> is blocked by Caddy.
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}

function About() {
  return (
    <>
      <PageHeading
        eyebrow="ABOUT ENTANGLEOPS"
        title="The control plane for a shared fiber network"
        description="See how classical traffic, environmental drift and routing policy shape a simulated quantum network."
      />
      <div className="about-layout">
        <Panel
          title="The network challenge"
          sub="Classical and quantum traffic share the same metro fiber."
        >
          <p className="body-copy">
            EntangleOps models a metro quantum network where classical traffic
            noise can degrade quantum links and aerial fiber responds to
            temperature and wind. The system compares fixed C-band and O-band
            routing with an adaptive policy that uses predictions, band
            selection, admission control and rerouting. The console lets
            operators configure a scenario, simulate a day, replay link
            conditions and compare policies against the same seed. The headline
            metric is SLA-satisfied entanglement throughput: pairs delivered at
            or above the requested fidelity, as reported by the backend. Every
            displayed result comes from a simulated digital twin with
            illustrative physics.
          </p>
          <div className="metric-definition">
            <Zap size={18} />
            <span>
              <b>SLA-satisfied entanglement throughput</b>
              <small>
                Pairs delivered at or above each request's minimum fidelity
                threshold.
              </small>
            </span>
          </div>
        </Panel>
        <Panel
          title="Honest limits"
          sub="What this console does and does not claim."
        >
          <ul className="limit-list">
            <li>
              API keys are bearer secrets held in browser memory; cross-site
              scripting could expose them. Strict CSP, no third-party code and
              no HTML injection are mitigations.
            </li>
            <li>
              Role gating in the UI is a convenience. The backend enforces
              access. Keys are shared secrets, not user accounts; there is no
              SSO or MFA.
            </li>
            <li>
              Everything shown comes from a simulated digital twin with
              illustrative physics. It is not a measurement of real hardware or
              a performance or quantum-security guarantee.
            </li>
            <li>
              Replay buffers run records in browser memory. Closing the tab
              discards them; reopening streams them again. The backend limits
              concurrent streams.
            </li>
            <li>
              Benchmark history is kept per browser tab because the backend has
              no benchmark list endpoint.
            </li>
            <li>
              This frontend has not been penetration-tested or independently
              accessibility-audited.
            </li>
          </ul>
        </Panel>
        <Panel
          title="Architecture"
          sub="The frontend connects each control-plane layer."
        >
          <div className="architecture-row">
            <div>
              <ShieldCheck />
              <b>Security</b>
              <small>API keys · roles · audit chain</small>
            </div>
            <span>→</span>
            <div>
              <Activity />
              <b>Monitoring</b>
              <small>Readiness · health · Prometheus</small>
            </div>
            <span>→</span>
            <div>
              <Network />
              <b>Simulation</b>
              <small>Runs · benchmarks · predictor</small>
            </div>
          </div>
        </Panel>
      </div>
    </>
  );
}
