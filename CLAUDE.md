# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Jupyter notebook-based factory planner for the game Satisfactory. Notebooks calculate production chain rates, building counts, and belt/pipe throughput for each manufactured part, using shared Python modules for game data and blueprint definitions.

## Commands

All commands use `just`:

```bash
just setup      # One-time: create .venv and install full Python stack (uv)
just start      # Start JupyterLab in background on port 8888 (no token auth)
just stop       # Stop JupyterLab
just status     # Show server status and URL
just run [notebook]    # Execute notebook in-place and trust it (default: index.ipynb)
just render [notebook] # Render to HTML (default: index.ipynb)
just view [notebook]   # Render then open in browser
```

Always use `just run` (not the Jupyter UI execute button) when executing notebooks in scripts — it clears `PYTHONPATH` first to prevent Nix-shell interference with the venv.

## Architecture

### Shared modules (imported by notebooks)

**`satisfactory.py`** — Game data layer. Loads `data.json` at import time and exposes typed, indexed collections:
- `ITEMS: dict[str, Item]` — all items and fluids
- `RECIPES: dict[str, Recipe]` — primary recipe per item (non-alt preferred)
- `RECIPES_FOR: dict[str, list[Recipe]]` — all recipes per item (non-alts first)
- `BUILDINGS`, `MINERS`, `BELTS`, `PIPES`, `RESOURCES`
- All recipe quantities are pre-converted to **items/min** (not per-cycle amounts)

**`blueprints.py`** — Factory blueprint registry. A `Blueprint` models a pre-built factory module with fixed I/O rates at 100% clock; underclocking scales all rates linearly. `Stage` describes one tier of machines inside a blueprint (including internal intermediate stages). `BLUEPRINTS` dict maps output item key → `Blueprint`.

**`data.json`** — Raw game data (items, fluids, recipes, buildings, miners, belts, pipes, resources). Source of truth for all game constants.

### Notebook structure

**`index.ipynb`** — Top-level ingot budget: divides the total iron ingot supply across all Phase 1 consumers (rods, plates, screws).

**`parts/phase-1/*.ipynb`** — One notebook per production chain (e.g. `smart-plating.ipynb`, `rotors.ipynb`). Each notebook is either a **Producer** (final output pushed to storage) or **Consumer** (pulls from upstream storage). Supply rates from upstream notebooks are copied as constants at the top of each consumer notebook — they are not dynamically linked.

**`reinforced_iron_plate.ipynb`** — Legacy root-level notebook (predates the `parts/` structure).

### Patterns used in notebooks

Each parts notebook:
1. Adds `../..` to `sys.path` to import `satisfactory` and `blueprints`
2. Declares supply constants sourced from upstream notebooks
3. Computes derived rates using `Blueprint.input_ratio()` and `Blueprint.clock()`
4. Asserts balance within a tolerance (`TOL = 0.5`) to catch rounding drift
5. Renders a Plotly chart via `display(HTML(...))` — this is required because JupyterLab without the plotly extension needs the full HTML export path

### Python environment

The `.venv` owns the entire Python stack; Nix provides no Python. This is intentional — a Nix-provided Python exports `PYTHONPATH` over its store site-packages, which JupyterLab kernels inherit, shadowing pip-installed packages (notably Plotly). The `just run` and `just render` recipes call `env -u PYTHONPATH` before invoking Jupyter to prevent this even if a Nix devshell is active.
