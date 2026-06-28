# Factory Graph Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `factory-plan.ipynb` notebook that turns LP fractional building counts into an integer build spec + Graphviz DAG showing the full production chain with belt counts and clock speeds.

**Architecture:** Extract the LP solver into `solve.py` (shared by both notebooks), implement the Graphviz DAG builder in `graph.py` (testable pure function), then compose them in the new notebook. Tests live in `tests/`.

**Tech Stack:** PuLP (LP), graphviz Python package + Nix dot binary, pandas, nbformat, pytest

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `solve.py` | Create | LP solver returning active recipes, net output fn, shadow prices |
| `graph.py` | Create | `build_graph()` pure function → Graphviz Digraph |
| `optimization.ipynb` | Modify | Replace inline LP with `from solve import solve` |
| `factory-plan.ipynb` | Create | Build plan table + DAG render + extensibility docs |
| `tests/__init__.py` | Create | Makes tests/ a package |
| `tests/test_solve.py` | Create | pytest tests for solve.py |
| `tests/test_graph.py` | Create | pytest tests for graph.py |
| `Justfile` | Modify | Add pytest recipe; add graphviz to PATH in `run` recipe |

---

## Task 1: Test infrastructure + pytest

**Files:**
- Modify: `Justfile`
- Create: `tests/__init__.py`

- [ ] **Install pytest into venv**

```bash
uv pip install --python .venv/bin/python pytest
```

Expected output: `Installed 1 package`

- [ ] **Add pytest to Justfile setup recipe and add test recipe**

In `Justfile`, change the `uv pip install` line in `setup:` from:
```
    uv pip install --python .venv/bin/python \
        jupyterlab ipykernel numpy pandas matplotlib scipy plotly jupyter-mcp-server pulp
```
to:
```
    uv pip install --python .venv/bin/python \
        jupyterlab ipykernel numpy pandas matplotlib scipy plotly jupyter-mcp-server pulp graphviz pytest
```

Also add this recipe after the `setup:` recipe:
```
# Run all tests
test:
    env -u PYTHONPATH .venv/bin/pytest tests/ -v
```

- [ ] **Update `run` recipe in Justfile to add graphviz to PATH**

Replace the existing `run` recipe:
```
run notebook="index.ipynb":
    env -u PYTHONPATH {{JUPYTER}} nbconvert --to notebook --execute --inplace {{notebook}}
    {{JUPYTER}} trust {{notebook}}
```

With:
```
# Execute notebook and save outputs in-place (auto-trusts so HTML/JS renders in JupyterLab)
# env -u PYTHONPATH: the devshell's python language exports PYTHONPATH, which would
# shadow the venv in the spawned kernel and hide pip-installed packages (e.g. plotly).
# GV: adds graphviz dot binary to PATH so graph.py can render SVG inline.
run notebook="index.ipynb":
    #!/usr/bin/env bash
    GV=$(nix-build '<nixpkgs>' -A graphviz --no-out-link 2>/dev/null)
    [ -n "$GV" ] && export PATH="$GV/bin:$PATH"
    env -u PYTHONPATH {{JUPYTER}} nbconvert --to notebook --execute --inplace {{notebook}}
    {{JUPYTER}} trust {{notebook}}
```

- [ ] **Create `tests/__init__.py`**

```bash
mkdir -p tests && touch tests/__init__.py
```

- [ ] **Verify pytest runs (no tests yet, just infrastructure)**

```bash
env -u PYTHONPATH .venv/bin/pytest tests/ -v
```

Expected: `no tests ran` (exit code 5 is fine at this stage, or `0 passed`)

- [ ] **Commit**

```bash
git add Justfile tests/__init__.py
git commit -m "Add pytest to venv and test infrastructure; add graphviz to run PATH"
```

---

## Task 2: Create `solve.py` with tests

**Files:**
- Create: `solve.py`
- Create: `tests/test_solve.py`

- [ ] **Write the failing tests first**

Create `tests/test_solve.py`:

```python
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
    # iron-ore is a resource (constrained), net should not be positive
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
```

