"""graph.py — Graphviz DAG builder for the Satisfactory factory build plan.

Usage:
    from graph import build_graph
    from solve import solve

    result = solve(RESOURCE_SUPPLY)
    dot = build_graph(result["active"], result["net"], RESOURCE_SUPPLY)
    # Render inline in a Jupyter notebook:
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
    "smelter":             ("#FF6B35", "#fff"),
    "foundry":             ("#E8521A", "#fff"),
    "constructor":         ("#2E86AB", "#fff"),
    "assembler":           ("#1B5E7C", "#fff"),
    "manufacturer":        ("#1A6B4A", "#fff"),
    "oil-refinery":        ("#6B3FA0", "#fff"),
    "blender":             ("#9C3A6B", "#fff"),
    "accelerator":         ("#B8860B", "#fff"),
    "converter":           ("#2E7D6B", "#fff"),
    "quantum-encoder":     ("#1A4A6B", "#fff"),
    "nuclear-power-plant": ("#8B0000", "#fff"),
    "packager":            ("#4A6B4A", "#fff"),
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
            nodesep="0.6",
            ranksep="1.8",
            fontname="Helvetica",
            pad="0.6",
        ),
        node_attr=dict(fontname="Helvetica", fontsize="10"),
        edge_attr=dict(
            fontname="Helvetica",
            fontsize="11",
            fontcolor="#dddddd",
        ),
    )

    # All items that appear in any active recipe edge
    active_items: set[str] = set()
    for r, _ in active:
        active_items.update(r.ingredients)
        active_items.update(r.products)

    # Items sunk (net positive output + have sink pts) — pinned right
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
        # Show total production throughput, not net excess (net is 0 for fully-consumed items)
        total_prod = sum(rate * r.products.get(item, 0) for r, rate in active if item in r.products)
        dot.node(
            f"item_{item}",
            label=f"{ITEMS[item].name}\n{total_prod:.0f}/min",
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
            label=f'''<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="3" BGCOLOR="{bg}">
  <TR><TD><B><FONT COLOR="{fg}" POINT-SIZE="14">{n}× {r.building}</FONT></B></TD></TR>
  <TR><TD><FONT COLOR="{fg}" POINT-SIZE="10">{r.name}</FONT></TD></TR>
  <TR><TD><FONT COLOR="{fg}" POINT-SIZE="9">@ {clk:.0f}%</FONT></TD></TR>
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
