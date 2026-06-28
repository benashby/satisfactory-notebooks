"""solve.py — Shared LP solver for Satisfactory AWESOME Sink optimization.

Usage:
    from solve import solve, building_spec

    result = solve(RESOURCE_SUPPLY)
    active = result["active"]   # [(Recipe, float)] — recipe + buildings-at-100%
    net    = result["net"]      # item_key -> net items/min
    pts    = result["objective"]
"""

from __future__ import annotations

import math

import pulp

from satisfactory import ITEMS, RECIPES_FOR, RESOURCES


def building_spec(fractional_buildings: float) -> tuple[int, float]:
    """Return (n_buildings, clock_pct) that exactly achieves the LP rate.

    Uses ceiling (underclock) — always produces clock_pct in [1%, 100%].

    Examples:
        building_spec(2.7)  → (3, 90.0)   # 3 buildings at 90%
        building_spec(1.0)  → (1, 100.0)
        building_spec(0.5)  → (1, 50.0)
    """
    n = max(1, math.ceil(fractional_buildings))
    clock = fractional_buildings / n * 100.0
    return n, clock


def solve(resource_supply: dict[str, float]) -> dict:
    """Run the AWESOME Sink LP and return solution components.

    Args:
        resource_supply: {item_key: items_per_min} for available raw resources.
                         Resources absent from this dict are constrained to 0,
                         preventing the LP from using them.

    Returns a dict with:
        status    (str)       — 'Optimal', 'Infeasible', 'Unbounded', etc.
        objective (float)     — total sink points/min
        active    (list)      — [(Recipe, float)]: active recipes + building rates
        net       (Callable)  — item_key -> net production rate (items/min)
        used      (dict)      — resource_key -> items/min consumed
        shadow    (dict)      — resource_key -> dual value (pts per extra unit/min)
    """
    # Gather all standard (non-alternate) recipes, deduplicated by key
    all_recipes: list = []
    seen: set[str] = set()
    for recipes in RECIPES_FOR.values():
        for r in recipes:
            if not r.is_alt and r.key not in seen:
                all_recipes.append(r)
                seen.add(r.key)

    all_items: set[str] = set()
    for r in all_recipes:
        all_items.update(r.ingredients)
        all_items.update(r.products)
    non_resource = all_items - RESOURCES

    prob = pulp.LpProblem("awesome_sink", pulp.LpMaximize)
    x = {r.key: pulp.LpVariable(f"x_{r.key}", lowBound=0) for r in all_recipes}

    def net_expr(item: str) -> pulp.LpAffineExpression:
        return pulp.lpSum(
            x[r.key] * r.products.get(item, 0) for r in all_recipes
        ) - pulp.lpSum(
            x[r.key] * r.ingredients.get(item, 0) for r in all_recipes
        )

    # Objective: maximise total AWESOME Sink points/min
    prob += pulp.lpSum(
        ITEMS[i].sink_points * net_expr(i)
        for i in non_resource
        if i in ITEMS and ITEMS[i].sink_points > 0
    ), "sink_pts_per_min"

    # Flow balance: no item consumed more than produced
    for item in non_resource:
        prob += net_expr(item) >= 0, f"flow_{item}"

    # Resource constraints — ALL resources constrained; absent ones get 0.
    # This prevents unbounded LP from packaging cycles on unconstrained resources.
    for resource in RESOURCES:
        supply = resource_supply.get(resource, 0)
        prob += (
            pulp.lpSum(
                x[r.key] * r.ingredients.get(resource, 0)
                for r in all_recipes
                if resource in r.ingredients
            )
            <= supply,
            f"res_{resource}",
        )

    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    def _val(v: pulp.LpVariable) -> float:
        return pulp.value(v) or 0.0

    def net(item: str) -> float:
        return (
            sum(_val(x[r.key]) * r.products.get(item, 0) for r in all_recipes)
            - sum(_val(x[r.key]) * r.ingredients.get(item, 0) for r in all_recipes)
        )

    active = [
        (r, _val(x[r.key]))
        for r in all_recipes
        if _val(x[r.key]) > 1e-4
    ]

    used = {
        res: sum(_val(x[r.key]) * r.ingredients.get(res, 0) for r in all_recipes)
        for res in RESOURCES
    }

    shadow = {
        res: (prob.constraints[f"res_{res}"].pi or 0.0)
        for res in RESOURCES
        if f"res_{res}" in prob.constraints
    }

    return {
        "status": pulp.LpStatus[prob.status],
        "objective": pulp.value(prob.objective) or 0.0,
        "active": active,
        "net": net,
        "used": used,
        "shadow": shadow,
    }