- [ ] **Run tests to confirm they all fail**

```bash
env -u PYTHONPATH .venv/bin/pytest tests/test_solve.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'solve'`

- [ ] **Create `solve.py`**

```python
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
from typing import Callable

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

    # Resource constraints — ALL resources constrained; absent ones get 0
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
```

- [ ] **Run tests — all should pass**

```bash
env -u PYTHONPATH .venv/bin/pytest tests/test_solve.py -v
```

Expected: all tests pass (the known objective test may take ~2s for the LP solve).

- [ ] **Commit**

```bash
git add solve.py tests/test_solve.py
git commit -m "Add solve.py: shared LP solver with building_spec helper"
```

---

## Task 3: Create `graph.py` with tests

**Files:**
- Create: `graph.py`
- Create: `tests/test_graph.py`

- [ ] **Write the failing tests first**

Create `tests/test_graph.py`:

```python
"""Tests for graph.py — the Graphviz DAG builder."""
import math
import pytest


@pytest.fixture(scope="module")
def small_solution():
    from solve import solve
    return solve({"iron-ore": 480.0, "water": 99_999.0})


def test_build_graph_returns_digraph(small_solution):
    import graphviz
    from graph import build_graph
    g = build_graph(
        small_solution["active"],
        small_solution["net"],
        {"iron-ore": 480.0, "water": 99_999.0},
    )
    assert isinstance(g, graphviz.Digraph)


def test_graph_has_recipe_nodes(small_solution):
    from graph import build_graph
    g = build_graph(
        small_solution["active"],
        small_solution["net"],
        {"iron-ore": 480.0, "water": 99_999.0},
    )
    assert "recipe_" in g.source


def test_graph_has_resource_node(small_solution):
    from graph import build_graph
    g = build_graph(
        small_solution["active"],
        small_solution["net"],
        {"iron-ore": 480.0},
    )
    assert "item_iron-ore" in g.source


def test_graph_dark_background(small_solution):
    from graph import build_graph
    g = build_graph(
        small_solution["active"],
        small_solution["net"],
        {"iron-ore": 480.0},
    )
    assert "#1a1a2e" in g.source


def test_belt_style_single():
    from graph import _belt_style
    color, pw = _belt_style(480.0)
    assert pw == "1"
    assert color == "#666688"


def test_belt_style_double():
    from graph import _belt_style
    color, pw = _belt_style(481.0)
    assert pw == "2.5"
    assert color == "#cc4400"


def test_belt_style_triple():
    from graph import _belt_style
    color, pw = _belt_style(961.0)
    assert pw == "3.5"


def test_belt_style_quad_plus():
    from graph import _belt_style
    color, pw = _belt_style(1441.0)
    assert pw == "4.5"
    assert color == "#ff2200"


def test_belt_label_single():
    from graph import _belt_label
    assert _belt_label(320.0) == "320/m"


def test_belt_label_multi():
    from graph import _belt_label
    label = _belt_label(960.0)
    assert "×2" in label
    assert "960" in label


def test_is_junction_with_split(small_solution):
    """An item consumed by 2+ active recipes is a junction."""
    from graph import _is_junction
    active = small_solution["active"]
    # Find any item consumed by more than one active recipe
    from collections import Counter
    counts = Counter()
    for r, _ in active:
        for item in r.ingredients:
            counts[item] += 1
    split_items = [k for k, v in counts.items() if v > 1]
    if split_items:
        assert _is_junction(split_items[0], active)


def test_is_not_junction_passthrough(small_solution):
    """A pass-through item (one producer, one consumer) is not a junction."""
    from graph import _is_junction
    active = small_solution["active"]
    from collections import Counter
    prod_counts = Counter()
    cons_counts = Counter()
    for r, _ in active:
        for item in r.products:
            prod_counts[item] += 1
        for item in r.ingredients:
            cons_counts[item] += 1
    passthrough = [
        k for k in prod_counts
        if prod_counts[k] == 1 and cons_counts.get(k, 0) == 1
    ]
    if passthrough:
        assert not _is_junction(passthrough[0], active)


def test_graph_rankdir_lr(small_solution):
    from graph import build_graph
    g = build_graph(
        small_solution["active"],
        small_solution["net"],
        {"iron-ore": 480.0},
    )
    assert "rankdir=LR" in g.source or 'rankdir="LR"' in g.source
```

