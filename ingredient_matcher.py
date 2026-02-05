"""
Ingredient matching algorithm for finding the best products in a supermarket catalog.
Uses LLM for intelligent unit conversion, ingredient matching, and product selection.
"""
import math
import asyncio
import re
from dataclasses import dataclass
from typing import Optional, Any


@dataclass
class Ingredient:
    """Recipe ingredient with quantity and form."""
    name: str
    quantity: float
    unit: str
    form: Optional[str] = None  # e.g., "whole", "chopped", "powdered"
    required_quantity: Optional[float] = None  # normalized to base unit


@dataclass
class Product:
    """Supermarket product with pricing and packaging info."""
    id: str
    name: str
    ingredient_type: str  # matches ingredient.name
    form: Optional[str] = None  # matches ingredient.form
    price: float = 0.0
    package_quantity: float = 0.0
    unit: str = ""
    normalized_quantity: Optional[float] = None  # normalized to base unit
    price_per_unit: Optional[float] = None
    score: Optional[float] = None
    required_units: int = 1  # number of packages needed
    total_price: Optional[float] = None
    total_quantity: Optional[float] = None


async def convert_to_base_unit_llm(quantity: float, unit: str, ingredient_name: str, llm: Any) -> float:
    """
    Use LLM to convert quantity to base unit with context awareness.
    Handles complex cases like "3 cloves of garlic" -> grams.
    """
    prompt = f"""Convert {quantity} {unit} of {ingredient_name} to a base unit.

Rules:
- Weight units (g, kg, oz, lb, cloves, etc.) → convert to grams
- Volume units (ml, l, tsp, tbsp, cup, etc.) → convert to milliliters  
- Count units (pieces, units, etc.) → keep as count

For context-specific conversions:
- 1 clove of garlic ≈ 3g
- Consider the ingredient type for accurate conversion

Return ONLY the numeric value in the base unit (grams for weight, ml for volume, count for discrete items).

Example: "3 cloves" of "garlic" → 9.0
Example: "2 tbsp" of "oil" → 29.58
Example: "500g" of "flour" → 500.0
"""
    
    try:
        # Try different LLM invocation methods
        result = None
        if hasattr(llm, 'ainvoke'):
            # Try with message list
            try:
                from langchain_core.messages import HumanMessage
                result = await llm.ainvoke([HumanMessage(content=prompt)])
            except (ImportError, Exception):
                # Try with string directly
                result = await llm.ainvoke(prompt)
        elif hasattr(llm, 'invoke'):
            result = await asyncio.to_thread(llm.invoke, prompt)
        elif hasattr(llm, 'predict'):
            result = await asyncio.to_thread(llm.predict, prompt)
        
        if result is None:
            raise ValueError(f"LLM conversion failed for {quantity} {unit} of {ingredient_name}")
        
        # Extract content
        if hasattr(result, 'content'):
            content = result.content
        elif isinstance(result, list) and len(result) > 0:
            content = result[0].content if hasattr(result[0], 'content') else str(result[0])
        else:
            content = str(result)
        
        # Extract numeric value
        numbers = re.findall(r'\d+\.?\d*', content)
        if numbers:
            return float(numbers[0])
        else:
            raise ValueError(f"Could not extract numeric value from LLM response: {content}")
    except Exception as e:
        raise ValueError(f"LLM conversion failed for {quantity} {unit} of {ingredient_name}: {e}")


async def normalize_ingredient_llm(ingredient: Ingredient, llm: Any) -> Ingredient:
    """Step 1: Normalize ingredient quantity to base unit using LLM."""
    ingredient.required_quantity = await convert_to_base_unit_llm(
        ingredient.quantity, 
        ingredient.unit, 
        ingredient.name,
        llm
    )
    return ingredient




async def find_candidates_llm(ingredient: Ingredient, catalog: list[Product], llm: Any) -> list[Product]:
    """
    Step 2: Use LLM to find products that match ingredient (fuzzy matching, synonyms).
    """
    # Prepare product list for LLM (limit to avoid token limits)
    product_list = "\n".join([
        f"ID: {p.id}, Name: {p.name}, Type: {p.ingredient_type}, Form: {p.form or 'N/A'}"
        for p in catalog[:50]  # Limit to first 50 products
    ])
    
    prompt = f"""Find products that match this recipe ingredient:
- Ingredient name: {ingredient.name}
- Form: {ingredient.form or 'any form'}
- Required quantity: {ingredient.quantity} {ingredient.unit}

Available products:
{product_list}

Consider:
- Exact name matches
- Synonyms (e.g., "papas" = "potatoes", "ajo" = "garlic")
- Similar names (fuzzy matching)
- Form compatibility: Products must match the specified form. If form is specified, only include products with matching form.

Return ONLY a comma-separated list of product IDs that match this ingredient.
"""
    
    try:
        # Try different LLM invocation methods
        result = None
        if hasattr(llm, 'ainvoke'):
            try:
                from langchain_core.messages import HumanMessage
                result = await llm.ainvoke([HumanMessage(content=prompt)])
            except (ImportError, Exception):
                result = await llm.ainvoke(prompt)
        elif hasattr(llm, 'invoke'):
            result = await asyncio.to_thread(llm.invoke, prompt)
        elif hasattr(llm, 'predict'):
            result = await asyncio.to_thread(llm.predict, prompt)
        
        if result is None:
            return find_candidates(ingredient, catalog)
        
        # Extract content
        if hasattr(result, 'content'):
            content = result.content
        elif isinstance(result, list) and len(result) > 0:
            content = result[0].content if hasattr(result[0], 'content') else str(result[0])
        else:
            content = str(result)
        
        # Extract product IDs from response
        matching_ids = []
        for product in catalog:
            # Check if product ID or name appears in LLM response
            if product.id in content or product.name.lower() in content.lower() or product.ingredient_type.lower() in content.lower():
                matching_ids.append(product.id)
        
        # If LLM found matches, return them
        if matching_ids:
            return [p for p in catalog if p.id in matching_ids]
    except Exception:
        pass
    
    # Fallback to exact matching
    return find_candidates(ingredient, catalog)


