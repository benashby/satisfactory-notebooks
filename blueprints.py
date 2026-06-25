"""
blueprints.py — Blueprint registry.

A Blueprint is a pre-built factory module with fixed I/O rates at 100% clock.
Setting an output rate in-game underclocks all rates linearly.

    from blueprints import BLUEPRINTS, Blueprint, Stage
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Stage:
    """One tier of machines inside a blueprint.

    rate_at_100 is the total output of this stage across all machines at 100% clock.
    For the final output stage, this equals blueprint.outputs[item_key].
    For intermediate stages, this is the internal throughput (e.g. rods/min inside a screw blueprint).
    """
    item_key: str
    machines: int
    rate_at_100: float
    building: str = "constructor"

    def per_machine_rate(self, clock: float) -> float:
        """Output per individual machine at the given clock fraction (0–1)."""
        return (self.rate_at_100 / self.machines) * clock


@dataclass(frozen=True)
class Blueprint:
    name: str
    inputs: dict[str, float]   # item_key -> items/min at 100% clock
    outputs: dict[str, float]  # item_key -> items/min at 100% clock
    stages: tuple[Stage, ...] = field(default_factory=tuple)

    def input_ratio(self, input_key: str, output_key: str) -> float:
        """Items of input_key consumed per item of output_key produced."""
        return self.inputs[input_key] / self.outputs[output_key]

    def clock(self, output_key: str, target_rate: float) -> float:
        """Clock fraction (0–1) needed to hit target_rate of output_key."""
        return target_rate / self.outputs[output_key]

    def stage_rates(self, output_key: str, target_rate: float) -> list[dict]:
        """Per-machine rates for every internal stage at the given target output rate.

        Returns a list of dicts with keys:
            item_key, building, machines, total_rate, per_machine_rate
        """
        c = self.clock(output_key, target_rate)
        return [
            {
                "item_key":        s.item_key,
                "building":        s.building,
                "machines":        s.machines,
                "total_rate":      s.rate_at_100 * c,
                "per_machine_rate": s.per_machine_rate(c),
            }
            for s in self.stages
        ]


# ---------------------------------------------------------------------------
# Blueprint registry — add yours here
# ---------------------------------------------------------------------------

BLUEPRINTS: dict[str, Blueprint] = {
    # key = the primary output item_key this blueprint produces

    "iron-rod": Blueprint(
        name="60 ingots to 60 rods",
        inputs={"iron-ingot": 60.0},
        outputs={"iron-rod": 60.0},
        stages=(
            Stage(item_key="iron-rod", machines=4, rate_at_100=60.0),
        ),
    ),
    "screw": Blueprint(
        name="40 ingots to 160 screws",
        inputs={"iron-ingot": 40.0},
        outputs={"screw": 160.0},
        stages=(
            # Internal chain: ingots → rods → screws
            Stage(item_key="iron-rod", machines=3, rate_at_100=40.0),
            Stage(item_key="screw",    machines=4, rate_at_100=160.0),
        ),
    ),
    "iron-plate": Blueprint(
        name="120 iron ingots to 80 iron plates",
        inputs={"iron-ingot": 120.0},
        outputs={"iron-plate": 80.0},
        stages=(
            Stage(item_key="iron-plate", machines=4, rate_at_100=80.0),
        ),
    ),
    "reinforced-iron-plate": Blueprint(
        name="90 plates + 180 screws to 15 RIP",
        inputs={"iron-plate": 90.0, "screw": 180.0},
        outputs={"reinforced-iron-plate": 15.0},
        stages=(
            Stage(item_key="reinforced-iron-plate", machines=3, rate_at_100=15.0, building="assembler"),
        ),
    ),
    "rotor": Blueprint(
        name="60 rods + 300 screws to 12 rotors",
        inputs={"iron-rod": 60.0, "screw": 300.0},
        outputs={"rotor": 12.0},
        stages=(
            Stage(item_key="rotor", machines=3, rate_at_100=12.0, building="assembler"),
        ),
    ),
    "smart-plating": Blueprint(
        name="6 RIP + 6 rotors to 6 smart plating",
        inputs={"reinforced-iron-plate": 6.0, "rotor": 6.0},
        outputs={"smart-plating": 6.0},
        stages=(
            Stage(item_key="smart-plating", machines=3, rate_at_100=6.0, building="assembler"),
        ),
    ),
}