- [ ] **Run tests — confirm they fail**

```bash
env -u PYTHONPATH .venv/bin/pytest tests/test_graph.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'graph'`

- [ ] **Create `graph.py`**

```python
"""graph.py — Graphviz DAG builder for the Satisfactory factory build plan.

Usage:
    from graph import build_graph
    from solve import solve

    result = solve(RESOURCE_SUPPLY)
    dot = build_graph(result["active"], result["net"], RESOURCE_SUPPLY)
    dot.render(...)            # write SVG/PNG
    # or in a notebook:
    from IPython.display import display, SVG
    display(SVG(dot.pipe(format='svg')))
"""

from __future__ import annotations

import math

import graphviz

from satisfactory import ITEMS, RESOURCES

BELT_CAP = 480  # items/min per physical belt line

# Fill color and text color per building type
BUILDING_COLORS: dict[str, tuple[str, str]] = {
    "smelter":            ("#FF6B35", "#fff"),
    "foundry":            ("#E8521A", "#fff"),
    "constructor":        ("#2E86AB", "#fff"),
    "assembler":          ("#1B5E7C", "#fff"),
    "manufacturer":       ("#1A6B4A", "#fff"),
    "oil-refinery":       ("#6B3FA0", "#fff"),
    "blender":            ("#9C3A6B", "#fff"),
    "accelerator":        ("#B8860B", "#fff"),
    "converter":          ("#2E7D6B", "#fff"),
    "quantum-encoder":    ("#1A4A6B", "#fff"),
    "nuclear-power-plant":("#8B0000", "#fff"),
    "packager":           ("#4A6B4A", "#fff"),
}


def _belt_style(flow: float, belt_cap: int = BELT_CAP) -> tuple[str, str]:
    """Return (color, penwidth_str) for an edge carrying flow items/min."""
    belts = math.ceil(flow / belt_cap)
    if belts <= 1:
        return "#666688", "1"
    if belts == 2:
        return "#cc4400", "2.5"
    if belts == 3:
        return "#cc4400", "3.5"
    return "#ff2200", "4.5"


def _belt_label(flow: float, belt_cap: int = BELT_CAP) -> str:
    """Edge label: flow rate + optional ×N belt count."""
    belts = math.ceil(flow / belt_cap)
    suffix = f" ×{belts}" if belts > 1 else ""
    return f"{flow:.0f}/m{suffix}"


def _is_junction(item_key: str, active: list) -> bool:
    """True if item is produced by 2+ recipes OR consumed by 2+ recipes in active."""
    producers = sum(1 for r, _ in active if item_key in r.products)
    consumers = sum(1 for r, _ in active if item_key in r.ingredients)
    return producers > 1 or consumers > 1


def build_graph(
    active: list,
    net_fn,
    resource_supply: dict[str, float],
    belt_cap: int = BELT_CAP,
) -> graphviz.Digraph:
    """Build a Graphviz Digraph representing the active production chain.

    Args:
        active:          [(Recipe, float)] from solve()["active"]
        net_fn:          solve()["net"] — item_key -> net items/min
        resource_supply: {item_key: items/min} available resources
        belt_cap:        max items/min per physical belt (default 480)

    Returns:
        graphviz.Digraph — call .pipe('svg') or display in a Jupyter cell
    """
    dot = graphviz.Digraph(
        name="factory",
        engine="dot",
        graph_attr=dict(
            rankdir="LR",
            bgcolor="#1a1a2e",
            splines="polyline",
            nodesep="0.5",
            ranksep="1.4",
            fontname="Helvetica",
            pad="0.6",
        ),
        node_attr=dict(fontname="Helvetica", fontsize="9"),
        edge_attr=dict(
            fontname="Helvetica",
            fontsize="8",
            fontcolor="#aaaacc",
        ),
    )

    # All items that appear in any active recipe edge
    active_items: set[str] = set()
    for r, _ in active:
        active_items.update(r.ingredients)
        active_items.update(r.products)

    # Items sunk (net positive output + have sink pts) — go in right cluster
    sinkable = {
        i for i in active_items - RESOURCES
        if i in ITEMS and ITEMS[i].sink_points > 0 and net_fn(i) > 0.01
    }

    # ── Resource nodes (left cluster, rank=source) ────────────────────────────
    with dot.subgraph(name="cluster_resources") as s:
        s.attr(rank="source", style="invis")
        for res, supply in resource_supply.items():
            if res not in active_items or supply <= 0:
                continue
            name = ITEMS[res].name if res in ITEMS else res
            belts = math.ceil(supply / belt_cap)
            belt_str = f"\n{belts} belts" if belts > 1 else ""
            s.node(
                f"item_{res}",
                label=f"{name}\n{supply:.0f}/min{belt_str}",
                shape="house",
                style="filled",
                fillcolor="#3d2020",
                color="#ff6060",
                fontcolor="#ffcccc",
            )

    # ── Sink nodes (right cluster, rank=sink) ─────────────────────────────────
    with dot.subgraph(name="cluster_sink") as s:
        s.attr(rank="sink", style="invis")
        for item in sorted(sinkable):
            flow = net_fn(item)
            name = ITEMS[item].name
            pts = ITEMS[item].sink_points
            s.node(
                f"item_{item}",
                label=f"{name}\n{flow:.1f}/min → SINK\n{pts:,} pts ea",
                shape="invhouse",
                style="filled",
                fillcolor="#1a3d1a",
                color="#44cc44",
                fontcolor="#aaffaa",
            )

    # ── Junction item nodes (split/merge only) ────────────────────────────────
    for item in sorted(active_items - RESOURCES - sinkable):
        if item not in ITEMS:
            continue
        if not _is_junction(item, active):
            continue
        flow = abs(net_fn(item))
        dot.node(
            f"item_{item}",
            label=f"{ITEMS[item].name}\n{flow:.0f}/min",
            shape="ellipse",
            style="filled",
            fillcolor="#2d2d4a",
            color="#6666aa",
            fontcolor="#ccccee",
        )

    # ── Recipe nodes (colored by building type) ───────────────────────────────
    from solve import building_spec
    for r, rate in active:
        n, clk = building_spec(rate)
        bg, fg = BUILDING_COLORS.get(r.building, ("#444", "#fff"))
        dot.node(
            f"recipe_{r.key}",
            label=f'''<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="2" BGCOLOR="{bg}">
  <TR><TD><B><FONT COLOR="{fg}" POINT-SIZE="11">{n}× {r.building}</FONT></B></TD></TR>
  <TR><TD><FONT COLOR="{fg}" POINT-SIZE="9">{r.name}</FONT></TD></TR>
  <TR><TD><FONT COLOR="{fg}" POINT-SIZE="8">@ {clk:.0f}%</FONT></TD></TR>
</TABLE>>''',
            shape="none",
            margin="0",
        )

    # ── Edges ─────────────────────────────────────────────────────────────────
    for r, rate in active:
        # Ingredient edges: item_node → recipe_node
        for item, qty in r.ingredients.items():
            flow = rate * qty
            if flow < 0.01:
                continue
            color, pw = _belt_style(flow, belt_cap)
            is_node = item in RESOURCES or _is_junction(item, active) or item in sinkable
            if is_node:
                lbl = _belt_label(flow, belt_cap)
            else:
                item_name = ITEMS[item].name if item in ITEMS else item
                lbl = f"{item_name}\n{_belt_label(flow, belt_cap)}"
            dot.edge(
                f"item_{item}",
                f"recipe_{r.key}",
                label=lbl,
                color=color,
                penwidth=pw,
            )

        # Product edges: recipe_node → item_node
        for item, qty in r.products.items():
            flow = rate * qty
            if flow < 0.01 or item not in active_items:
                continue
            color, pw = _belt_style(flow, belt_cap)
            is_node = _is_junction(item, active) or item in sinkable
            if is_node:
                lbl = _belt_label(flow, belt_cap)
            else:
                item_name = ITEMS[item].name if item in ITEMS else item
                lbl = f"{item_name}\n{_belt_label(flow, belt_cap)}"
            dot.edge(
                f"recipe_{r.key}",
                f"item_{item}",
                label=lbl,
                color=color,
                penwidth=pw,
            )

    return dot
```

