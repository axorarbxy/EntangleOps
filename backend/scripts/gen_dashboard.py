from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "monitoring" / "grafana" / "dashboards" / "entangleops.json"

QUERIES = [
    ("HTTP request rate", 'sum(rate(eo_http_requests_total[5m]))', "reqps"),
    ("HTTP p95 latency", 'histogram_quantile(0.95, sum by (le) (rate(eo_http_request_duration_seconds_bucket[5m])))', "s"),
    ("HTTP 5xx rate", 'sum(rate(eo_http_requests_total{status_class="5xx"}[5m]))', "reqps"),
    ("In flight requests", 'eo_http_in_flight', "short"),
    ("Run queue depth", 'eo_queue_depth', "short"),
    ("Run duration p95", 'histogram_quantile(0.95, sum by (le) (rate(eo_run_duration_seconds_bucket[5m])))', "s"),
    ("Simulation SLA efficiency", 'eo_sim_sla_efficiency', "percentunit"),
    ("Predictor MAE", 'eo_predictor_mae', "short"),
    ("Out of range features", 'eo_predictor_out_of_range_ratio', "percentunit"),
    ("Audit chain", 'eo_audit_chain_ok', "short"),
    ("Authentication failures", 'sum(rate(eo_auth_failures_total[5m]))', "reqps"),
    ("WebSocket connections", 'eo_ws_connections', "short"),
    ("Event loop lag p95", 'histogram_quantile(0.95, sum by (le) (rate(eo_event_loop_lag_seconds_bucket[5m])))', "s"),
]

def main() -> None:
    panels=[]
    for i,(title,expr,unit) in enumerate(QUERIES,1):
        panels.append({"id":i,"type":"timeseries","title":title,"datasource":{"type":"prometheus","uid":"prometheus"},"gridPos":{"h":8,"w":12,"x":((i-1)%2)*12,"y":((i-1)//2)*8},"targets":[{"refId":"A","expr":expr,"legendFormat":"{{policy}}"}],"fieldConfig":{"defaults":{"unit":unit},"overrides":[]},"options":{"legend":{"showLegend":True},"tooltip":{"mode":"multi"}}})
    doc={"uid":"entangleops-overview","title":"EntangleOps Overview","schemaVersion":39,"version":1,"refresh":"15s","time":{"from":"now-6h","to":"now"},"panels":panels}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(doc,indent=2)+"\n",encoding="utf-8")

if __name__ == "__main__": main()
