"""
Interface for the jumbo agent: produce the normalized, flattened grocery list.

Output format (list of items, one per ingredient line):
  - name: str          – canonical display name (e.g. "Potato", "Olive Oil")
  - amount_str: str    – combined amount for the agent to interpret (e.g. "3 medium + 2 lb", "2 tbsp")
  - form: str          – fresh | canned | frozen | dried | liquid (for search: "frozen peas")
  - category: str      – pantry | dairy | produce | meat | seafood | spice | condiment | frozen | other
  - optional: bool     – True if ingredient is optional
  - pantry_item: bool  – True if typically kept stocked (agent may skip or restock)

Usage from jumbo agent:
  from grocery_agent.grocery_list import get_grocery_list
  items = await get_grocery_list(recipe_ids=[1, 2], portions_override={1: 4, 2: 6})
  for item in items:
      # e.g. search jumbo.cl for item["amount_str"] + " " + item["name"] + " " + item["form"]
      ...

CLI (JSON to stdout):
  uv run python -m grocery_agent.grocery_list 1 2 --portions 1=4 2=6
  uv run python -m grocery_agent.grocery_list 1 2 --selected 0 1 3   # only those indices
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from grocery_agent.aggregate import flat_ingredients, merge_flat_ingredients
from grocery_agent.db import get_connection, recipe_from_row
from grocery_agent.ingredient_normalizer import normalize_ingredients_with_llm

# Path where the web app writes the list and run_jumbo.py reads it (single source of truth)
GROCERY_LIST_PATH = Path(__file__).resolve().parent.parent / "data" / "grocery_list.json"


def write_grocery_list(items: list[dict[str, Any]], path: Path | None = None) -> None:
    """Write the grocery list to a JSON file for the jumbo bot to read."""
    p = path or GROCERY_LIST_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"items": items}, indent=2), encoding="utf-8")


def load_grocery_list(path: Path | None = None) -> list[dict[str, Any]] | None:
    """Load the grocery list from the JSON file. Returns None if file missing or invalid."""
    p = path or GROCERY_LIST_PATH
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("items") if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


async def get_grocery_list(
    recipe_ids: list[int],
    portions_override: dict[int, int] | None = None,
    selected_indices: list[int] | None = None,
) -> list[dict[str, Any]]:
    """
    Build the normalized, flattened grocery list for the jumbo agent.

    - recipe_ids: list of recipe IDs from the DB.
    - portions_override: optional {recipe_id: portions} (default: recipe's stored portions).
    - selected_indices: optional list of checklist indices to include (e.g. user checked those).
      If None, all merged items are returned.

    Returns list of dicts with keys: name, amount_str, form, category, optional, pantry_item.
    """
    portions_override = portions_override or {}
    conn = get_connection()
    try:
        recipes = []
        for rid in recipe_ids:
            r = recipe_from_row(conn, rid)
            if r:
                if rid in portions_override:
                    r.portions = portions_override[rid]
                recipes.append(r)
    finally:
        conn.close()
    if not recipes:
        return []
    flat = flat_ingredients(recipes)
    canonical_list = await normalize_ingredients_with_llm(flat)
    merged = merge_flat_ingredients(flat, canonical_list)
    # When checklist is used: include only items that were checked (unchecked are omitted).
    if selected_indices is not None:
        selected_set = set(selected_indices)
        merged = [m for m in merged if m["index"] in selected_set]
        for i, m in enumerate(merged):
            m["index"] = i
    # Output schema for jumbo agent (drop internal "index" if you want; keeping it for ordering)
    return [
        {
            "name": m["name"],
            "amount_str": m["amount_str"],
            "form": m["form"],
            "category": m["category"],
            "optional": m["optional"],
            "pantry_item": m["pantry_item"],
        }
        for m in merged
    ]


def get_grocery_list_sync(
    recipe_ids: list[int],
    portions_override: dict[int, int] | None = None,
    selected_indices: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Synchronous wrapper: runs get_grocery_list in the current or a new event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(get_grocery_list(recipe_ids, portions_override, selected_indices))
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        future = pool.submit(
            asyncio.run,
            get_grocery_list(recipe_ids, portions_override, selected_indices),
        )
        return future.result()


def _parse_portions(s: str) -> dict[int, int]:
    out = {}
    for part in s.replace(",", " ").split():
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            try:
                out[int(k.strip())] = max(1, int(v.strip()))
            except ValueError:
                pass
    return out


def main() -> None:
    """CLI: recipe IDs as positional args, optional --portions 1=4 2=6, optional --selected 0 1 3."""
    args = list(sys.argv[1:])
    portions_override: dict[int, int] = {}
    selected_indices: list[int] | None = None
    if "--portions" in args:
        i = args.index("--portions")
        args.pop(i)
        if i < len(args):
            portions_override = _parse_portions(args.pop(i))
    if "--selected" in args:
        i = args.index("--selected")
        args.pop(i)
        selected_indices = []
        while i < len(args) and args[i].isdigit():
            selected_indices.append(int(args.pop(i)))
    recipe_ids = []
    for a in args:
        try:
            recipe_ids.append(int(a))
        except ValueError:
            break
    if not recipe_ids:
        print("Usage: python -m grocery_agent.grocery_list <recipe_id> [recipe_id ...] [--portions 1=4 2=6] [--selected 0 1 3]", file=sys.stderr)
        sys.exit(1)
    items = asyncio.run(get_grocery_list(recipe_ids, portions_override or None, selected_indices))
    print(json.dumps(items, indent=2))


if __name__ == "__main__":
    main()
