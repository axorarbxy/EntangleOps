from __future__ import annotations
import argparse,hashlib,sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import ScenarioConfig,settings
from app.core.environment import generate_env
from app.core.policies import make_policy
from app.core.requests_gen import generate_requests
from app.core.simulator import run_simulation
from app.core.metrics import compute_summary
from app.core.topology import get_preset,link_lookup
from app.db.repos.ml_experiments import ExperimentRepo
from app.ml.constants import ALPHAS
from app.ml.serving import RowCachePredictor
from app.db.repos.model_registry import ModelRegistry
from app.core.predictor import FidelityPredictor
from scripts._ml_cli import candidate_path,dump_report,open_ml_db,require_signing_key

def run_seed(seed,model,duration,alphas=ALPHAS):
 nodes,links=get_preset('metro');lookup=link_lookup(links);scenario=ScenarioConfig();env=generate_env(list(lookup),duration,60,seed,scenario);reqs=generate_requests(nodes,env.n_steps,60,seed,scenario);out={}
 names=['static_c','static_o','adaptive']+[f'adaptive_risk_{a}' for a in alphas]
 for name in names:
  alpha=float(name.rsplit('_',1)[-1]) if name.startswith('adaptive_risk') else None
  policy=make_policy('adaptive_risk',alpha) if alpha is not None else make_policy(name)
  predictor=RowCachePredictor(model,settings.ml_prediction_cache_rows) if name in {'adaptive'} or name.startswith('adaptive_risk') else model
  records,summary=run_simulation(policy,env,reqs,lookup,predictor,settings.forecast_horizon_steps,settings.k_paths,0.0 if name.startswith('adaptive_risk') else settings.safety_margin)
  summary['policy']=policy.name
  out[name]=summary
 return out

def _run_seed_arg(args):
 seed,model_path,duration,alphas=args
 from app.core.predictor import FidelityPredictor
 return seed,run_seed(seed,FidelityPredictor.load(model_path),duration,alphas)

def _parse_seed_range(value):
 try:
  parts=value.split('-')
  if len(parts)!=2:raise ValueError
  start,end=(int(part) for part in parts)
 except ValueError as exc:
  raise SystemExit('seed ranges must use START-END, for example 100-104') from exc
 if start<0 or end<start or end-start>1000:
  raise SystemExit('seed range must be non-negative, ascending, and at most 1001 seeds')
 return list(range(start,end+1))

