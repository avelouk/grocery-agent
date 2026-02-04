"""
Pydantic models for recipes and ingredients.
Used for LLM structured output and API validation.
"""
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class IngredientCategory(str, Enum):
    """Broad category for an ingredient (helps with pantry vs perishable, substitutes)."""
    PANTRY = "pantry"       # long-lasting: oil, flour, salt, canned
    DAIRY = "dairy"
    PRODUCE = "produce"
    MEAT = "meat"
    SEAFOOD = "seafood"
    SPICE = "spice"
    CONDIMENT = "condiment"
    FROZEN = "frozen"
    OTHER = "other"


class Ingredient(BaseModel):
    """A single ingredient in a recipe."""
    name: str = Field(..., description="Ingredient name as used in the recipe (e.g. 'olive oil')")
    quantity: Optional[str] = Field(None, description="Quantity if specified (e.g. '2', '1/2 cup') – from LLM")
    unit: Optional[str] = Field(None, description="Unit (e.g. 'tbsp', 'g') or qualitative ('to taste', 'pinch')")
    category: IngredientCategory = Field(
        IngredientCategory.OTHER,
        description="Category for pantry vs perishable and substitutes",
    )
    # Set when loading from DB or after computing from quantity/portions; used for display with scaling
    quantity_per_portion: Optional[float] = Field(None, description="Numeric amount per 1 portion; null for 'to taste' etc.")


class Recipe(BaseModel):
    """Structured recipe: name, portions, ingredients, instructions, optional source."""
    name: str = Field(..., description="Recipe title")
    portions: int | float = Field(4, description="Number of portions/servings the recipe is written for")
    ingredients: list[Ingredient] = Field(default_factory=list, description="List of ingredients")
    instructions: str = Field(..., description="Cooking instructions (plain text or steps)")
    source_url: Optional[str] = Field(None, description="URL of the recipe if from a link")
