import { useState } from 'react';
import { Activity, ArrowRight, Clock3, Sparkles } from 'lucide-react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Bar, BarChart, CartesianGrid, ComposedChart, ErrorBar, Line, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from 'recharts';
import { estimatePtpDelay, mlExperiment, mlExperiments, mlModel, type PtpDelayRequest } from '../api/endpoints';

const caption = 'Simulated data from an illustrative physics model.';
const record = (value: unknown): Record<string, unknown> => value && typeof value === 'object' ? value as Record<string, unknown> : {};
const label = (value: unknown) => typeof value === 'number' ? value.toFixed(4) : '—';

function PtpDelayPlanner() {
  const [settings, setSettings] = useState<PtpDelayRequest>({
    progress: 0.5,
    mode: 'M2',
    load_low_pct: 20,
    load_high_pct: 60,
    duration_minutes: 30,
    traffic_model: 'IMIX',
    message_type: 'sync',
    recent_same_message_delays_us: [],
  });
  const [historyText, setHistoryText] = useState('');
  const [delayBudget, setDelayBudget] = useState(10);
  const estimate = useMutation({ mutationFn: estimatePtpDelay });
  const update = <K extends keyof PtpDelayRequest>(key: K, value: PtpDelayRequest[K]) =>
    setSettings((current) => ({ ...current, [key]: value }));
  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const history = historyText.trim()
      ? historyText.split(',').map((value) => Number(value.trim()))
      : [];
    if (history.length > 5 || history.some((value) => !Number.isFinite(value) || value <= 0)) {
      estimate.reset();
      return;
    }
    estimate.mutate({ ...settings, recent_same_message_delays_us: history });
  };
  const result = estimate.data;
  return <section className="panel ptp-planner">
    <div className="ptp-hero">
      <div className="ptp-hero-copy">
        <div className="ptp-kicker"><Sparkles size={14}/> FIELD TIMING WORKBENCH</div>
        <h2>Plan a PTP timing run</h2>
        <p>Explore how traffic mix and load may affect one-way timing delay before you configure a run. Add recent readings to ground the estimate in your current session.</p>
        <div className="ptp-context"><Activity size={16}/><span><b>Measured against SLATE-PTP runs</b><small>Research dataset · held-out runs · no live network connection</small></span></div>
      </div>
      <div className="ptp-hero-stat"><span>VALIDATION MAE</span><b>0.88 <small>µs</small></b><small>48,000 measurements · 12 held-out runs</small></div>
    </div>
    <form onSubmit={submit}>
      <div className="ptp-form-grid">
        <label className="form-field">Experiment mode<select value={settings.mode} onChange={(e) => update('mode', e.target.value as PtpDelayRequest['mode'])}><option value="M1">M1</option><option value="M2">M2</option><option value="M3">M3</option></select></label>
        <label className="form-field">Traffic mix<select value={settings.traffic_model} onChange={(e) => update('traffic_model', e.target.value as PtpDelayRequest['traffic_model'])}><option value="IMIX">IMIX · mixed packet sizes</option><option value="LP">LP · large packets</option><option value="MTU">MTU · maximum frames</option><option value="SP">SP · small packets</option><option value="NO">NO · no background traffic</option></select></label>
        <label className="form-field">PTP message<select value={settings.message_type} onChange={(e) => update('message_type', e.target.value as PtpDelayRequest['message_type'])}><option value="sync">Sync · t2 − t1</option><option value="delay_req">Delay request · t4 − t3</option></select></label>
        <label className="form-field">Run duration <small>1–900 minutes</small><input type="number" min="1" max="900" value={settings.duration_minutes} onChange={(e) => update('duration_minutes', Number(e.target.value))}/></label>
        <label className="form-field">Traffic load range <small>Low and high percent</small><div className="ptp-dual-input"><input aria-label="Low traffic load percent" type="number" min="0" max="100" value={settings.load_low_pct} onChange={(e) => update('load_low_pct', Number(e.target.value))}/><span>to</span><input aria-label="High traffic load percent" type="number" min="0" max="100" value={settings.load_high_pct} onChange={(e) => update('load_high_pct', Number(e.target.value))}/></div></label>
        <label className="form-field">Run progress <small>Where should the estimate land?</small><div className="ptp-progress"><input type="range" min="0" max="100" value={settings.progress * 100} onChange={(e) => update('progress', Number(e.target.value) / 100)}/><b>{Math.round(settings.progress * 100)}%</b></div></label>
        <label className="form-field">Your one-way delay budget <small>Planning target in microseconds</small><input type="number" min="0.01" max="1000" step="0.1" required value={delayBudget} onChange={(e) => setDelayBudget(Number(e.target.value))}/></label>
        <label className="form-field span-2">Recent {settings.message_type === 'sync' ? 'Sync' : 'Delay request'} delays in µs <small>Optional · up to five, comma separated, oldest first</small><input placeholder="e.g. 7.8, 8.1, 7.9" value={historyText} onChange={(e) => setHistoryText(e.target.value)}/></label>
      </div>
      {settings.load_low_pct > settings.load_high_pct && <p className="ptp-error" role="alert">Low load must be less than or equal to high load.</p>}
      {historyText && (historyText.split(',').length > 5 || historyText.split(',').some((v) => !Number.isFinite(Number(v.trim())) || Number(v.trim()) <= 0)) && <p className="ptp-error" role="alert">Enter up to five positive delay values, separated by commas.</p>}
      {estimate.isError && <p className="ptp-error" role="alert">Could not estimate this scenario. {estimate.error instanceof Error ? estimate.error.message : 'Check your connection and try again.'}</p>}
      <div className="ptp-submit-row"><span><Clock3 size={14}/> Estimate from the trained model; usually returns instantly.</span><button className="primary-button" disabled={estimate.isPending || !Number.isFinite(delayBudget) || delayBudget < 0.01 || delayBudget > 1000 || settings.load_low_pct > settings.load_high_pct || (historyText !== '' && (historyText.split(',').length > 5 || historyText.split(',').some((v) => !Number.isFinite(Number(v.trim())) || Number(v.trim()) <= 0)))}>{estimate.isPending ? 'Estimating…' : 'Estimate one-way delay'} <ArrowRight size={15}/></button></div>
    </form>
    {result && <div className="ptp-result" aria-live="polite">
      <div className="ptp-result-heading"><span>SCENARIO ESTIMATE</span><small>{result.history_count ? `Personalized with ${result.history_count} recent readings` : 'Scenario-only estimate'}</small></div>
      <div className="ptp-result-body"><div className="ptp-result-value">{result.predicted_delay_us.toFixed(2)} <small>µs</small><span>predicted one-way delay</span><b className={`ptp-budget-check ${result.predicted_delay_us <= delayBudget ? 'within' : 'over'}`}>{result.predicted_delay_us <= delayBudget ? 'Within' : 'Over'} your {delayBudget.toFixed(1)} µs planning budget</b></div><div className="ptp-result-detail"><b>How to read this</b><p>The model estimates {settings.message_type === 'sync' ? 'Sync path delay (t2 − t1)' : 'Delay request path delay (t4 − t3)'} for the selected traffic profile. Its typical absolute error on held-out runs was {result.validation_mae_us.toFixed(2)} µs; that is a dataset-level score, not a per-prediction confidence interval.</p><small>Validation MAE · {result.validation_scope}</small></div></div>
    </div>}
    <p className="ptp-footnote">Use this for scenario exploration and experiment planning. The model learned from recorded SLATE-PTP conditions; performance outside those configurations is unknown, and this estimate is not a live measurement or clock-accuracy guarantee.</p>
  </section>;
}

