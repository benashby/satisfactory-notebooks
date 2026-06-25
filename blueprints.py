"""
blueprints.py — Blueprint registry and blueprint-aware production planner.

A Blueprint is a pre-built factory module with fixed I/O rates at 100% clock.
Underclocking scales all rates linearly.

    from blueprints import BLUEPRINTS, blueprint_plan, optimize_from_supply
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from satisfactory import (
    RESOURCES, Recipe,
    recipe_for, buildings_needed,
)


# ---------------------------------------------------------------------------
# Blueprint data type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Blueprint:
    name: str
    inputs: dict[str, float]   # item_key -> items/min at 100% clock
    outputs: dict[str, float]  # item_key -> items/min at 100% clock

    def copies_and_clock(self, item_key: str, needed_rate: float) -> tuple[int, float]:
        """Integer copy count and clock fraction (0–1) to hit needed_rate of item_key."""
        rate_per_copy = self.outputs[item_key]
        raw = needed_rate / rate_per_copy
        copies = math.ceil(raw)
        clock = raw / copies if copies else 0.0
        return copies, clock


# ---------------------------------------------------------------------------
# Plan node — one step in a blueprint plan tree
# ---------------------------------------------------------------------------

@dataclass
class PlanNode:
    item_key: str
    rate: float                        # items/min demanded at this node

    # Exactly one of these is set (or neither for raw resources)
    blueprint: Optional[Blueprint] = None
    recipe: Optional[Recipe] = None

    # Blueprint-specific
    copies: int = 0
    clock: float = 1.0                 # 0.0–1.0

    # Recipe-specific
    buildings: float = 0.0            # fractional building count

    children: list[PlanNode] = field(default_factory=list)

    # ------------------------------------------------------------------

    @property
    def is_resource(self) -> bool:
        return self.blueprint is None and self.recipe is None

    @property
    def clock_pct(self) -> float:
        return self.clock * 100.0

    @property
    def effective_outputs(self) -> dict[str, float]:
        if not self.blueprint:
            return {}
        scale = self.copies * self.clock
        return {k: v * scale for k, v in self.blueprint.outputs.items()}

    @property
    def effective_inputs(self) -> dict[str, float]:
        if not self.blueprint:
            return {}
        scale = self.copies * self.clock
        return {k: v * scale for k, v in self.blueprint.inputs.items()}

    @property
    def label(self) -> str:
        if self.blueprint:
            return f"{self.copies}x [{self.blueprint.name}] @ {self.clock_pct:.1f}%"
        if self.recipe:
            return f"{self.buildings:.2f}x {self.recipe.building} ({self.recipe.name})"
        return f"[raw] {self.item_key}"

    # ------------------------------------------------------------------

    def all_nodes(self) -> list[PlanNode]:
        result: list[PlanNode] = [self]
        for child in self.children:
            result.extend(child.all_nodes())
        return result

    def raw_resources(self) -> dict[str, float]:
        """Total items/min of each raw resource consumed by the full subtree."""
        totals: dict[str, float] = {}
        for node in self.all_nodes():
            if node.is_resource:
                totals[node.item_key] = totals.get(node.item_key, 0.0) + node.rate
        return totals

    def blueprint_steps(self) -> list[PlanNode]:
        """All blueprint nodes in the subtree (depth-first)."""
        return [n for n in self.all_nodes() if n.blueprint is not None]

    def building_totals(self) -> dict[str, float]:
        """Fractional building counts by building key for recipe (non-blueprint) nodes."""
        totals: dict[str, float] = {}
        for node in self.all_nodes():
            if node.recipe:
                b = node.recipe.building
                totals[b] = totals.get(b, 0.0) + node.buildings
        return totals

    def print_tree(self, indent: int = 0) -> None:
        prefix = "  " * indent
        print(f"{prefix}{self.rate:.2f}/min {self.item_key}  ← {self.label}")
        for child in self.children:
            child.print_tree(indent + 1)


# ---------------------------------------------------------------------------
# Blueprint registry — add yours here
# ---------------------------------------------------------------------------

BLUEPRINTS: dict[str, Blueprint] = {
    # key = the primary output item_key this blueprint produces

    "iron-rod": Blueprint(
        name="60 ingots to 60 rods",
        inputs={"iron-ingot": 60.0},
        outputs={"iron-rod": 60.0},
    ),
    "screw": Blueprint(
        name="40 ingots to 160 screws",
        inputs={"iron-ingot": 40.0},
        outputs={"screw": 160.0},
    ),
    "iron-plate": Blueprint(
        name="120 Iron Ingots to 80 Iron Plates",
        inputs={"iron-ingot": 120.0},
        outputs={"iron-plate": 80.0},
    ),
    "smart-plating": Blueprint(
        name="6rip,6rotor to 6smart plating",
        inputs={"reinforced-iron-plate": 6.0, "rotor": 6.0},
        outputs={"smart-plating": 6.0},
    ),
    "rotor": Blueprint(
        name="60 rod,300 screw to 12 rotor",
        inputs={"iron-rod": 60.0, "screw": 300.0},
        outputs={"rotor": 12.0},
    ),
    "reinforced-iron-plate": Blueprint(
        name="90 plate,180 screw to 15 rip",
        inputs={"iron-plate": 90.0, "screw": 180.0},
        outputs={"reinforced-iron-plate": 15.0},
    ),
}


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

def _find_blueprint(item_key: str, bp_map: dict[str, Blueprint]) -> Optional[Blueprint]:
    """Return the blueprint whose primary output is item_key, or None."""
    return bp_map.get(item_key)


def _resolve(
    item_key: str,
    rate: float,
    bp_map: dict[str, Blueprint],
    prefer_alt: bool,
    supply_boundaries: frozenset[str] = frozenset(),
) -> PlanNode:
    """Recursively resolve item_key at rate into a PlanNode tree."""

    # Raw resource or explicit supply boundary — leaf, no further resolution
    if item_key in RESOURCES or item_key in supply_boundaries:
        return PlanNode(item_key=item_key, rate=rate)

    # Blueprint available — use it, then recurse into its inputs
    bp = _find_blueprint(item_key, bp_map)
    if bp:
        copies, clock = bp.copies_and_clock(item_key, rate)
        scale = copies * clock  # = rate / bp.outputs[item_key]
        children = [
            _resolve(ing_key, ing_rate * scale, bp_map, prefer_alt, supply_boundaries)
            for ing_key, ing_rate in bp.inputs.items()
        ]
        return PlanNode(
            item_key=item_key,
            rate=rate,
            blueprint=bp,
            copies=copies,
            clock=clock,
            children=children,
        )

    # No blueprint — fall back to recipe
    recipe = recipe_for(item_key, prefer_alt)
    if recipe is None:
        # Not a known resource and no recipe — treat as raw
        return PlanNode(item_key=item_key, rate=rate)

    scale = rate / recipe.products[item_key]
    children = [
        _resolve(ing_key, ing_rate * scale, bp_map, prefer_alt, supply_boundaries)
        for ing_key, ing_rate in recipe.ingredients.items()
    ]
    return PlanNode(
        item_key=item_key,
        rate=rate,
        recipe=recipe,
        buildings=buildings_needed(item_key, rate, recipe),
        children=children,
    )


def blueprint_plan(
    target_item: str,
    target_rate: float,
    blueprints: Optional[dict[str, Blueprint]] = None,
    prefer_alt: bool = False,
) -> PlanNode:
    """
    Build a production plan using blueprints where possible, falling back to
    individual recipe buildings elsewhere.

    Parameters
    ----------
    target_item  : item to produce, e.g. 'smart-plating'
    target_rate  : desired items/min
    blueprints   : override the global BLUEPRINTS registry
    prefer_alt   : prefer alternate recipes for non-blueprint steps

    Returns
    -------
    PlanNode tree. Call .print_tree(), .blueprint_steps(), .raw_resources(), etc.
    """
    bp_map = blueprints if blueprints is not None else BLUEPRINTS
    return _resolve(target_item, target_rate, bp_map, prefer_alt)


def optimize_from_supply(
    supply_item: str,
    supply_rate: float,
    target_item: str,
    blueprints: Optional[dict[str, Blueprint]] = None,
    prefer_alt: bool = False,
) -> PlanNode:
    """
    Find the maximum target_item/min achievable from supply_rate of supply_item,
    then return the full blueprint plan for that rate.

    Works by running the plan at rate=1 to find the supply_item consumption ratio,
    then scales to the available supply.

    Parameters
    ----------
    supply_item  : the resource you have, e.g. 'iron-ingot'
    supply_rate  : how much you have per minute, e.g. 500.0
    target_item  : what you want to maximize, e.g. 'smart-plating'
    """
    bp_map = blueprints if blueprints is not None else BLUEPRINTS
    boundary = frozenset([supply_item])

    # Run at rate=1 to find how much supply_item one unit of target_item costs
    unit_plan = _resolve(target_item, 1.0, bp_map, prefer_alt, boundary)
    consumption_per_unit = unit_plan.raw_resources().get(supply_item, 0.0)

    if consumption_per_unit == 0:
        raise ValueError(
            f"{supply_item!r} is not consumed in the {target_item!r} production chain"
        )

    max_rate = supply_rate / consumption_per_unit
    return _resolve(target_item, max_rate, bp_map, prefer_alt, boundary)