def find_candidates(ingredient: Ingredient, catalog: list[Product]) -> list[Product]:
    """
    Step 2: Find products that match ingredient name AND form (fallback).
    Only products that match both are allowed.
    """
    candidates = []
    for product in catalog:
        # Match ingredient name (case-insensitive)
        if product.ingredient_type.lower() == ingredient.name.lower():
            # Match form if both are specified
            if ingredient.form is None or product.form is None:
                # If either is None, consider it a match (no form constraint)
                candidates.append(product)
            elif product.form.lower() == ingredient.form.lower():
                candidates.append(product)
    return candidates


async def normalize_product_data_llm(product: Product, llm: Any) -> Product:
    """
    Step 3: Normalize product data for fair price comparison using LLM.
    Convert package quantity to base unit and calculate price per unit.
    """
    # Use LLM to convert product package quantity (product name as context)
    product.normalized_quantity = await convert_to_base_unit_llm(
        product.package_quantity,
        product.unit,
        product.name,
        llm
    )
    if product.normalized_quantity > 0:
        product.price_per_unit = product.price / product.normalized_quantity
    else:
        product.price_per_unit = float('inf')
    return product


async def filter_by_quantity(ingredient: Ingredient, candidates: list[Product], llm: Any) -> list[Product]:
    """
    Step 4: Filter products that can satisfy the recipe quantity.
    Discard products that cannot satisfy the required quantity.
    """
    valid_products = []
    for product in candidates:
        # Products should already be normalized, but ensure they are
        if product.normalized_quantity is None:
            product = await normalize_product_data_llm(product, llm)
        if product.normalized_quantity >= ingredient.required_quantity:
            valid_products.append(product)
    return valid_products


def apply_overbuy_penalty(ingredient: Ingredient, valid_products: list[Product]) -> list[Product]:
    """
    Step 5: Calculate overbuy penalty.
    Avoid absurdly large packages (overbuy ratio > 3 gets 30% penalty).
    """
    for product in valid_products:
        overbuy_ratio = product.normalized_quantity / ingredient.required_quantity
        
        if overbuy_ratio > 3:
            # Apply 30% penalty for excessive overbuy
            product.score = product.price_per_unit * 1.3
        else:
            # No penalty for reasonable overbuy
            product.score = product.price_per_unit
    
    return valid_products


async def resolve_multi_package(ingredient: Ingredient, candidates: list[Product], llm: Any) -> list[Product]:
    """
    Step 6: Multi-package resolution.
    If no single product covers the quantity, allow multiples.
    """
    valid_products = []
    
    for product in candidates:
        product = await normalize_product_data_llm(product, llm)
        
        # Calculate how many units we need
        required_units = math.ceil(ingredient.required_quantity / product.normalized_quantity)
        
        product.required_units = required_units
        product.total_price = required_units * product.price
        product.total_quantity = required_units * product.normalized_quantity
        
        # Recalculate price per unit based on total
        if product.total_quantity > 0:
            product.price_per_unit = product.total_price / product.total_quantity
        
        valid_products.append(product)
    
    return valid_products


def select_cheapest(valid_products: list[Product]) -> Optional[Product]:
    """
    Step 7: Select cheapest valid product.
    Price dominates once constraints are met.
    """
    if not valid_products:
        return None
    
    # Find product with minimum score (price per unit)
    best_product = min(valid_products, key=lambda p: p.score if p.score is not None else float('inf'))
    return best_product


async def find_best_product_llm(ingredient: Ingredient, catalog: list[Product], llm: Any) -> Optional[Product]:
    """
    Full algorithm flow with LLM: find the best product for an ingredient.
    
    Returns the best matching product or None if no match found.
    """
    # Step 1: Normalize ingredient using LLM
    ingredient = await normalize_ingredient_llm(ingredient, llm)
    
    # Step 2: Find candidates using LLM (fuzzy matching, synonyms)
    candidates = await find_candidates_llm(ingredient, catalog, llm)
    if not candidates:
        return None
    
    # Step 3: Normalize all candidate data using LLM
    candidates = [await normalize_product_data_llm(p, llm) for p in candidates]
    
    # Step 4: Filter by quantity coverage
    valid_products = await filter_by_quantity(ingredient, candidates, llm)
    
    # Step 5: Apply overbuy penalty
    if valid_products:
        valid_products = apply_overbuy_penalty(ingredient, valid_products)
    else:
        # Step 6: Multi-package resolution if no single product works
        valid_products = await resolve_multi_package(ingredient, candidates, llm)
        valid_products = apply_overbuy_penalty(ingredient, valid_products)
    
    # Step 7: Select cheapest
    best_product = select_cheapest(valid_products)
    
    return best_product


async def build_cart_llm(recipe_ingredients: list[Ingredient], catalog: list[Product], llm: Any) -> list[dict]:
    """
    Build shopping cart from recipe ingredients using LLM for intelligent matching.
    
    Returns list of cart items with ingredient, product_id, and quantity.
    """
    cart = []
    
    for ingredient in recipe_ingredients:
        best_product = await find_best_product_llm(ingredient, catalog, llm)
        
        if best_product:
            cart.append({
                "ingredient": ingredient.name,
                "product_id": best_product.id,
                "product_name": best_product.name,
                "quantity": best_product.required_units,
                "price": best_product.total_price if best_product.total_price else best_product.price,
            })
    
    return cart

