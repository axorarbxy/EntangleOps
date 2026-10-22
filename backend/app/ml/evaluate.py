from __future__ import annotations

import time
import numpy as np
from app.core.physics import BANDS, SWAP_W, link_werner, path_metrics
from app.core.topology import build_graph, candidate_paths
from app.ml.features import build_features
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from app.core.physics import werner_to_fidelity
from app.ml.constants import ALPHAS, IDX


def _metrics(y, pred):
    if len(y) == 0: return {"mae_w": None, "rmse_w": None, "r2_w": None, "bias_w": None, "mae_f": None}
    mae = float(mean_absolute_error(y, pred))
    return {"mae_w": mae, "rmse_w": float(np.sqrt(mean_squared_error(y, pred))),
            "r2_w": float(r2_score(y, pred)) if len(y) > 1 else None,
            "bias_w": float(np.mean(pred-y)), "mae_f": .75*mae}


def evaluate_predictions(X, y, predicted, persistence=None, *, min_slice_rows=200):
    X, y, p = np.asarray(X, dtype=float), np.asarray(y, dtype=float), np.asarray(predicted, dtype=float)
    if X.ndim != 2 or len(X) != len(y) or len(y) != len(p) or not np.isfinite(X).all() or not np.isfinite(y).all() or not np.isfinite(p).all():
        raise ValueError("evaluation data must be finite and aligned")
    overall = _metrics(y, p)
    if persistence is not None:
        base = _metrics(y, np.asarray(persistence, dtype=float))
        overall["skill_vs_persistence"] = (1 - overall["mae_w"] / base["mae_w"]) if base["mae_w"] else 0.0
    masks = {"band_C": X[:, IDX["band_is_o"]] < .5, "band_O": X[:, IDX["band_is_o"]] >= .5,
             "buried": X[:, IDX["aerial_fraction"]] <= 0, "mixed": (X[:, IDX["aerial_fraction"]] > 0) & (X[:, IDX["aerial_fraction"]] < 1),
             "aerial": X[:, IDX["aerial_fraction"]] >= 1, "gusty": X[:, IDX["wind_now"]] >= 10,
             "not_gusty": X[:, IDX["wind_now"]] < 10, "rapid_cooling": X[:, IDX["dtemp_dt_now"]] <= -3,
             "not_rapid_cooling": X[:, IDX["dtemp_dt_now"]] > -3, "peak_load": X[:, IDX["traffic_now"]] >= .7,
             "not_peak_load": X[:, IDX["traffic_now"]] < .7}
    slices = {name: (_metrics(y[mask], p[mask]) if int(mask.sum()) >= min_slice_rows else None) for name, mask in masks.items()}
    return overall, slices


def calibration_report(predictor, X, y):
    result = {}
    for alpha in ALPHAS:
        try: point, lo, hi = predictor.predict_w_interval_full(X, alpha)
        except Exception: continue
        groups = np.where(X[:, IDX["aerial_fraction"]] <= 0, "buried", np.where(X[:, IDX["aerial_fraction"]] >= 1, "aerial", "mixed"))
        result[str(alpha)] = {"nominal": 1-alpha, "empirical": float(np.mean((y>=lo)&(y<=hi))),
                              "mean_width_w": float(np.mean(hi-lo)),
                              "by_group": {g: (float(np.mean((y[groups==g]>=lo[groups==g]) & (y[groups==g]<=hi[groups==g]))) if np.any(groups==g) else None) for g in ("buried","mixed","aerial")}}
    return result


def reliability_report(y, predicted, n_bins=10):
    y, predicted = np.asarray(y, dtype=float), np.asarray(predicted, dtype=float)
    edges = np.linspace(0, .97, n_bins + 1)
    bins = np.clip(np.digitize(predicted, edges[1:-1], right=False), 0, n_bins - 1)
    return [{"bin": i, "n": int(np.sum(bins == i)),
             "mean_predicted_w": float(np.mean(predicted[bins == i])) if np.any(bins == i) else None,
             "mean_true_w": float(np.mean(y[bins == i])) if np.any(bins == i) else None}
            for i in range(n_bins)]


def latency_report(predictor, batch_sizes=(1,24,1000), repeats=200):
    result = {}
    width = len(predictor.feature_min)
    for size in batch_sizes:
        X = np.zeros((size, width), dtype=np.float64)
        predictor.predict_w(X)
        samples=[]
        for _ in range(repeats):
            started=time.perf_counter();predictor.predict_w(X);samples.append((time.perf_counter()-started)*1000)
        item={"p50":float(np.percentile(samples,50)),"p95":float(np.percentile(samples,95))}
        if getattr(predictor,"calibration",None):
            interval=[]
            for _ in range(repeats):
                started=time.perf_counter();predictor.predict_w_interval_full(X,.1);interval.append((time.perf_counter()-started)*1000)
            item["interval"]={"p50":float(np.percentile(interval,50)),"p95":float(np.percentile(interval,95))}
        result[str(size)]=item
    return result