def main():
 p=argparse.ArgumentParser();p.add_argument('--model-id',type=int);p.add_argument('--alphas',default='0.05,0.1,0.2');p.add_argument('--select-seeds',default='100-104');p.add_argument('--report-seeds',default='42-46');p.add_argument('--quick',action='store_true');p.add_argument('--workers',type=int,default=4);p.add_argument('--gate-check',action='store_true');a=p.parse_args();require_signing_key()
 try:alphas=tuple(float(value) for value in a.alphas.split(','))
 except ValueError:raise SystemExit('--alphas must be a comma-separated list from 0.05,0.1,0.2')
 if not alphas or len(set(alphas))!=len(alphas) or any(alpha not in ALPHAS for alpha in alphas):raise SystemExit('--alphas must be a non-empty subset of 0.05,0.1,0.2')
 engine,sf=open_ml_db();registry=ModelRegistry(sf)
 try:
  model_id=a.model_id or registry.active_id()
  row=registry.get(model_id) if model_id else None
  if not row:raise SystemExit('model not found')
  model=FidelityPredictor.load(candidate_path(row['sha256']))
 finally:engine.dispose()
 if not model.calibration:raise SystemExit('policy study requires a calibrated model')
 if a.quick:select_seeds=report_seeds=[42,43];duration=6.0
 else:
  select_seeds,report_seeds=_parse_seed_range(a.select_seeds),_parse_seed_range(a.report_seeds);duration=24.0
 workers=max(1,min(a.workers,8))
 if workers>1:
  with ProcessPoolExecutor(max_workers=workers) as pool:
   selected=dict(pool.map(_run_seed_arg,[(seed,str(candidate_path(row['sha256'])),duration,alphas) for seed in select_seeds]))
 else:selected={seed:run_seed(seed,model,duration,alphas) for seed in select_seeds}
 adaptive_v=np.mean([v['adaptive']['violation_fraction'] for v in selected.values()]);choice=None;best=-1.0
 for alpha in alphas:
  key=f'adaptive_risk_{alpha}';violation=np.mean([v[key]['violation_fraction'] for v in selected.values()]);sla=np.mean([v[key]['sla_satisfied_pairs'] for v in selected.values()])
  if violation<=adaptive_v and sla>best:choice,best=alpha,sla
 if workers>1:
  with ProcessPoolExecutor(max_workers=workers) as pool:
   reports=dict(pool.map(_run_seed_arg,[(seed,str(candidate_path(row['sha256'])),duration,alphas) for seed in report_seeds]))
 else:reports={seed:run_seed(seed,model,duration,alphas) for seed in report_seeds}
 gate_ready=(not a.quick and select_seeds==[100,101,102,103,104] and report_seeds==[42,43,44,45,46])
 champion_id=registry.active_id() if a.gate_check and gate_ready else None
 champion_row=registry.get(champion_id) if champion_id else None
 if a.gate_check and champion_row and champion_id!=model_id:
  champion_model=FidelityPredictor.load(candidate_path(champion_row['sha256']))
  if workers>1:
   with ProcessPoolExecutor(max_workers=workers) as pool:
    champion_reports=dict(pool.map(_run_seed_arg,[(seed,str(candidate_path(champion_row['sha256'])),duration,alphas) for seed in report_seeds]))
  else:champion_reports={seed:run_seed(seed,champion_model,duration,alphas) for seed in report_seeds}
 else:champion_reports=reports
 entries={}
 for policy in ['static_c','static_o','adaptive']+[f'adaptive_risk_{x}' for x in alphas]:
  entries[policy]={}
  for metric in ('sla_satisfied_pairs','violation_fraction','block_rate','sla_efficiency','reroutes'):
   vals=[float(v[policy][metric]) for v in reports.values()];entries[policy][metric]={'mean':float(np.mean(vals)),'min':float(np.min(vals)),'max':float(np.max(vals))}
   if policy!='adaptive':entries[policy][metric]['paired_diff_vs_adaptive']=[float(v[policy][metric]-v['adaptive'][metric]) for v in reports.values()]
 result={'alpha_star':choice,'selection_seeds':select_seeds,'report_seeds':report_seeds,'reports':entries,'pareto':[], 'note':'Descriptive results only; no significance tests are computed.'}
 for name,metrics in entries.items():
  point=(metrics['violation_fraction']['mean'],metrics['sla_satisfied_pairs']['mean'])
  dominated=any(other['violation_fraction']['mean']<=point[0] and other['sla_satisfied_pairs']['mean']>=point[1] and (other['violation_fraction']['mean']<point[0] or other['sla_satisfied_pairs']['mean']>point[1]) for other in entries.values())
  if not dominated:result['pareto'].append(name)
 if a.gate_check:
  candidate_sla=float(np.mean([v['adaptive']['sla_satisfied_pairs'] for v in reports.values()]))
  candidate_violation=float(np.mean([v['adaptive']['violation_fraction'] for v in reports.values()]))
  champion_sla=float(np.mean([v['adaptive']['sla_satisfied_pairs'] for v in champion_reports.values()]))
  champion_violation=float(np.mean([v['adaptive']['violation_fraction'] for v in champion_reports.values()]))
  g7=(gate_ready
      and candidate_sla>=.99*champion_sla and candidate_violation<=champion_violation+.005)
  result['champion_comparison']={'model_id':champion_id,'candidate_adaptive':{'sla_satisfied_pairs':candidate_sla,'violation_fraction':candidate_violation},'champion_adaptive':{'sla_satisfied_pairs':champion_sla,'violation_fraction':champion_violation}}
  result['gates']={'G7':g7,'failures':[] if g7 else ['candidate adaptive policy missed champion throughput or violation bound']}
 engine,sf=open_ml_db()
 try:result['experiment_id']=ExperimentRepo(sf).record('policy_study','adaptive risk policy study',{'model_id':model_id,'select_seeds':select_seeds,'report_seeds':report_seeds,'duration_hours':duration,'quick':a.quick,'alphas':alphas},result,profile=row['profile'],model_id=model_id)
 finally:engine.dispose()
 dump_report(result)
if __name__=='__main__':main()
