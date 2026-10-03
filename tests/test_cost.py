from mathlab.cost import estimate_astra_cost, estimate_model_cost


def test_cost_estimate():
    # 1M input with 0.2M cached + 0.1M output = 8 + .2 + 5 = 13.2
    assert abs(estimate_astra_cost(1_000_000, 200_000, 100_000) - 13.2) < 1e-9


def test_mini_cost_estimate():
    # 1M input with 0.2M cached + 0.1M output = .6 + .015 + .45 = 1.065
    assert abs(estimate_model_cost("gpt-5.4-mini", 1_000_000, 200_000, 100_000) - 1.065) < 1e-9
