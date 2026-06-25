"""
satisfactory.py — All Satisfactory game data, importable in any notebook.

    from satisfactory import ITEMS, RECIPES, BUILDINGS, production_chain

Data is loaded from data.json and converted to rates (items/min) at import time.
All recipe quantities are in items/min, not per-cycle amounts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_DATA_PATH = Path(__file__).parent / "data.json"

_CATEGORY_TO_BUILDING = {
    "smelting1":    "smelter",
    "smelting2":    "foundry",
    "crafting1":    "constructor",
    "crafting2":    "assembler",
    "crafting3":    "manufacturer",
    "refining":     "oil-refinery",
    "blending":     "blender",
    "accelerating": "accelerator",
    "packaging":    "packager",
    "converting":   "converter",
    "encoding":     "quantum-encoder",
    "nuke-reacting":"nuclear-power-plant",
}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Item:
    key: str
    name: str
    tier: int
    stack_size: int
    is_fluid: bool
    is_resource: bool  # True = raw extractable, no recipe needed


@dataclass(frozen=True)
class Recipe:
    key: str
    name: str
    building: str                  # building key, e.g. 'assembler'
    time_sec: float
    ingredients: dict[str, float]  # item_key -> items/min
    products: dict[str, float]     # item_key -> items/min
    is_alt: bool


@dataclass(frozen=True)
class Building:
    key: str
    name: str
    power_mw: float
    somersloop_slots: int
    category: str


@dataclass(frozen=True)
class Miner:
    key: str
    name: str
    category: str   # 'mineral', 'oil', 'water'
    base_rate: float  # items/min at normal purity, 100% clock
    power_mw: float


@dataclass(frozen=True)
class Belt:
    key: str
    name: str
    rate: float  # items/min


@dataclass(frozen=True)
class Pipe:
    key: str
    name: str
    rate: float  # m3/min


@dataclass
class ProductionNode:
    """One node in a production chain tree."""
    item_key: str
    rate: float                          # items/min demanded at this node
    recipe: Optional[Recipe]             # None if this is a raw resource leaf
    buildings: float                     # fractional building count at 100% clock
    children: list[ProductionNode] = field(default_factory=list)

    @property
    def is_resource(self) -> bool:
        return self.recipe is None

    def all_nodes(self) -> list[ProductionNode]:
        """Flat list of every node in the subtree (depth-first)."""
        result: list[ProductionNode] = [self]
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

    def building_totals(self) -> dict[str, float]:
        """Total fractional building count by building key across the full subtree."""
        totals: dict[str, float] = {}
        for node in self.all_nodes():
            if node.recipe:
                b = node.recipe.building
                totals[b] = totals.get(b, 0.0) + node.buildings
        return totals

    def __repr__(self) -> str:
        r = f"{self.item_key} @ {self.rate:.2f}/min"
        if self.recipe:
            r += f" ({self.buildings:.2f}x {self.recipe.building})"
        return r


# ---------------------------------------------------------------------------
# Load + index
# ---------------------------------------------------------------------------

def _rate(qty: float, time_sec: float) -> float:
    return (qty / time_sec) * 60.0


def _build_indexes(raw: dict):
    resource_keys = {r["key_name"] for r in raw["resources"]}

    items: dict[str, Item] = {}
    for entry in raw["items"]:
        k = entry["key_name"]
        items[k] = Item(
            key=k,
            name=entry["name"],
            tier=entry.get("tier", -1),
            stack_size=entry.get("stack_size", 0),
            is_fluid=False,
            is_resource=k in resource_keys,
        )
    for entry in raw["fluids"]:
        k = entry["key_name"]
        items[k] = Item(
            key=k,
            name=entry["name"],
            tier=entry.get("tier", -1),
            stack_size=0,
            is_fluid=True,
            is_resource=k in resource_keys,
        )

    buildings: dict[str, Building] = {}
    for entry in raw["buildings"]:
        k = entry["key_name"]
        buildings[k] = Building(
            key=k,
            name=entry["name"],
            power_mw=entry.get("power", 0),
            somersloop_slots=entry.get("somersloop_slots", 0),
            category=entry.get("category", ""),
        )

    miners: dict[str, Miner] = {}
    for entry in raw["miners"]:
        k = entry["key_name"]
        miners[k] = Miner(
            key=k,
            name=entry["name"],
            category=entry.get("category", ""),
            base_rate=entry.get("base_rate", 0),
            power_mw=entry.get("power", 0),
        )

    belts = [Belt(key=b["key_name"], name=b["name"], rate=b["rate"]) for b in raw["belts"]]
    pipes = [Pipe(key=p["key_name"], name=p["name"], rate=p["rate"]) for p in raw["pipes"]]

    recipes_for: dict[str, list[Recipe]] = {}
    for entry in raw["recipes"]:
        t = entry["time"]
        is_alt = entry["name"].lower().startswith("alternate:")
        building: str = _CATEGORY_TO_BUILDING.get(entry["category"]) or entry["category"]
        ingredients = {k: _rate(q, t) for k, q in entry["ingredients"]}
        products = {k: _rate(q, t) for k, q in entry["products"]}
        recipe = Recipe(
            key=entry["key_name"],
            name=entry["name"],
            building=building,
            time_sec=t,
            ingredients=ingredients,
            products=products,
            is_alt=is_alt,
        )
        for item_key in products:
            recipes_for.setdefault(item_key, []).append(recipe)

    for lst in recipes_for.values():
        lst.sort(key=lambda r: r.is_alt)  # non-alts first

    recipes = {item_key: lst[0] for item_key, lst in recipes_for.items()}
    return items, recipes, recipes_for, buildings, miners, belts, pipes, resource_keys


with open(_DATA_PATH) as _f:
    _raw = json.load(_f)

ITEMS: dict[str, Item]
RECIPES: dict[str, Recipe]
RECIPES_FOR: dict[str, list[Recipe]]
BUILDINGS: dict[str, Building]
MINERS: dict[str, Miner]
BELTS: list[Belt]
PIPES: list[Pipe]
RESOURCES: set[str]  # raw extractable item keys

ITEMS, RECIPES, RECIPES_FOR, BUILDINGS, MINERS, BELTS, PIPES, RESOURCES = _build_indexes(_raw)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def recipe_for(item_key: str, prefer_alt: bool = False) -> Optional[Recipe]:
    """Return the primary recipe for item_key, or the first alt if prefer_alt=True."""
    candidates = RECIPES_FOR.get(item_key, [])
    if not candidates:
        return None
    if prefer_alt:
        alts = [r for r in candidates if r.is_alt]
        return alts[0] if alts else candidates[0]
    return candidates[0]


def buildings_needed(item_key: str, target_rate: float, recipe: Optional[Recipe] = None) -> float:
    """Fractional building count at 100% clock to hit target_rate items/min."""
    r = recipe or recipe_for(item_key)
    if r is None:
        return 0.0
    output_rate = r.products.get(item_key, 0.0)
    return 0.0 if output_rate == 0 else target_rate / output_rate


# ---------------------------------------------------------------------------
# Production chain — YOUR CODE GOES HERE
# ---------------------------------------------------------------------------

def production_chain(
    item_key: str,
    target_rate: float,
    prefer_alt: bool = False,
    _overrides: Optional[dict[str, Recipe]] = None,
) -> ProductionNode:
    """
    Recursively build a production tree for item_key at target_rate items/min.

    Parameters
    ----------
    item_key     : item to produce, e.g. 'rotor'
    target_rate  : desired output in items/min
    prefer_alt   : use alternate recipes where available
    _overrides   : optional {item_key: Recipe} to force specific recipes per item

    Returns
    -------
    ProductionNode — root of the full dependency tree.
    Leaf nodes (raw resources) have recipe=None and buildings=0.
    Call .raw_resources() or .building_totals() on the result for summary data.

    Algorithm
    ---------
    1. Check _overrides first, then recipe_for(item_key, prefer_alt).
    2. If no recipe → raw resource. Return leaf node (recipe=None, buildings=0, no children).
    3. Calculate buildings = buildings_needed(item_key, target_rate, recipe).
    4. For each ingredient, calculate the rate needed to sustain target_rate output:
           needed_rate = recipe.ingredients[ing_key]
                         * (target_rate / recipe.products[item_key])
       Then recurse: production_chain(ing_key, needed_rate, prefer_alt, _overrides).
    5. Return ProductionNode(item_key, target_rate, recipe, buildings, children).
    """
    overrides = _overrides or {}
    if item_key in RESOURCES and item_key not in overrides:
        return ProductionNode(item_key, target_rate, recipe=None, buildings=0.0)
    recipe = overrides.get(item_key) or recipe_for(item_key, prefer_alt)

    if recipe is None:
        return ProductionNode(item_key, target_rate, recipe=None, buildings=0.0)

    scale = target_rate / recipe.products[item_key]
    children = [
        production_chain(ing_key, ing_rate * scale, prefer_alt, overrides)
        for ing_key, ing_rate in recipe.ingredients.items()
    ]
    return ProductionNode(
        item_key=item_key,
        rate=target_rate,
        recipe=recipe,
        buildings=buildings_needed(item_key, target_rate, recipe),
        children=children,
    )
