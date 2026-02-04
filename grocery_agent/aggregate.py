"""
Aggregate recipe ingredients into a normalized, flattened grocery list.
Used by the web checklist and by get_grocery_list() for the jumbo agent interface.
"""
from grocery_agent.ingredient_normalizer import (
    normalize_name_for_display,
    normalize_name_for_key,
    normalize_unit_for_key,
)
from grocery_agent.models import Recipe


def _format_amount(total_quantity: float | None, unit: str | None) -> str:
    """Format total quantity + unit for display (e.g. '3 cups', 'to taste')."""
    if total_quantity is None:
        return (unit or "to taste").strip()
    if total_quantity == int(total_quantity):
        num_str = str(int(total_quantity))
    else:
        num_str = f"{total_quantity:.2g}".rstrip("0").rstrip(".")
    return f"{num_str} {unit or ''}".strip()


def flat_ingredients(recipes: list[Recipe]) -> list[dict]:
    """Build a flat list of ingredient rows (one per recipe ingredient) with portions applied."""
    flat = []
    for recipe in recipes:
        portions = recipe.portions or 4
        if portions <= 0:
            portions = 4
        for ing in recipe.ingredients:
            qpp = ing.quantity_per_portion
            total = (qpp * portions) if qpp is not None else None
            form_val = getattr(ing.form, "value", str(ing.form))
            flat.append({
                "name": (ing.name or "").strip(),
                "unit": (ing.unit or "").strip() or "",
                "form": form_val if isinstance(form_val, str) else getattr(form_val, "value", "fresh"),
                "total": total,
                "pantry_item": getattr(ing, "pantry_item", False),
                "optional": getattr(ing, "optional", False),
                "category": ing.category.value,
            })
    return flat


def merge_flat_ingredients(
    flat: list[dict],
    canonical_list: list[dict] | None,
) -> list[dict]:
    """
    Merge flat ingredient rows by (canonical name, form) only. Same ingredient with different
    units (e.g. "3 medium" and "2 lb" of potato) become one line: "3 medium + 2 lb".
    Same unit is summed (e.g. 2 tbsp + 1 tbsp -> 3 tbsp). The grocery agent interprets the combined string.
    """
    def name_key_for(i: int) -> str:
        row = flat[i]
        if canonical_list and i < len(canonical_list):
            c = canonical_list[i]
            return (c.get("name") or "").strip().lower() or normalize_name_for_key(row["name"])
        return normalize_name_for_key(row["name"])

    # (name_key, form) -> (list of (total, unit), all_pantry, any_optional, category)
    merged: dict[tuple, tuple[list[tuple[float | None, str]], bool, bool, str]] = {}
    for i, row in enumerate(flat):
        k = (name_key_for(i), row["form"])
        total = row["total"]
        disp_unit = (row["unit"] or "").strip() or ""
        if canonical_list and i < len(canonical_list):
            disp_unit = (canonical_list[i].get("unit") or "").strip().lower() or disp_unit
        disp_unit = normalize_unit_for_key(disp_unit) or disp_unit
        if k not in merged:
            merged[k] = ([(total, disp_unit)], row["pantry_item"], row["optional"], row["category"])
        else:
            amounts, all_pantry, any_opt, cat = merged[k]
            unit_norm = normalize_unit_for_key(disp_unit)
            found = False
            for j, (t, u) in enumerate(amounts):
                if normalize_unit_for_key(u) == unit_norm:
                    if t is not None and total is not None:
                        amounts[j] = (t + total, u)
                    elif total is not None:
                        amounts[j] = (total, u)
                    found = True
                    break
            if not found:
                amounts.append((total, disp_unit))
            merged[k] = (amounts, all_pantry and row["pantry_item"], any_opt or row["optional"], cat)
    out = []
    for idx, ((name_key, form_val), (amounts, pantry_item, optional, category)) in enumerate(sorted(merged.items(), key=lambda x: (x[0][1], x[0][0]))):
        display_name = normalize_name_for_display(name_key)
        amount_str = " + ".join(_format_amount(t, u) for t, u in amounts)
        out.append({
            "index": idx,
            "name": display_name,
            "unit": None,
            "form": form_val,
            "amount_str": amount_str,
            "pantry_item": pantry_item,
            "optional": optional,
            "category": category,
        })
    return out