- [ ] **Run the tests — all should pass**

```bash
env -u PYTHONPATH .venv/bin/pytest tests/test_graph.py -v
```

Expected: all pass. The `build_graph` test won't render (no graphviz binary needed — Digraph is built but not rendered), so it passes without the Nix PATH trick.

- [ ] **Commit**

```bash
git add graph.py tests/test_graph.py
git commit -m "Add graph.py: Graphviz DAG builder with belt-capacity encoding"
```

---

## Task 4: Update `optimization.ipynb` to use `solve.py`

**Files:**
- Modify: `optimization.ipynb`

The LP setup code currently lives inline in cell 8 (prob = LpProblem...), cell 9 (objective + flow balance + resource constraints), and cell 10 (solve). Replace these with a single import-and-call.

- [ ] **Identify the cells to replace**

Run in terminal:
```bash
.venv/bin/python -c "
import nbformat
nb = nbformat.read('optimization.ipynb', as_version=4)
for i, c in enumerate(nb.cells):
    if c['cell_type'] == 'code':
        src = ''.join(c['source'])
        if 'LpProblem' in src or 'prob.solve' in src or 'net_output' in src and 'def net' in src:
            print(f'Cell {i}: {src[:80]}')
"
```

Note the cell indices of: (a) the `prob = pulp.LpProblem(...)` cell, (b) the objective/constraints cell, (c) the `prob.solve(...)` cell.

