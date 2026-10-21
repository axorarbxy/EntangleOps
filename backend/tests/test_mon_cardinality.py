from monitoring import metrics

def test_metrics_do_not_use_sensitive_label_names():
    forbidden={"run_id","key_id","ip","path","url","error","message","user"}
    for family in metrics.registry.collect():
        assert not forbidden.intersection(family.labels)