def evaluate_dataset(predictor, dataset):
    pred=predictor.predict_w(dataset.X)
    from app.ml.features import physics_w_np
    overall,slices=evaluate_predictions(dataset.X,dataset.y,pred,physics_w_np(dataset.X))
    persist=physics_w_np(dataset.X)
    baselines={"physics_persistence":_metrics(dataset.y,persist),
               "constant_mean":_metrics(dataset.y,np.full(len(dataset.y),getattr(predictor,"mean_target",float(np.mean(dataset.y)))))}
    from app.core.topology import get_preset
    nodes,links=get_preset(dataset.meta.get("preset","metro"))
    decision_seed=42 if dataset.meta.get("suite") == "eval_v1" else 47 if dataset.meta.get("suite") == "ood_v1" else 0
    decisions=decision_metrics(predictor,dataset.envs,nodes,links,horizon_steps=predictor.horizon_steps,n_requests_per_scenario=200,seed=decision_seed)
    from app.ml.explain import permutation_importance, partial_dependence
    return {"suite":{"name":dataset.meta.get("suite","dataset"),"sha256":dataset.meta["sha256"],
                      "n_scenarios":dataset.meta["n_scenarios"],"n_rows":len(dataset.y),
                      "horizon_steps":dataset.meta["horizon_steps"]},
            "overall":overall,"baselines":baselines,"slices":slices,"decision":decisions,
            "calibration":calibration_report(predictor,dataset.X,dataset.y),
            "latency_ms":latency_report(predictor),
            "reliability":reliability_report(dataset.y,pred),
            "importance":permutation_importance(predictor,dataset.X,dataset.y,n_repeats=5,seed=0),
            "partial_dependence":partial_dependence(predictor,dataset.X)}


def decision_metrics(model, env_list, nodes, links, *, horizon_steps=5, n_requests_per_scenario=200, seed=0):
    lookup={link.link_id:link for link in links};graph=build_graph(list(links));rng=np.random.default_rng(seed)
    accum={}
    for threshold in (.80,.85,.88):
        accum[str(threshold)]={name:{"pred":[],"truth":[]} for name in ("point_m0.00","point_m0.01",*[f"risk_{a}" for a in ALPHAS])}
    for env in env_list:
        node_ids=list(nodes)
        for _ in range(n_requests_per_scenario):
            t=int(rng.integers(0,max(1,env.n_steps-horizon_steps)));src,dst=rng.choice(node_ids,size=2,replace=False)
            paths=candidate_paths(graph,src,dst,1)
            if not paths:continue
            path=paths[0];ids=[graph[path[i]][path[i+1]]["link_id"] for i in range(len(path)-1)]
            rows=np.asarray([build_features(env,lookup[lid],band,t,schema=model.feature_schema) for lid in ids for band in BANDS])
            point=model.predict_w(rows).reshape(len(ids),len(BANDS));bands=[];chosen=[]
            for i in range(len(ids)):
                j=int(np.argmax(point[i]));bands.append(BANDS[j]);chosen.append(float(point[i,j]))
            predicted=werner_to_fidelity(float(np.prod(chosen))*SWAP_W**(len(ids)-1))
            truth=path_metrics([(lookup[lid],band,env.conditions(lid,min(env.n_steps-1,t+horizon_steps))) for lid,band in zip(ids,bands)])[0]
            risk_pred={}
            if getattr(model,"calibration",None):
                for alpha in ALPHAS:
                    _,lower=model.predict_w_interval(rows,alpha);lower=lower.reshape(len(ids),len(BANDS));vals=[float(lower[i,BANDS.index(bands[i])]) for i in range(len(ids))]
                    risk_pred[f"risk_{alpha}"]=werner_to_fidelity(float(np.prod(vals))*SWAP_W**(len(ids)-1))
            for threshold in (.80,.85,.88):
                for name,estimate,margin in [("point_m0.00",predicted,0.0),("point_m0.01",predicted,.01),*((key,val,0.0) for key,val in risk_pred.items())]:
                    accum[str(threshold)][name]["pred"].append(estimate>=threshold+margin)
                    accum[str(threshold)][name]["truth"].append(truth>=threshold)
                    accum[str(threshold)][name].setdefault("absolute_error",[]).append(abs(estimate-truth))
    report={}
    for threshold,rules in accum.items():
        report[threshold]={}
        for name,item in rules.items():
            pred=np.asarray(item["pred"],dtype=bool);truth=np.asarray(item["truth"],dtype=bool)
            admitted=int(pred.sum());true_feasible=int(truth.sum())
            report[threshold][name]={"n_pred_feasible":admitted,
                "false_feasible_rate":float(np.sum(pred&~truth)/admitted) if admitted else None,
                "false_reject_rate":float(np.sum(~pred&truth)/true_feasible) if true_feasible else None,
                "path_mae_f":float(np.mean(item["absolute_error"])) if item.get("absolute_error") else None}
    return report