- [ ] **Replace LP cells with solve import**

Use `just run optimization.ipynb` after editing. The edit: find the three LP cells and replace them with two cells:

**Cell A — import and run (replaces the 3 LP cells):**
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))

from solve import solve

result = solve(RESOURCE_SUPPLY)
status    = result["status"]
objective = result["objective"]
active    = result["active"]
net_output = result["net"]
used      = result["used"]
shadow    = result["shadow"]

print(f"Status:          {status}")
print(f"Sink points/min: {objective:,.0f}")
```

(Keep all downstream cells — the assertions, results tables, Sankey — they already use `active`, `net_output`, etc. which are now set from `result`.)

Also update the `all_recipes` variable that downstream cells reference. Add after the result unpacking:

```python
from satisfactory import RECIPES_FOR
all_recipes = []
seen = set()
for recipes in RECIPES_FOR.values():
    for r in recipes:
        if not r.is_alt and r.key not in seen:
            all_recipes.append(r)
            seen.add(r.key)
all_items = set()
for r in all_recipes:
    all_items.update(r.ingredients)
    all_items.update(r.products)
from satisfactory import RESOURCES
non_resource_items = all_items - RESOURCES
```

- [ ] **Also update `x` variable references in assertions**

The assertion cell references `x[r.key]` directly (the PuLP variable). Since `solve.py` encapsulates that, replace any `pulp.value(x[r.key])` with `(get_val := lambda r, rate: rate)` — actually, the assertion cell uses `get_val(x[r.key])` which calls `pulp.value`. Replace the assertion's manual resource check with:

In the assertion cell, change:
```python
actual = sum(
    get_val(x[r.key]) * r.ingredients.get(resource, 0)
    for r in all_recipes
)
```
to:
```python
actual = used.get(resource, 0)
```

And change the objective manual recompute:
```python
manual_obj = sum(
    ITEMS[item].sink_points * (
        sum(get_val(x[r.key]) * r.products.get(item, 0) for r in all_recipes)
        - sum(get_val(x[r.key]) * r.ingredients.get(item, 0) for r in all_recipes)
        ...
    )
```
to:
```python
manual_obj = sum(
    ITEMS[item].sink_points * net_output(item)
    for item in non_resource_items
    if item in ITEMS and ITEMS[item].sink_points > 0
)
```

- [ ] **Run notebook to verify same result**

```bash
just run optimization.ipynb
```

Check the output of the solve cell: should show `Status: Optimal` and `Sink points/min: 835,077`. Check the assertions cell: should print `All assertions passed.`

- [ ] **Commit**

```bash
git add optimization.ipynb
git commit -m "Refactor optimization.ipynb to use shared solve.py"
```

---

## Task 5: Create `factory-plan.ipynb`

**Files:**
- Create: `factory-plan.ipynb`

- [ ] **Generate the notebook with nbformat**

Create and run `/tmp/make_factory_plan.py`:

```python
import nbformat as nbf

nb = nbf.v4.new_notebook()
cells = []
md  = lambda s: nbf.v4.new_markdown_cell(s)
code = lambda s: nbf.v4.new_code_cell(s)

# ── Introduction ──────────────────────────────────────────────────────────────
cells.append(md("""\
# Satisfactory Factory Build Plan

**What this shows:** For your current resource nodes, the LP optimizer found the
recipe mix that maximises AWESOME Sink points/min. This notebook converts those
fractional building counts into a concrete build spec:

- **Build plan table** — every active recipe: how many buildings to place and at
  what clock speed to set each one (always underclocked, never exceeds 100%)
- **Production graph** — a hierarchical diagram showing what feeds into what,
  flow rates on every connection, and orange/red highlighting on connections that
  need more than one physical belt line

## How to update when you claim new nodes

```python
# In the RESOURCE_SUPPLY cell below, change the number:
'iron-ore': 5 * 480,   # was 5 veins → change to 7 * 480 after claiming 2 more
```

Re-run the notebook top-to-bottom. The LP reoptimises everything simultaneously.

## How to unlock a new tier (e.g. bauxite after Phase 3)

Add the new resource to `RESOURCE_SUPPLY`:

```python
'bauxite':      4 * 480,   # Miner Mk.3 on pure node → 480/min each
'nitrogen-gas': 2 * 120,   # Resource Well Extractor equivalent
```

All tier 7–9 recipes are already in `data.json`. Adding the resource activates
the full aluminum/converter/quantum chain automatically.

## Switching objective: sink points → phase completion

To optimise for completing a specific Space Elevator phase instead of farming
sink points, open `solve.py` and swap the objective line:

```python
# Current (sink points):
prob += pulp.lpSum(ITEMS[i].sink_points * net_expr(i) ...)

# Phase completion rate (e.g. Phase 4 parts):
PHASE4 = {'assembly-director-system', 'magnetic-field-generator',
           'thermal-propulsion-rocket', 'nuclear-pasta'}
prob += pulp.lpSum(net_expr(p) for p in PHASE4), "phase4_rate"
```
"""))

# ── Setup ─────────────────────────────────────────────────────────────────────
cells.append(code("""\
import os, sys, math
from pathlib import Path

# Add repo root to path so we can import solve, graph, satisfactory
sys.path.insert(0, str(Path('.').resolve()))

# Ensure graphviz dot binary is on PATH (installed via Nix in this repo)
import subprocess
_gv = subprocess.run(
    ['nix-build', '<nixpkgs>', '-A', 'graphviz', '--no-out-link'],
    capture_output=True, text=True
).stdout.strip()
if _gv:
    os.environ['PATH'] = f"{_gv}/bin:{os.environ['PATH']}"

import pandas as pd
from IPython.display import display, HTML, SVG

from solve import solve, building_spec
from graph import build_graph, BELT_CAP
from satisfactory import ITEMS
"""))

# ── Resource supply ────────────────────────────────────────────────────────────
cells.append(md("## Resource Supply\n\nEdit this cell to reflect your claimed nodes. Re-run top-to-bottom after any change."))

cells.append(code("""\
# items/min from claimed extraction nodes
# Format: 'resource-key': n_veins * items_per_min_per_vein
RESOURCE_SUPPLY: dict[str, float] = {
    'iron-ore':     5 * 480,   # 2,400/min
    'copper-ore':   2 * 480,   #   960/min
    'coal':         3 * 480,   # 1,440/min
    'limestone':    2 * 480,   #   960/min
    'crude-oil':    2 * 300,   #   600/min
    'water':        99_999,    # effectively unlimited (Water Extractors)
    'caterium-ore': 2 * 480,   #   960/min
    # Unlock new tiers by adding resources here, e.g.:
    # 'bauxite':      4 * 480,
    # 'nitrogen-gas': 2 * 120,
}
"""))

# ── Solve ─────────────────────────────────────────────────────────────────────
cells.append(code("""\
result = solve(RESOURCE_SUPPLY)
print(f"Status:          {result['status']}")
print(f"Sink points/min: {result['objective']:,.0f}")
print(f"Active recipes:  {len(result['active'])}")
"""))

# ── Build plan table ───────────────────────────────────────────────────────────
cells.append(md("""\
## Build Plan

Every active recipe with its building count and clock speed.
\"Clock %\" is always ≤ 100% (underclocked) — set this in-game via the building's
clock dial. **Belt lines** = number of physical conveyor belts needed for that connection.
"""))

cells.append(code("""\
rows = []
for r, rate in sorted(result['active'], key=lambda x: (x[0].building, x[0].name)):
    n, clk = building_spec(rate)
    rows.append({
        'Recipe':    r.name,
        'Building':  r.building,
        'Count':     n,
        'Clock %':   round(clk, 1),
        'Rate out':  ', '.join(
            f"{ITEMS[k].name if k in ITEMS else k} {v*rate:.1f}/min "
            f"(×{math.ceil(v*rate/BELT_CAP)}belt)"
            if math.ceil(v*rate/BELT_CAP) > 1
            else f"{ITEMS[k].name if k in ITEMS else k} {v*rate:.1f}/min"
            for k, v in r.products.items()
        ),
    })

df = pd.DataFrame(rows)
display(
    df.style
    .hide(axis='index')
    .set_table_styles([{'selector': 'th', 'props': [('text-align', 'left')]}])
    .format({'Clock %': '{:.1f}%'})
)
print(f"\\nTotal active buildings: {sum(r['Count'] for r in rows)}")
"""))

# ── Resource utilization ───────────────────────────────────────────────────────
cells.append(md("## Resource Utilization & Bottlenecks\n\nThe **shadow price** tells you how many extra sink points/min you'd gain by adding one more unit/min of that resource. The highest shadow price is your real bottleneck."))

cells.append(code("""\
util_rows = []
for res, supply in RESOURCE_SUPPLY.items():
    used = result['used'].get(res, 0.0)
    shadow = result['shadow'].get(res, 0.0)
    util_rows.append({
        'Resource': res,
        'Supply': f"{supply:.0f}/min" if supply < 90_000 else '∞',
        'Used': f"{used:.1f}/min",
        'Utilisation': f"{100*used/supply:.1f}%" if supply < 90_000 else 'N/A',
        'Shadow price (pts/unit)': round(shadow, 2),
    })

df_util = (
    pd.DataFrame(util_rows)
    .sort_values('Shadow price (pts/unit)', ascending=False)
    .reset_index(drop=True)
)
display(df_util.style.hide(axis='index'))
"""))

# ── Production graph ───────────────────────────────────────────────────────────
cells.append(md("""\
## Production Graph

Left → Right: raw resources flow left, AWESOME Sink items arrive right.

- **Colored boxes** = recipe nodes. Color = building type. Label shows N× buildings @ clock%.
- **Ellipses** = intermediate items that split or merge routes (multi-producer or multi-consumer).
- **Gray edges** = single-belt flows (≤ 480/min).
- **Orange/red edges** = multi-belt flows. Label suffix shows ×N belt count needed.

Pass-through items (one producer, one consumer) appear as labels on the edge rather than as separate nodes — this keeps the graph compact.
"""))

cells.append(code("""\
dot = build_graph(result['active'], result['net'], RESOURCE_SUPPLY)

# Render inline as SVG (vector, zoomable in JupyterLab)
svg_bytes = dot.pipe(format='svg')
display(SVG(svg_bytes))
"""))

# ── Write notebook ─────────────────────────────────────────────────────────────
nb.cells = cells
nbf.write(nb, '/home/bashby/projects/bashby/satisfactory/factory-plan.ipynb')
print("Written factory-plan.ipynb")
```

Run the script:

```bash
.venv/bin/python /tmp/make_factory_plan.py
```

Expected: `Written factory-plan.ipynb`

- [ ] **Execute and trust the notebook**

```bash
just run factory-plan.ipynb
```

Expected: notebook runs without errors; output of the solve cell shows `Status: Optimal` and `Sink points/min: 835,077`.

If the graph cell fails due to a missing `dot` binary (the `nix-build` call in setup didn't work), run manually:

```bash
GV=$(nix-build '<nixpkgs>' -A graphviz --no-out-link 2>/dev/null)
echo $GV/bin/dot
```

Then hardcode the path in the notebook's setup cell temporarily to debug.

- [ ] **Verify the graph renders in JupyterLab**

Open http://localhost:8888 (or check `just status` for the URL). Open `factory-plan.ipynb` and confirm:
- Build plan table shows recipes with building counts and clock %
- Resource utilization table shows shadow prices
- SVG graph renders inline (resources on left, sink items on right, orange multi-belt edges visible)

- [ ] **Commit**

```bash
git add factory-plan.ipynb
git commit -m "Add factory-plan.ipynb: build plan table + Graphviz production DAG"
```

---

## Task 6: Run full test suite and final checks

**Files:** none new

- [ ] **Run all tests**

```bash
env -u PYTHONPATH .venv/bin/pytest tests/ -v
```

Expected: all tests pass (green).

- [ ] **Run both notebooks end-to-end**

```bash
just run optimization.ipynb && just run factory-plan.ipynb
```

Expected: both execute without errors.

- [ ] **Verify optimization.ipynb still shows 835,077 pts/min**

```bash
.venv/bin/python -c "
import nbformat
nb = nbformat.read('optimization.ipynb', as_version=4)
for c in nb.cells:
    for out in getattr(c, 'outputs', []):
        txt = getattr(out, 'text', '')
        if 'Sink points' in txt:
            print(txt.strip())
"
```

Expected: `Sink points/min: 835,077`

- [ ] **Commit final state**

```bash
git add -A
git commit -m "Verified: all tests pass, both notebooks produce consistent 835,077 pts/min"
```

---

## Self-Review

**Spec coverage:**
- ✅ `solve.py` extracted — both notebooks share one solver
- ✅ `building_spec()` — ceiling + underclock, always ≤ 100%
- ✅ `graph.py` — dark bipartite LR, HTML table recipe nodes, dual-encoded multi-belt edges
- ✅ Junction-only item nodes (pass-throughs on edges)
- ✅ Resources pinned left (`rank='source'`), sink pinned right (`rank='sink'`)
- ✅ Belt capacity table in build plan (`ceil(flow/480)`)
- ✅ Extensibility documented in notebook intro cell
- ✅ Objective-switching documented with code example
- ✅ Graphviz PATH handled both in `just run` (Justfile) and in notebook setup cell

**Placeholder scan:** No TBDs, no "implement later", all code blocks are complete.

**Type consistency:**
- `building_spec` defined in `solve.py`, imported in `graph.py` and notebook — consistent
- `active` is always `list[tuple[Recipe, float]]` — solve.py returns it, graph.py and notebook consume it — consistent
- `net` / `net_fn` callable signature `(str) -> float` — consistent across solve.py, graph.py, tests
