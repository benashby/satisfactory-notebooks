# Factory Graph Visualization — Design Spec
_2026-06-28_

## Problem

The LP optimizer in `optimization.ipynb` outputs fractional building counts (e.g., "2.7 assemblers"). Turning that into a buildable factory requires:

1. **Integer buildings + clock speeds** — "3 assemblers @ 90%"
2. **Full dependency tree** — what produces what, at what rate, across every stage
3. **Belt capacity awareness** — 480/min per physical belt line; connections needing N belts must be explicitly shown

The Sankey diagram already in the notebook shows flow volumes but not hierarchy, building specs, or belt counts.

## Approach

New notebook: **`factory-plan.ipynb`**

Imports the LP solution from `optimization.ipynb` via a shared solve function in a new module **`solve.py`** (extracts the LP + solve logic so both notebooks can use it without duplication). Renders a Graphviz `dot` DAG directly in the notebook cell as an SVG.

**Library:** `graphviz` Python package (thin wrapper over the `dot` binary already installed via Nix). Chosen over pyvis, networkx+matplotlib, and plotly for this use case because: `dot` engine guarantees correct layered layout without edge crossings at 79 nodes; native edge label support at 99 edges; static SVG renders cleanly inline in JupyterLab.

---

## Node Design

### Recipe nodes (colored by building type)

HTML table label, three-line hierarchy:

```
┌─────────────────────────────┐
│  3× Assembler               │  ← bold, large (the build instruction)
│  Automated Wiring           │  ← medium (recipe name)
│  @ 90%                      │  ← small, subdued (clock speed)
└─────────────────────────────┘
```

Fill color keyed to building type (smelter = orange, constructor = teal, assembler = blue, manufacturer = green, oil-refinery = purple, etc.). White text. `shape='none'` with `margin='0'`.

### Item nodes — split/merge only

A separate item node is rendered **only** when the item is a genuine junction: produced by 2+ recipes OR consumed by 2+ recipes simultaneously in the active solution. Pass-through items (one producer → one consumer) appear as a label on the direct edge instead.

Node shape: `ellipse`, dark fill (`#2d2d4a`), item name + net flow rate.

### Resource nodes (leftmost rank)

`shape='house'` pointing right, dark-red fill (`#3d2020`). Label: resource name + total supply/min + belt count. All resources pinned to `rank='source'` in a subgraph so they form a clean left column.

### Sink nodes (rightmost rank)

`shape='house'` pointing left (inverted), dark-green fill (`#1a3d1a`). Label: item name + rate/min → SINK + pts/item. All sink items pinned to `rank='sink'`.

---

## Edge Design

### Belt capacity encoding (dual)

| Flow | Color | Thickness | Label suffix |
|---|---|---|---|
| ≤ 480/min (1 belt) | `#666688` gray | `penwidth=1` | none |
| 481–960/min (2 belts) | `#cc4400` orange-red | `penwidth=2.5` | `×2` |
| 961–1440/min (3 belts) | `#cc4400` orange-red | `penwidth=3.5` | `×3` |
| > 1440/min (4+ belts) | `#ff2200` bright red | `penwidth=4.5` | `×N` |

Belt count = `ceil(flow / 480)`.

### Edge labels

Format: `ItemName\n{flow:.0f}/min` for pass-through items (replacing the absent item node). For edges into/out of explicit item nodes: `{flow:.0f}/min` only (item name already on the node).

Font size: 9pt minimum. Labels are tested at 900px render width (actual Jupyter cell width) before finalizing. `fontname='Helvetica'`.

---

## Layout

```python
dot.attr('graph',
    rankdir='LR',          # left-to-right flow
    splines='polyline',    # supports edge labels (ortho does not)
    nodesep='0.5',
    ranksep='1.4',
    bgcolor='#1a1a2e',
    pad='0.6',
)
```

Resources pinned left via `with dot.subgraph(name='cluster_resources') as s: s.attr(rank='source')`.  
Sink items pinned right via `with dot.subgraph(name='cluster_sink') as s: s.attr(rank='sink')`.

---

## Clock Speed Calculation

