"""Tests for solve.py — the shared LP solver module."""
import pytest


SMALL_SUPPLY = {"iron-ore": 480.0, "water": 99_999.0}

FULL_SUPPLY = {
    "iron-ore": 2400.0,
    "copper-ore": 960.0,
    "coal": 1440.0,
    "limestone": 960.0,
    "crude-oil": 600.0,
    "water": 99_999.0,
    "caterium-ore": 960.0,
}


def test_solve_returns_required_keys():
    from solve import solve
    result = solve(SMALL_SUPPLY)
    assert set(result.keys()) == {"status", "objective", "active", "net", "used", "shadow"}


def test_solve_optimal_status():
    from solve import solve
    result = solve(SMALL_SUPPLY)
    assert result["status"] == "Optimal"


def test_solve_objective_positive():
    from solve import solve
    result = solve(SMALL_SUPPLY)
    assert result["objective"] > 0


def test_solve_empty_supply_gives_zero():
    from solve import solve
    result = solve({})
    assert result["objective"] == pytest.approx(0.0, abs=0.1)


def test_solve_resources_within_supply():
    from solve import solve
    result = solve(FULL_SUPPLY)
    for res, supply in FULL_SUPPLY.items():
        if supply < 90_000:
            assert result["used"].get(res, 0) <= supply + 1e-3, \
                f"{res} used {result['used'].get(res, 0):.2f} > supply {supply}"


def test_solve_flow_balance_non_negative():
    from solve import solve
    from satisfactory import RECIPES_FOR, RESOURCES
    result = solve(SMALL_SUPPLY)
    all_items = set()
    for recipes in RECIPES_FOR.values():
        for r in recipes:
            all_items.update(r.ingredients)
            all_items.update(r.products)
    for item in all_items - RESOURCES:
        net = result["net"](item)
        assert net >= -1e-3, f"Negative net for {item}: {net:.4f}"


def test_solve_known_objective_full_supply():
    """Regression: full user supply gives expected sink pts/min."""
    from solve import solve
    result = solve(FULL_SUPPLY)
    assert result["status"] == "Optimal"
    assert abs(result["objective"] - 835_077) < 1_000   # within ~0.1%


def test_solve_active_recipes_non_empty():
    from solve import solve
    result = solve(SMALL_SUPPLY)
    assert len(result["active"]) > 0


def test_solve_net_callable():
    from solve import solve
    result = solve(SMALL_SUPPLY)
    net = result["net"]
    assert callable(net)
    val = net("iron-ingot")
    assert isinstance(val, float)


def test_building_spec_ceiling():
    from solve import building_spec
    n, clk = building_spec(2.7)
    assert n == 3
    assert abs(clk - 90.0) < 0.01


def test_building_spec_exact():
    from solve import building_spec
    n, clk = building_spec(1.0)
    assert n == 1
    assert clk == pytest.approx(100.0)


def test_building_spec_fraction():
    from solve import building_spec
    n, clk = building_spec(0.5)
    assert n == 1
    assert clk == pytest.approx(50.0)


def test_building_spec_never_exceeds_100():
    from solve import building_spec
    import random
    for _ in range(50):
        rate = random.uniform(0.01, 10.0)
        _, clk = building_spec(rate)
        assert clk <= 100.0 + 1e-9
