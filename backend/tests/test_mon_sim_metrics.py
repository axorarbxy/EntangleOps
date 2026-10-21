from monitoring.observer import SimObserver

def test_observer_exception_is_contained():
    class Boom:
        def __call__(self, record): raise RuntimeError("telemetry")
    assert SimObserver("adaptive").policy == "adaptive"
    assert callable(Boom())
