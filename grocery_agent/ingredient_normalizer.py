"""
Normalize ingredient names and units so the grocery list merges duplicates.
Used only at aggregation time (checklist); DB stays as ingested.

Two modes:
- Static: CANONICAL_INGREDIENT_NAMES + UNIT_ALIASES (fallback when LLM not used or fails).
- LLM: one call per checklist to canonicalize all ingredient names (handles any food).
"""

import logging

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static maps (fallback when LLM is not used or fails)
# ---------------------------------------------------------------------------

# Variant (lowercase) -> canonical name (lowercase, for merge key). Display = title-case of canonical.
CANONICAL_INGREDIENT_NAMES: dict[str, str] = {
    # Garlic
    "garlic": "garlic",
    "garlic clove": "garlic",
    "garlic cloves": "garlic",
    "clove garlic": "garlic",
    "cloves garlic": "garlic",
    # Salt
    "salt": "salt",
    "sea salt": "salt",
    "kosher salt": "salt",
    "table salt": "salt",
    "fine salt": "salt",
    "coarse salt": "salt",
    # Oil
    "olive oil": "olive oil",
    "extra virgin olive oil": "olive oil",
    "evoo": "olive oil",
    "vegetable oil": "vegetable oil",
    "cooking oil": "vegetable oil",
    # Pepper
    "black pepper": "black pepper",
    "ground black pepper": "black pepper",
    "pepper": "black pepper",
    "freshly ground black pepper": "black pepper",
    # Onion
    "onion": "onion",
    "onions": "onion",
    "yellow onion": "onion",
    "white onion": "onion",
    "red onion": "onion",
    # Butter
    "butter": "butter",
    "unsalted butter": "butter",
    "salted butter": "butter",
    # Common others
    "all-purpose flour": "flour",
    "plain flour": "flour",
    "flour": "flour",
    "sugar": "sugar",
    "granulated sugar": "sugar",
    "white sugar": "sugar",
    "brown sugar": "brown sugar",
    "eggs": "egg",
    "egg": "egg",
    "large egg": "egg",
    "large eggs": "egg",
    "milk": "milk",
    "whole milk": "milk",
    "water": "water",
    "lemon juice": "lemon juice",
    "fresh lemon juice": "lemon juice",
    "lime juice": "lime juice",
    "soy sauce": "soy sauce",
    "tomato paste": "tomato paste",
    "canned tomatoes": "canned tomatoes",
    "diced tomatoes": "canned tomatoes",
    "crushed tomatoes": "canned tomatoes",
    "parmesan": "parmesan",
    "parmesan cheese": "parmesan",
    "parmigiano-reggiano": "parmesan",
    "parsley": "parsley",
    "fresh parsley": "parsley",
    "cilantro": "cilantro",
    "fresh cilantro": "cilantro",
    "coriander": "cilantro",
    "fresh coriander": "cilantro",
}

# Unit alias (lowercase) -> canonical unit for merge key. Different units (tbsp vs cup) stay separate.
UNIT_ALIASES: dict[str, str] = {
    "tbsp": "tbsp",
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "tb": "tbsp",
    "tsp": "tsp",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "cup": "cup",
    "cups": "cup",
    "g": "g",
    "gram": "g",
    "grams": "g",
    "kg": "kg",
    "ml": "ml",
    "milliliter": "ml",
    "milliliters": "ml",
    "l": "l",
    "liter": "l",
    "liters": "l",
    "oz": "oz",
    "ounce": "oz",
    "ounces": "oz",
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "pinch": "pinch",
    "pinches": "pinch",
    "to taste": "to taste",
    "": "",
}


def normalize_name_for_key(raw: str) -> str:
    """Return lowercase canonical name for merge key. Unknown names pass through lowercased."""
    s = (raw or "").strip().lower()
    return CANONICAL_INGREDIENT_NAMES.get(s, s)


def normalize_name_for_display(normalized_key: str) -> str:
    """Return a display name (title-case) from the merge-key name."""
    if not normalized_key:
        return ""
    return normalized_key.replace("-", " ").title()


def normalize_unit_for_key(raw: str | None) -> str:
    """Return canonical unit for merge key. Unknown units pass through lowercased."""
    s = (raw or "").strip().lower()
    return UNIT_ALIASES.get(s, s)


# ---------------------------------------------------------------------------
# LLM-based normalization (one call per grocery list)
# ---------------------------------------------------------------------------

class CanonicalIngredient(BaseModel):
    """One canonical (name, unit) for the grocery list merge."""
    name: str = Field(..., description="Short canonical name, lowercase (e.g. garlic, olive oil)")
    unit: str = Field(..., description="Canonical unit (e.g. tbsp, cup, g, to taste)")


class CanonicalIngredientList(BaseModel):
    """List of canonical ingredients in the same order as the input list."""
    ingredients: list[CanonicalIngredient] = Field(..., description="Same length and order as the input list")


NORMALIZE_SYSTEM_PROMPT = """You normalize ingredient names for a grocery list so duplicates merge.

Rules:
- Output one canonical (name, unit) per input line, in the SAME ORDER.
- Use short, standard names. Same ingredient must get the same name (e.g. "garlic clove", "garlic cloves", "2 cloves garlic" -> name "garlic"; "sea salt", "kosher salt", "salt" -> "salt"; "extra virgin olive oil", "olive oil" -> "olive oil").
- Use standard units: tbsp, tsp, cup, g, ml, oz, lb, pinch, to taste, or empty string if no unit.
- Keep the unit meaning: if input is "2 tbsp" output unit "tbsp"; if "to taste" output "to taste"."""


async def normalize_ingredients_with_llm(flat_list: list[dict]) -> list[dict]:
    """
    Call the LLM to get canonical (name, unit) for each ingredient. One API call per checklist.
    flat_list: list of dicts with at least "name", "unit" (and optionally "form").
    Returns list of {"name": str, "unit": str} in the same order. On failure returns empty list
    (caller should fall back to static normalizer).

    Uses get_generic_llm() (Google/Gemini) so structured output is supported.
    On failure (no GOOGLE_API_KEY or API error) returns [] and caller uses static normalizer.
    """
    if not flat_list:
        return []
    try:
        from browser_use.llm.messages import SystemMessage, UserMessage
        from grocery_agent.llm import get_generic_llm

        llm = get_generic_llm()
        lines = []
        for row in flat_list:
            name = (row.get("name") or "").strip()
            unit = (row.get("unit") or "").strip() or "(no unit)"
            lines.append(f"- {name} | {unit}")
        user_content = "Normalize these ingredients (one per line). Output the list in the SAME ORDER.\n\n" + "\n".join(lines)

        messages = [
            SystemMessage(content=NORMALIZE_SYSTEM_PROMPT),
            UserMessage(content=user_content),
        ]
        result = await llm.ainvoke(messages, output_format=CanonicalIngredientList)
        out = result.completion
        if not out or not getattr(out, "ingredients", None):
            logger.warning("LLM ingredient normalization failed: empty or missing ingredients in response")
            return []
        canonical = out.ingredients
        if len(canonical) != len(flat_list):
            logger.warning(
                "LLM ingredient normalization failed: response length %s != input length %s",
                len(canonical),
                len(flat_list),
            )
            return []
        return [{"name": (c.name or "").strip().lower(), "unit": (c.unit or "").strip().lower() or ""} for c in canonical]
    except Exception as e:
        logger.warning("LLM ingredient normalization failed: %s", e, exc_info=True)
        return []
