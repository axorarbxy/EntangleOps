import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Bar, BarChart, CartesianGrid, ComposedChart, ErrorBar, Line, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from 'recharts';
import { mlExperiment, mlExperiments, mlModel } from '../api/endpoints';

const caption = 'Simulated data from an illustrative physics model.';
const record = (value: unknown): Record<string, unknown> => value && typeof value === 'object' ? value as Record<string, unknown> : {};
const label = (value: unknown) => typeof value === 'number' ? value.toFixed(4) : '—';

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
    <div className="page-heading"><div><div className="eyebrow">GOVERNED ML</div><h1>Models</h1><p>Registry, calibration and experiment evidence for the simulated link-fidelity predictor.</p></div></div>
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
