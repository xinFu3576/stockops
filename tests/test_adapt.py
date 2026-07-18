from datetime import date
from tools.adapt import suggest_weights, DEFAULT_WEIGHTS


def test_empty_falls_back():
    s = {"total": 0, "min_samples": 5,
         "per_analyst": {k: {"n": 0, "hit_rate": None, "avg_alpha": 0.0} for k in DEFAULT_WEIGHTS}}
    assert suggest_weights(s) == DEFAULT_WEIGHTS


def test_high_alpha_gets_more_weight():
    s = {"total": 10, "min_samples": 5,
         "per_analyst": {
             "technical":   {"n": 10, "hit_rate": 0.7, "avg_alpha": 0.05},
             "fundamental": {"n": 10, "hit_rate": 0.6, "avg_alpha": 0.03},
             "sentiment":   {"n": 10, "hit_rate": 0.4, "avg_alpha": -0.02},
             "macro_event": {"n": 10, "hit_rate": 0.5, "avg_alpha": 0.01},
             "portfolio_view": {"n": 10, "hit_rate": 0.55, "avg_alpha": 0.02},
         }}
    w = suggest_weights(s)
    assert w["technical"] > w["sentiment"]
    assert abs(sum(w.values()) - 1.0) < 0.01
