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
