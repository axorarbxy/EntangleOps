import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def test_generated_dashboard_has_unique_ids_and_uid():
    doc=json.loads((ROOT/"monitoring/grafana/dashboards/entangleops.json").read_text())
    ids=[p["id"] for p in doc["panels"]]
    assert doc["uid"]=="entangleops-overview" and len(ids)==len(set(ids))
