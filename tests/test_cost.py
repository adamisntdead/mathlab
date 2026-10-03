from mathlab.cost import estimate_astra_cost, estimate_model_cost


def test_cost_estimate():
    # 1M input with 0.2M cached + 0.1M output = 8 + .2 + 5 = 13.2
    assert abs(estimate_astra_cost(1_000_000, 200_000, 100_000) - 13.2) < 1e-9


def test_luna_cost_estimate():
    # 1M input with 0.2M cached + 0.1M output = .08 + .002 + .05 = .132
    assert abs(estimate_model_cost("gpt-6-luna", 1_000_000, 200_000, 100_000) - 0.132) < 1e-9
