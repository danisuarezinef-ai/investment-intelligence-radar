from radar_brain_readiness_v1 import _economic_edge_state


def test_cost_adjusted_edge_requires_positive_net_return():
    assert _economic_edge_state(True, 0.001) == 'PASS'
    assert _economic_edge_state(True, 0.0) == 'FAILED'
    assert _economic_edge_state(True, -0.001) == 'FAILED'
    assert _economic_edge_state(False, 0.1) == 'PENDING_SAMPLE'
    assert _economic_edge_state(True, None) == 'PENDING_SAMPLE'


def test_benchmark_relative_edge_requires_positive_excess_return():
    assert _economic_edge_state(True, 0.002) == 'PASS'
    assert _economic_edge_state(True, -0.002) == 'FAILED'
