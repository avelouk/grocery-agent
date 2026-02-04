"""
Small web UI: paste recipe or URL → LLM → save to SQLite → show recipe.
"""
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import httpx

from grocery_agent.aggregate import flat_ingredients, merge_flat_ingredients
from grocery_agent.db import get_connection, init_db, insert_recipe, list_recipes, recipe_from_row
from grocery_agent.fetch import fetch_recipe_text
from grocery_agent.ingredient_normalizer import normalize_ingredients_with_llm
from grocery_agent.models import Recipe
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


@app.get("/list", response_class=HTMLResponse)
async def list_page(request: Request):
    """Step 1: Pick recipes for the week (from saved or paste link/text to ingest)."""
    conn = get_connection()
    try:
        recipes = list_recipes(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(
        "list.html",
        {"request": request, "recipes": recipes},
    )


@app.post("/list", response_class=HTMLResponse)
async def list_submit(
    request: Request,
    recipe_ids: list[int] = Form(default=[]),
    url: str | None = Form(None),
    text: str | None = Form(None),
):
    """
    Step 1 submit: optional new recipe via url/text (ingest then add id), then redirect to checklist.
    recipe_ids from checkboxes: Form sends as repeated keys or single int when one selected.
    """
    if isinstance(recipe_ids, list):
        ids = [int(x) for x in recipe_ids if x is not None]
    elif recipe_ids is not None:
        ids = [int(recipe_ids)]
    else:
        ids = []
    if url and url.strip():
        try:
            recipe_text = await fetch_recipe_text(url.strip())
        except Exception:
            conn = get_connection()
            try:
                recipes = list_recipes(conn)
            finally:
                conn.close()
            return templates.TemplateResponse(
                "list.html",
                {"request": request, "recipes": recipes, "error": "Could not fetch URL. Try pasting text."},
            )
        try:
            recipe = await parse_recipe(recipe_text)
        except ValueError as e:
            conn = get_connection()
            recipes = list_recipes(conn)
            conn.close()
            return templates.TemplateResponse(
                "list.html",
                {"request": request, "recipes": recipes, "error": str(e)},
            )
        recipe.source_url = url.strip()
        conn = get_connection()
        try:
            new_id = insert_recipe(conn, recipe)
            conn.commit()
            ids.append(new_id)
        finally:
            conn.close()
    elif text and text.strip():
        try:
            recipe = await parse_recipe(text.strip())
        except ValueError as e:
            conn = get_connection()
            recipes = list_recipes(conn)
            conn.close()
            return templates.TemplateResponse(
                "list.html",
                {"request": request, "recipes": recipes, "error": str(e)},
            )
        conn = get_connection()
        try:
            new_id = insert_recipe(conn, recipe)
            conn.commit()
            ids.append(new_id)
        finally:
            conn.close()
    if not ids:
        conn = get_connection()
        try:
            recipes = list_recipes(conn)
        finally:
            conn.close()
            return templates.TemplateResponse(
                "list.html",
                {"request": request, "recipes": recipes, "error": "Select at least one recipe or add one by link/text."},
            )
    form = await request.form()
    portion_qs = []
    for rid in ids:
        raw = form.get(f"portion_{rid}")
        if raw is not None and str(raw).strip():
            try:
                p = max(1, int(float(str(raw).strip())))
                portion_qs.append(f"portion_{rid}={p}")
            except (ValueError, TypeError):
                pass
    query = "&".join([f"ids={','.join(map(str, ids))}"] + portion_qs)
    return RedirectResponse(url=f"/list/checklist?{query}", status_code=303)


@app.get("/list/checklist", response_class=HTMLResponse)
async def checklist_page(request: Request, ids: str = ""):
    """
    Step 2 & 3: Aggregated ingredient checklist.
    Default: pantry items unchecked (won't order), weekly items checked (will order).
    User marks pantry items they need to restock.
    Portions per recipe: use query portion_1=4, portion_2=6 etc.; else recipe default.
    """
    recipe_ids = [int(x.strip()) for x in ids.split(",") if x.strip()]
    if not recipe_ids:
        return RedirectResponse(url="/list", status_code=302)
    portions_override = {}
    for rid in recipe_ids:
        raw = request.query_params.get(f"portion_{rid}")
        if raw is not None and str(raw).strip():
            try:
                portions_override[rid] = max(1, int(float(str(raw).strip())))
            except (ValueError, TypeError):
                pass
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
        return RedirectResponse(url="/list", status_code=302)
    flat = flat_ingredients(recipes)
    canonical_list = await normalize_ingredients_with_llm(flat)
    ingredients_display = merge_flat_ingredients(flat, canonical_list)
    recipe_portions = [(recipe_ids[i], int(recipes[i].portions)) for i in range(len(recipe_ids))]
    return templates.TemplateResponse(
        "checklist.html",
        {
            "request": request,
            "recipe_ids": recipe_ids,
            "recipes": recipes,
            "recipe_portions": recipe_portions,
            "ingredients_display": ingredients_display,
        },
    )


@app.get("/api/grocery-list")
async def api_grocery_list(
    request: Request,
    ids: str = "",
    selected: str = "",
):
    """
    JSON output for the jumbo agent. Same format as get_grocery_list().
    Query: ids=1,2,3 & portion_1=4 & portion_2=6 (optional) & selected=0,1,3 (optional, indices to include).
    """
    from grocery_agent.grocery_list import get_grocery_list

    recipe_ids = [int(x.strip()) for x in ids.split(",") if x.strip()]
    if not recipe_ids:
        return {"items": []}
    portions_override = {}
    for rid in recipe_ids:
        raw = request.query_params.get(f"portion_{rid}")
        if raw is not None and str(raw).strip():
            try:
                portions_override[rid] = max(1, int(float(str(raw).strip())))
            except (ValueError, TypeError):
                pass
    selected_indices = None
    if selected.strip():
        try:
            selected_indices = [int(x.strip()) for x in selected.split(",") if x.strip()]
        except ValueError:
            pass
    items = await get_grocery_list(recipe_ids, portions_override or None, selected_indices)
    return {"items": items}


@app.post("/list/confirm", response_class=HTMLResponse)
async def list_confirm(request: Request, recipe_ids: str = Form("")):
    """
    User confirmed. Build grocery list, write to data/grocery_list.json, start jumbo bot.
    """
    form = await request.form()
    ids_str = (recipe_ids or "").strip()
    recipe_id_list = [int(x.strip()) for x in ids_str.split(",") if x.strip()]
    raw = form.getlist("item_index")
    selected_indices = [int(x) for x in raw if x is not None and str(x).strip().isdigit()]
    portions_override = {}
    for rid in recipe_id_list:
        val = form.get(f"portion_{rid}")
        if val is not None and str(val).strip():
            try:
                portions_override[rid] = max(1, int(float(str(val).strip())))
            except (ValueError, TypeError):
                pass
    portions_qs = "&".join(
        f"portion_{rid}={form.get(f'portion_{rid}')}" for rid in recipe_id_list if form.get(f"portion_{rid}") is not None
    )

    from grocery_agent.grocery_list import get_grocery_list, write_grocery_list

    items = await get_grocery_list(recipe_id_list, portions_override or None, selected_indices)
    write_grocery_list(items)

    project_root = Path(__file__).resolve().parent.parent
    # Let stdout/stderr inherit so run_jumbo logs appear in the same terminal as the web server.
    subprocess.Popen(
        [sys.executable, str(project_root / "run_jumbo.py")],
        cwd=str(project_root),
        stdin=subprocess.DEVNULL,
    )

    return templates.TemplateResponse(
        "confirm.html",
        {
            "request": request,
            "recipe_ids": recipe_id_list,
            "recipe_ids_str": ",".join(map(str, recipe_id_list)),
            "portions_qs": portions_qs,
            "selected_count": len(selected_indices),
            "message": "Bot started. Check the browser window.",
        },
    )


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
            "optional": getattr(ing, "optional", False),
            "pantry_item": getattr(ing, "pantry_item", False),
            "form": getattr(ing, "form", None),
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
