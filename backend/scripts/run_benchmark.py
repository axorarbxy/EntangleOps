from __future__ import annotations
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import settings,ScenarioConfig
from app.core.environment import generate_env
from app.core.policies import AdaptivePolicy,StaticCPolicy,StaticOPolicy
from app.core.predictor import FidelityPredictor
from app.core.requests_gen import generate_requests
from app.core.simulator import run_simulation
from app.core.topology import get_preset,link_lookup

def main()->None:
    predictor=FidelityPredictor.load_or_train(settings.model_path,settings.forecast_horizon_steps,settings.default_seed);all_results={}
    for seed in [42,43,44,45,46]:
        nodes,links=get_preset("metro");lookup=link_lookup(links);sc=ScenarioConfig();env=generate_env(list(lookup),24,60,seed,sc);reqs=generate_requests(nodes,env.n_steps,60,seed,sc);all_results[str(seed)]={}
        for p in [StaticCPolicy(),StaticOPolicy(),AdaptivePolicy()]:
            _,summary=run_simulation(p,env,reqs,lookup,predictor,settings.forecast_horizon_steps,settings.k_paths,settings.safety_margin);all_results[str(seed)][p.name]=summary
    Path("data").mkdir(exist_ok=True);Path("data/benchmark_report.json").write_text(json.dumps(all_results,indent=2))
    keys=("sla_satisfied_pairs","violation_fraction","block_rate","reroutes")
    means={name:{key:sum(all_results[str(seed)][name][key] for seed in [42,43,44,45,46])/5 for key in keys} for name in ("static_c","static_o","adaptive")}
    print("policy       sla_satisfied_pairs  violation_fraction  block_rate  reroutes")
    for name,row in means.items():print(f"{name:12s} {row['sla_satisfied_pairs']:19.2f} {row['violation_fraction']:19.4f} {row['block_rate']:11.4f} {row['reroutes']:9.2f}")
    for baseline in ("static_c","static_o"):
        base=means[baseline]["sla_satisfied_pairs"];print(f"adaptive improvement over {baseline}: {(means['adaptive']['sla_satisfied_pairs']-base)/max(base,1e-9)*100:.2f}%")
if __name__=="__main__":main()