export function ModelsPage() {
  const model = useQuery({ queryKey: ['ml-model'], queryFn: mlModel, retry: false });
  const experiments = useQuery({ queryKey: ['ml-experiments'], queryFn: () => mlExperiments(undefined, 100), retry: false });
  const [selected, setSelected] = useState('');
  const chosen = selected || experiments.data?.[0]?.id || '';
  const detail = useQuery({ queryKey: ['ml-experiment', chosen], queryFn: () => mlExperiment(chosen), enabled: Boolean(chosen), retry: false });
  const evaluations = useQuery({ queryKey: ['ml-evaluations'], queryFn: () => mlExperiments('evaluation', 100), retry: false });
  const latestEvaluation = evaluations.data?.find((x) => x.name.startsWith('evaluation '))?.id ?? '';
  const evaluationDetail = useQuery({ queryKey: ['ml-experiment', latestEvaluation], queryFn: () => mlExperiment(latestEvaluation), enabled: Boolean(latestEvaluation), retry: false });
  const latestStudy = experiments.data?.find((x) => x.kind === 'policy_study')?.id ?? '';
  const studyDetail = useQuery({ queryKey: ['ml-experiment', latestStudy], queryFn: () => mlExperiment(latestStudy), enabled: Boolean(latestStudy), retry: false });
  if (model.isLoading || experiments.isLoading) return <section className="panel"><div className="panel-heading"><h2>Models</h2><p>Loading registered model and experiment evidence…</p></div><div className="ml-empty" role="status">Loading ML registry</div></section>;
  if (model.isError || experiments.isError) return <section className="panel"><div className="panel-heading"><h2>Models</h2><p>ML registry is unavailable</p></div><div className="ml-empty" role="alert">Could not load model information. Check backend connectivity and your API key.</div></section>;
  const active = model.data;
  const evaluationMetrics = record(evaluationDetail.data?.metrics);
  const reports = record(evaluationMetrics.reports);
  const evaluation = record(reports.eval_v1);
  const ood = record(reports.ood_v1);
  const coverage = record(evaluation.calibration);
  const oodCoverage = record(ood.calibration);
  const coverageRows = Object.entries(coverage).map(([alpha, value]) => ({ alpha: `${(1 - Number(alpha)) * 100}%`, nominal: Number(record(value).nominal), id: Number(record(value).empirical), ood: Number(record(oodCoverage[alpha]).empirical) })).filter((row) => Number.isFinite(row.ood));
  const decision = record(evaluation.decision);
  const studyMetrics = record(studyDetail.data?.metrics);
  const studyRecord = record(studyMetrics);
  const paretoSet = new Set(Array.isArray(studyRecord.pareto) ? studyRecord.pareto.filter((x): x is string => typeof x === 'string') : []);
  const alphaStar = typeof studyRecord.alpha_star === 'number' ? `adaptive_risk_${studyRecord.alpha_star}` : '';
  const studyPoints = Object.entries(record(studyRecord.reports)).map(([policy, row]) => {
    const entry = record(row);
    const slaMetric = record(entry.sla_satisfied_pairs); const violationMetric = record(entry.violation_fraction);
    const sla = Number(slaMetric.mean); const violation = Number(violationMetric.mean);
    return { policy, violation, sla, slaMin: Number(slaMetric.min), slaMax: Number(slaMetric.max), violationMin: Number(violationMetric.min), violationMax: Number(violationMetric.max), slaError: [sla - Number(slaMetric.min), Number(slaMetric.max) - sla], violationError: [violation - Number(violationMetric.min), Number(violationMetric.max) - violation], pareto: paretoSet.has(policy), alphaStar: policy === alphaStar };
  }).filter((point) => Number.isFinite(point.violation) && Number.isFinite(point.sla));
  const baselineRows = [{ name: 'Predictor', metrics: record(evaluation.overall) }, ...Object.entries(record(evaluation.baselines)).map(([name, value]) => ({ name, metrics: record(value) }))];
  const latencyRows = Object.entries(record(evaluation.latency_ms)).map(([batch, value]) => ({ batch, point: record(value), interval: record(record(value).interval) }));
  const importanceRows = Object.entries(record(record(evaluation.importance).individual)).map(([feature, value]) => ({ feature, importance: Number(record(value).mean) })).sort((a, b) => b.importance - a.importance);
  return <>
    <div className="page-heading"><div><div className="eyebrow">GOVERNED ML</div><h1>Models</h1><p>Explore the trained PTP timing model and review the network fidelity model’s evidence.</p></div></div>
    <PtpDelayPlanner />
    {!active ? <section className="panel"><div className="panel-heading"><h2>No registered model</h2><p>Train a candidate with the ML CLI to populate the registry.</p></div><div className="ml-empty">The API has not registered an active model yet.</div></section> : <>
      <section className="panel ml-model-card">
        <div className="panel-heading"><div><h2>Active model <span className="ml-champion">CHAMPION</span></h2><p>Integrity digest <code>{active.sha256.slice(0, 12)}</code> · trained {new Date(active.trained_at).toLocaleString()}</p></div></div>
        <div className="ml-facts"><div><small>PROFILE</small><b>{active.profile}</b></div><div><small>FEATURES</small><b>{active.feature_schema.toUpperCase()} · {active.target_mode}</b></div><div><small>HORIZON</small><b>{active.horizon_steps} steps</b></div><div><small>SCIKIT-LEARN</small><b>{active.sklearn_version ?? '—'}</b></div><div><small>TEST R²</small><b>{label(active.metrics.r2_test)}</b></div><div><small>TEST MAE</small><b>{label(active.metrics.mae_test)}</b></div><div><small>CALIBRATION</small><b>{active.calibration ? 'Calibrated on simulated data' : 'Uncalibrated'}</b></div></div>
        <p className="derived-note">{caption} Prediction intervals are calibrated on simulated data and are not guarantees.</p>
      </section>
      <section className="ml-chart-grid">
        <div className="panel"><div className="panel-heading"><h2>Interval calibration</h2><p>Nominal and empirical coverage by α · eval suite</p></div>
          {coverageRows.length ? <><div className="ml-chart"><ResponsiveContainer width="100%" height="100%"><ComposedChart data={coverageRows}><CartesianGrid strokeDasharray="3 3" stroke="var(--border)"/><XAxis dataKey="alpha"/><YAxis domain={[0,1]}/><Tooltip/><Line dataKey="nominal" stroke="#94a3b8" name="Nominal"/><Line dataKey="id" stroke="#2dd4bf" name="ID empirical"/><Line dataKey="ood" stroke="#c084fc" name="OOD empirical"/></ComposedChart></ResponsiveContainer></div><table className="ml-data-table"><caption>{caption}</caption><thead><tr><th>Nominal</th><th>ID empirical</th><th>OOD empirical</th></tr></thead><tbody>{coverageRows.map((r) => <tr key={r.alpha}><td>{r.alpha}</td><td>{label(r.id)}</td><td>{label(r.ood)}</td></tr>)}</tbody></table></> : <div className="ml-empty">Stored ID and OOD evaluation evidence is not available yet.</div>}
        </div>
        <div className="panel"><div className="panel-heading"><h2>Decision outcomes</h2><p>Admission error rates by SLA and routing rule</p></div>
          {Object.keys(decision).length ? <div className="table-scroll"><table className="ml-data-table"><caption>{caption}</caption><thead><tr><th>SLA</th><th>Rule</th><th>False feasible</th><th>False reject</th><th>Path MAE (F)</th></tr></thead><tbody>{Object.entries(decision).flatMap(([sla, rules]) => Object.entries(record(rules)).map(([rule, value]) => <tr key={`${sla}-${rule}`}><td>{sla}</td><td>{rule}</td><td>{label(record(value).false_feasible_rate)}</td><td>{label(record(value).false_reject_rate)}</td><td>{label(record(value).path_mae_f)}</td></tr>))}</tbody></table></div> : <div className="ml-empty">Run <code>ml_eval.py --store</code> to record held-out decision results.</div>}
        </div>
        <div className="panel"><div className="panel-heading"><h2>Held-out error vs baselines</h2><p>Werner MAE · slices with fewer than 200 rows are omitted</p></div>
          {baselineRows.length > 1 ? <div className="table-scroll"><table className="ml-data-table"><caption>{caption}</caption><thead><tr><th>Model / baseline</th><th>MAE W</th><th>RMSE W</th><th>R²</th><th>Skill vs physics</th></tr></thead><tbody>{baselineRows.map((row) => <tr key={row.name}><td>{row.name}</td><td>{label(row.metrics.mae_w)}</td><td>{label(row.metrics.rmse_w)}</td><td>{label(row.metrics.r2_w)}</td><td>{label(row.metrics.skill_vs_persistence)}</td></tr>)}</tbody></table></div> : <div className="ml-empty">Evaluation metrics are not recorded yet.</div>}
        </div>
        <div className="panel"><div className="panel-heading"><h2>Prediction latency</h2><p>Point and calibrated interval inference · milliseconds p50 / p95</p></div>
          {latencyRows.length ? <table className="ml-data-table"><thead><tr><th>Batch</th><th>Point p50</th><th>Point p95</th><th>Interval p50</th><th>Interval p95</th></tr></thead><tbody>{latencyRows.map((row) => <tr key={row.batch}><td>{row.batch}</td><td>{label(row.point.p50)}</td><td>{label(row.point.p95)}</td><td>{label(row.interval.p50)}</td><td>{label(row.interval.p95)}</td></tr>)}</tbody></table> : <div className="ml-empty">Latency results are not recorded yet.</div>}
        </div>
        <div className="panel"><div className="panel-heading"><h2>Feature importance</h2><p>Permutation MAE increase · descriptive, not causal</p></div>
          {importanceRows.length ? <><div className="ml-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={importanceRows} layout="vertical" margin={{ left: 12, right: 16 }}><CartesianGrid strokeDasharray="3 3" stroke="var(--border)"/><XAxis type="number"/><YAxis type="category" dataKey="feature" width={140}/><Tooltip/><Bar dataKey="importance" fill="#38bdf8"/></BarChart></ResponsiveContainer></div><table className="ml-data-table"><caption>{caption}</caption><thead><tr><th>Feature</th><th>MAE increase</th></tr></thead><tbody>{importanceRows.map((row) => <tr key={row.feature}><td>{row.feature}</td><td>{label(row.importance)}</td></tr>)}</tbody></table></> : <div className="ml-empty">Run <code>ml_eval.py --store</code> to measure feature importance.</div>}
        </div>
        <div className="panel"><div className="panel-heading"><h2>Policy study Pareto view</h2><p>Lower violation rate and higher SLA throughput</p></div>
          {studyPoints.length ? <><div className="ml-chart"><ResponsiveContainer width="100%" height="100%"><ComposedChart><CartesianGrid strokeDasharray="3 3" stroke="var(--border)"/><XAxis type="number" dataKey="violation" name="Violation fraction"/><YAxis type="number" dataKey="sla" name="SLA pairs"/><Tooltip cursor={{ strokeDasharray: '3 3' }}/><Scatter data={studyPoints.filter((p) => !p.pareto && !p.alphaStar)} fill="#64748b" name="Other"/><Scatter data={studyPoints.filter((p) => p.pareto)} fill="#c084fc" name="Pareto"><ErrorBar dataKey="slaError" direction="y" width={4} strokeWidth={1}/><ErrorBar dataKey="violationError" direction="x" width={4} strokeWidth={1}/></Scatter><Scatter data={studyPoints.filter((p) => p.alphaStar)} fill="#facc15" name="Selected α*"/></ComposedChart></ResponsiveContainer></div><table className="ml-data-table"><caption>{caption}</caption><thead><tr><th>Policy / α</th><th>Violation mean (min–max)</th><th>SLA pairs mean (min–max)</th><th>Selection / Pareto</th></tr></thead><tbody>{studyPoints.map((p) => <tr key={p.policy}><td>{p.policy}</td><td>{label(p.violation)} ({label(p.violationMin)}–{label(p.violationMax)})</td><td>{label(p.sla)} ({label(p.slaMin)}–{label(p.slaMax)})</td><td>{p.alphaStar ? 'α*' : p.pareto ? 'Pareto' : '—'}</td></tr>)}</tbody></table></> : <div className="ml-empty">No policy-study experiment is available. Run <code>ml_policy_study.py</code> to compare risk policies.</div>}
        </div>
      </section>
    </>}
    <section className="panel"><div className="panel-heading"><h2>Experiments</h2><p>Append-only records of training, evaluation, tuning and policy studies.</p></div>
      {!experiments.data?.length ? <div className="ml-empty">No ML experiments stored yet.</div> : <div className="table-scroll"><table className="ml-data-table"><thead><tr><th>Name</th><th>Kind</th><th>Profile</th><th>Model</th><th>Created</th><th>Detail</th></tr></thead><tbody>{experiments.data.map((row) => <tr key={row.id}><td>{row.name}</td><td>{row.kind}</td><td>{row.profile ?? '—'}</td><td>{row.model_id ?? '—'}</td><td>{new Date(row.created_at).toLocaleString()}</td><td><button className="text-link" onClick={() => setSelected(row.id)}>Inspect</button></td></tr>)}</tbody></table></div>}
    </section>
    {chosen && <section className="panel"><div className="panel-heading"><h2>Experiment detail</h2><p>{chosen}</p></div>{detail.isLoading ? <div className="ml-empty">Loading experiment…</div> : detail.isError ? <div className="ml-empty" role="alert">Could not load selected experiment.</div> : <pre className="json-view">{JSON.stringify(detail.data, null, 2)}</pre>}</section>}
  </>;
}
