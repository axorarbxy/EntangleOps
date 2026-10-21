from starlette.routing import Route
from monitoring.middleware import route_label

def test_metrics_route_uses_template_and_bounds_unknown_paths():
    assert route_label({"route":Route("/api/v1/simulations/{rid}",lambda request:None)})=="/api/v1/simulations/{rid}"
    assert route_label({"path":"/secret/raw/id"})=="unmatched"