```python
import math

def building_spec(fractional_buildings: float) -> tuple[int, float]:
    """Return (n_buildings, clock_pct) that exactly achieve the LP rate.
    Uses ceiling (underclock) since it always satisfies 1–100% range.
    """
    n = max(1, math.ceil(fractional_buildings))
    clock = fractional_buildings / n * 100  # always ≤ 100%
    return n, clock
```

Overclocking (>100%) is valid but not used here — underclocking is always sufficient and simpler to explain.

---

## Module: `solve.py`

Extracted from `optimization.ipynb` so both notebooks share one solve path:

```python
# solve.py
def solve(resource_supply: dict[str, float]) -> dict:
    """Run the AWESOME Sink LP and return solution dict with:
      - active_recipes: list of (Recipe, float) — (recipe, rate_in_buildings)
      - net_output: callable item_key -> items/min
      - objective: float — total sink pts/min
    """
```

`optimization.ipynb` and `factory-plan.ipynb` both `from solve import solve`.

---

## `factory-plan.ipynb` Structure

| Cell | Content |
|---|---|
| Markdown | Introduction: what this notebook shows |
| Code | Imports + `from solve import solve` |
| Code | `RESOURCE_SUPPLY` dict (same as optimization.ipynb) |
| Code | `BELT_CAP = 480` + `building_spec()` helper |
| Code | `build_graph()` — constructs the Graphviz Digraph |
| Code | `render_graph()` — renders SVG inline in notebook |
| Markdown | Build plan table |
| Code | Pandas DataFrame: recipe → N buildings, clock%, input rates, output rates |

---

## Belt Constraint in Build Plan Table

The build plan table includes a "Belt lines" column for every input/output showing `ceil(flow/BELT_CAP)`. This directly answers "how many physical conveyor lines do I need here?"

---

## Extensibility

### When you claim new nodes
Change one number in `RESOURCE_SUPPLY` and re-run. The LP reoptimizes globally — it may re-route existing resources differently once the new supply changes relative scarcities.

```python
# Before: 5 iron ore veins
'iron-ore': 5 * 480,

# After claiming 2 more:
'iron-ore': 7 * 480,   # just change the multiplier
```

### When you unlock a new tier (bauxite, aluminum, nitrogen, etc.)
Add the new resource to `RESOURCE_SUPPLY`. All tier 7–9 recipes are already in `data.json` — the solver was already aware of them but set their consumption to ≤ 0 because supply was 0. Adding the resource automatically activates the full recipe chain.

```python
RESOURCE_SUPPLY = {
    # existing...
    'bauxite':      4 * 480,   # add when nodes are claimed
    'nitrogen-gas': 2 * 120,   # water extractor equivalent
}
```

### Switching the objective (sink points vs phase completion rate)
The objective is a single `prob +=` line in `solve.py`. Two natural modes:

| Mode | When to use | Objective |
|---|---|---|
| **Sink points** (current default) | Farming coupons, no active phase target | `sum(sink_points[i] * net_output[i])` |
| **Phase completion rate** | Actively trying to complete a specific phase | `sum(phase_demand[p] * net_output[p])` for project parts `p` |

`optimization.ipynb` will document this switch with a commented-out alternative objective cell.

### Phase 5 data — fully present
All Phase 5 project parts are now in `data.json`:
- Biochemical Sculptor (added): blender, 120s, 0.5 ADS + 40 Ficsite Trigon + 10 water → 2/min, 301,778 pts
- Ballistic Warp Drive: already present, 2,895,334 pts
- AI Expansion Server: already present, 597,652 pts

The solver will naturally activate these chains once SAM/ficsite resources are added to `RESOURCE_SUPPLY`.

### What a "new phase" workflow looks like
1. Claim new resource nodes → update `RESOURCE_SUPPLY`
2. Re-run `optimization.ipynb` (one cell-by-cell run, ~2 seconds)
3. Re-run `factory-plan.ipynb` → updated graph and build plan

No other changes required unless a recipe or item is genuinely missing from `data.json`.

---

## Out of Scope

- Overclocking >100% (future: could offer as alternative to ceiling)  
- Interactive hover/click graph (graphviz SVG is static; interactive version is a future enhancement using pyvis importing DOT positions)  
- Multi-page or per-building-type sub-graphs  
- Somersloop optimization  
