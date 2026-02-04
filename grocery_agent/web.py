"""
Small web UI: paste recipe or URL → LLM → save to SQLite → show recipe.
"""
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import httpx

from grocery_agent.db import get_connection, init_db, insert_recipe, recipe_from_row
from grocery_agent.fetch import fetch_recipe_text
from grocery_agent.recipe import parse_recipe

# Init DB on startup (creates data/grocery.db and tables if missing)
init_db()

app = FastAPI(title="Grocery Agent")
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Form: paste recipe text or paste recipe URL."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/ingest")
async def ingest(
    request: Request,
    text: str | None = Form(None),
    url: str | None = Form(None),
):
    """
    Ingest recipe: either paste text or paste URL.
    Fetch URL if given, then one LLM call → save to SQLite → show recipe.
    """
    if url and url.strip():
        try:
            recipe_text = await fetch_recipe_text(url.strip())
        except httpx.HTTPStatusError as e:
            return templates.TemplateResponse(
                "index.html",
                {"request": request, "error": f"Could not fetch URL: {e.response.status_code} {e.response.reason_phrase}. Try pasting the recipe text instead."},
            )
        except httpx.RequestError as e:
            return templates.TemplateResponse(
                "index.html",
                {"request": request, "error": f"Could not fetch URL: {e!s}. Try pasting the recipe text instead."},
            )
    elif text and text.strip():
        recipe_text = text.strip()
    else:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "error": "Paste recipe text or a recipe URL."},
        )
    try:
        recipe = await parse_recipe(recipe_text)
    except ValueError as e:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "error": str(e)},
        )
    if url and url.strip():
        recipe.source_url = url.strip()
    conn = get_connection()
    try:
        recipe_id = insert_recipe(conn, recipe)
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(url=f"/recipe/{recipe_id}", status_code=303)


def run() -> None:
    """Run the web app (uv run start)."""
    import uvicorn
    uvicorn.run("grocery_agent.web:app", host="0.0.0.0", port=8000, reload=True)


def _format_scaled_amount(quantity_per_portion: float | None, unit: str | None, servings: int) -> str:
    """Format ingredient amount for display: scaled number + unit, or just unit (e.g. 'to taste')."""
    if quantity_per_portion is None:
        return (unit or "to taste").strip()
    amount = quantity_per_portion * servings
    # Avoid "2.0 cups" -> show "2 cups"
    if amount == int(amount):
        num_str = str(int(amount))
    else:
        num_str = f"{amount:.2g}".rstrip("0").rstrip(".")
    return f"{num_str} {unit or ''}".strip()


@app.get("/recipe/{recipe_id}", response_class=HTMLResponse)
async def show_recipe(request: Request, recipe_id: int, servings: int = 4):
    """Show a saved recipe scaled to the given number of servings (default 4)."""
    if servings < 1:
        servings = 4
    conn = get_connection()
    try:
        recipe = recipe_from_row(conn, recipe_id)
    finally:
        conn.close()
    if not recipe:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "error": f"Recipe {recipe_id} not found."},
        )
    # Precompute display string for each ingredient (scaled amount + unit, or just unit)
    ingredients_display = [
        {
            "name": ing.name,
            "category": ing.category,
            "amount_str": _format_scaled_amount(ing.quantity_per_portion, ing.unit, servings),
        }
        for ing in recipe.ingredients
    ]
    return templates.TemplateResponse(
        "recipe.html",
        {
            "request": request,
            "recipe": recipe,
            "recipe_id": recipe_id,
            "servings": servings,
            "ingredients_display": ingredients_display,
        },
    )
