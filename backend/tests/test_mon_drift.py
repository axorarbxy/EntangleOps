from monitoring.drift import DriftMonitor

def test_drift_monitor_is_created_with_bounded_sample_interval():
    class Predictor: pass
    monitor=DriftMonitor(Predictor(),None,{},sample_every=0)
    assert monitor.sample_every==1
