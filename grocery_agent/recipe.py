"""
Recipe parsing: one LLM call to turn recipe text into a structured Recipe.
"""
from browser_use.llm.messages import SystemMessage, UserMessage

from grocery_agent.llm import get_llm
from grocery_agent.models import Recipe

SYSTEM_PROMPT = """You extract a recipe from the given text and return it as a structured Recipe.

Rules:
- name: The recipe title.
- portions: The number of portions/servings the recipe is written for (integer or decimal, e.g. 4 or 6). If unclear, use 4.
- ingredients: List each ingredient once. Do not duplicate the same ingredient with different "(for X)" labels.
  - name: Use ONLY the ingredient name (e.g. "salt", "butter", "chicken breast"). Do NOT include "(for marinade)", "(for mashed potatoes)", "(divided)", or any step or use description. If the recipe uses "salt (for marinade)" and "salt (for potatoes)", output a single "salt" entry and combine or use the main quantity.
  - quantity: A single number or fraction only (e.g. "2", "1/2", "1 1/2", "70"). For "to taste", "pinch", "some" leave quantity null/empty.
  - unit: A single unit only: standard (cups, tbsp, g, ml, etc.) or qualitative ("to taste", "pinch"). Do NOT put numbers or extra text in unit (e.g. use quantity=70, unit="g" not unit="tbsp (70)" or "5 tbsp").
  - category: One of pantry, dairy, produce, meat, seafood, spice, condiment, frozen, other.
  - optional: Set true if the recipe says the ingredient is optional (e.g. "optional: parsley", "garnish (optional)", "or omit").
  - pantry_item: Set true for things people typically keep stocked (dry pasta, rice, oil, flour, spices, canned tomatoes, salt, sugar). Set false for things usually bought weekly (fresh meat, fresh produce, dairy, fresh herbs).
  - form: How the recipe specifies the ingredient – one of: fresh, canned, frozen, dried, liquid. Use "canned" for canned beans/tomatoes, "frozen" for frozen peas/corn, "dried" for dried pasta/herbs/lentils, "liquid" for oil/vinegar, "fresh" for fresh produce/meat/dairy unless the recipe says otherwise.
- instructions: Full cooking instructions as plain text.
- source_url: Leave null unless the text explicitly states a URL or you are given a URL."""


async def parse_recipe(text: str) -> Recipe:
    """Turn recipe text into a structured Recipe via one LLM call (structured output)."""
    if not text or not text.strip():
        raise ValueError("Recipe text is empty")
    llm = get_llm()
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        UserMessage(content=text.strip()),
    ]
    result = await llm.ainvoke(messages, output_format=Recipe)
    return result.completion
