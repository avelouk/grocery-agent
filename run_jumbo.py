"""
Browser-Use agent: jumbo.cl, find ingredients and add to cart using smart matching.
No vision (use_vision=False) for minimal tokens.
If logged out, logs in using JUMBO_EMAIL and JUMBO_PASSWORD from .env.

LLM: set one in .env — BROWSER_USE_API_KEY (cloud.browser-use.com) or GOOGLE_API_KEY (Google AI Studio).
Browser-Use is used if both are set.
"""
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

from browser_use import Agent, Browser, ChatBrowserUse, ChatGoogle
from ingredient_matcher import Ingredient, Product, build_cart_llm
from pydantic import BaseModel
from typing import Optional

load_dotenv()

SITE = "https://www.jumbo.cl"
EMAIL = os.environ.get("JUMBO_EMAIL", "")
PASSWORD = os.environ.get("JUMBO_PASSWORD", "")

# Recipe ingredients - customize this list
RECIPE_INGREDIENTS = [
    Ingredient(name="papas", quantity=500, unit="g", form="fresco"),  # 500g fresh/raw potatoes (not frozen or processed)
    # Add more ingredients as needed:
    # Ingredient(name="ajo", quantity=3, unit="cloves", form=None),
    # Ingredient(name="aceite", quantity=2, unit="tbsp", form=None),
]


def get_llm():
    if os.environ.get("BROWSER_USE_API_KEY"):
        return ChatBrowserUse()
    if os.environ.get("GOOGLE_API_KEY"):
        # Default: gemini-flash-latest (works but has 20 req/day free tier limit)
        # You can override with GEMINI_MODEL env var if you have access to other models
        # Note: Model names depend on what's available in your Google AI Studio account
        model = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
        return ChatGoogle(model=model)
    print("Set BROWSER_USE_API_KEY or GOOGLE_API_KEY in .env", file=sys.stderr)
    sys.exit(1)


def get_browser_executable():
    """Get browser executable path from env var or auto-detect Ungoogled Chromium."""
    # Check environment variable first
    env_path = os.environ.get("BROWSER_EXECUTABLE_PATH")
    if env_path and Path(env_path).exists():
        return env_path
    
    # Auto-detect Ungoogled Chromium at common macOS location
    default_path = Path("/Applications/Chromium.app/Contents/MacOS/Chromium")
    if default_path.exists():
        return str(default_path)
    
    # Return None to use browser-use default
    return None


class ProductInfo(BaseModel):
    """Structured product information extracted from the page."""
    id: str
    name: str
    price: float
    package_quantity: float
    unit: str
    form: Optional[str] = None


class ProductList(BaseModel):
    """List of products extracted from search results."""
    products: list[ProductInfo]


async def extract_product_catalog(browser: Browser, ingredients: list[Ingredient], llm) -> list[Product]:
    """
    Extract product catalog from the website for given ingredients.
    Uses browser-use's extract_content to get structured product data.
    """
    catalog = []
    
    # Get the current page from the browser
    pages = await browser.get_pages()
    if not pages:
        return catalog
    
    page = pages[0]
    
    # For each ingredient, search and extract products
    for ingredient in ingredients:
        # First, search for the ingredient
        search_task = f"""Search for "{ingredient.name}" on the website. 
        Make sure you're on the search results page showing multiple products."""
        
        search_agent = Agent(
            task=search_task,
            llm=llm,
            browser=browser,
            use_vision=False,
        )
        await search_agent.run(max_steps=10)
        
        # Extract product information from the current page
        try:
            extraction_prompt = f"""Extract all product information from the current page for "{ingredient.name}".
            For each product, extract: product ID (or SKU), name, price, package quantity, unit (g, kg, ml, l, units, etc.), and form if specified.
            Return a list of all available products."""
            
            product_list = await page.extract_content(
                extraction_prompt,
                ProductList,
                llm=llm
            )
            
            # Convert extracted products to Product objects
            for p in product_list.products:
                catalog.append(Product(
                    id=p.id,
                    name=p.name,
                    ingredient_type=ingredient.name,
                    form=p.form,
                    price=p.price,
                    package_quantity=p.package_quantity,
                    unit=p.unit,
                ))
        except Exception as e:
            # If extraction fails, continue without this ingredient's products
            print(f"Warning: Could not extract products for {ingredient.name}: {e}", file=sys.stderr)
            continue
        
    return catalog


async def add_products_to_cart(browser: Browser, cart_items: list[dict], llm):
    """Add selected products to cart using the browser agent."""
    for item in cart_items:
        task = f"""Find and add product "{item['product_name']}" (ID: {item['product_id']}) to cart. 
        Add {item['quantity']} unit(s) of this product. 
        If you need to search for it, search by name or ID."""
        
        agent = Agent(
            task=task,
            llm=llm,
            browser=browser,
            use_vision=False,
        )
        await agent.run(max_steps=10)


async def main():
    llm = get_llm()
    browser_kwargs = {
        "headless": False,
        "keep_alive": True,
    }
    executable_path = get_browser_executable()
    if executable_path:
        browser_kwargs["executable_path"] = executable_path
    
    browser = Browser(**browser_kwargs)
    await browser.start()
    
    try:
        # Login and navigate
        login_task = f"""Go to {SITE}.
        If the site shows you are logged out or asks you to sign in, log in first: 
        use email "{EMAIL}" and password "{PASSWORD}". Then continue."""
        
        agent = Agent(
            task=login_task,
            llm=llm,
            browser=browser,
            use_vision=False,
        )
        await agent.run(max_steps=10)
        
        # Extract product catalog for all ingredients
        catalog = await extract_product_catalog(browser, RECIPE_INGREDIENTS, llm)
        
        # If catalog is empty, fall back to simple agent-based search
        if not catalog:
            # Fallback: use agent to find and add products directly
            for ingredient in RECIPE_INGREDIENTS:
                form_instruction = ""
                if ingredient.form:
                    form_instruction = f" IMPORTANT: Only select products with form '{ingredient.form}'. Exclude products that don't match this form requirement."
                
                task = f"""Find "{ingredient.name}" ({ingredient.quantity} {ingredient.unit}) on the website.{form_instruction}
                Look for the best product that matches this ingredient.
                Add it to the cart. Then continue to the next ingredient."""
                
                agent = Agent(
                    task=task,
                    llm=llm,
                    browser=browser,
                    use_vision=False,
                )
                await agent.run(max_steps=15)
        else:
            # Use smart matching algorithm with LLM
            cart_items = await build_cart_llm(RECIPE_INGREDIENTS, catalog, llm)
            
            print(f"Selected {len(cart_items)} products using LLM-powered smart matching:")
            for item in cart_items:
                print(f"  - {item['product_name']}: {item['quantity']} unit(s) @ ${item['price']:.2f}")
            
            # Add products to cart
            await add_products_to_cart(browser, cart_items, llm)
            
            # Final task to verify cart
            verify_task = "Verify that all items have been added to the cart correctly."
            agent = Agent(
                task=verify_task,
                llm=llm,
                browser=browser,
                use_vision=False,
            )
            await agent.run(max_steps=5)
    
    finally:
        await browser.stop()


if __name__ == "__main__":
    asyncio.run(main())
