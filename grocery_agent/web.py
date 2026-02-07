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
from grocery_agent.db import (
    delete_recipe,
    get_connection,
    init_db,
    insert_recipe,
    list_recipes,
    recipe_from_row,
    replace_recipe_ingredients,
    update_recipe,
)
from grocery_agent.fetch import fetch_recipe_image_url, fetch_recipe_text
from grocery_agent.ingredient_normalizer import normalize_ingredients_with_llm
from grocery_agent.models import Recipe
from grocery_agent.recipe import parse_recipe

# Init DB on startup (creates data/grocery.db and tables if missing)
init_db()

app = FastAPI(title="Grocery Agent")
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _home_response(
    request: Request,
    recipes: list,
    error: str | None = None,
    new_id: int | None = None,
):
    """Render the home page (recipe picker + add recipe)."""
    return templates.TemplateResponse(
        "home.html",
        {"request": request, "recipes": recipes, "error": error, "new_id": new_id},
    )


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, new_id: int | None = None):
    """Single home: pick recipes for the week, or add a new one (link/text). new_id pre-selects that recipe."""
    conn = get_connection()
    try:
        recipes = list_recipes(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(
        "home.html",
        {"request": request, "recipes": recipes, "new_id": new_id},
    )


@app.get("/list", response_class=HTMLResponse)
async def list_redirect():
    """Redirect to home."""
    return RedirectResponse(url="/", status_code=302)


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
            return _home_response(request, recipes, "Could not fetch URL. Try pasting text.")
        try:
            recipe = await parse_recipe(recipe_text)
        except ValueError as e:
            conn = get_connection()
            recipes = list_recipes(conn)
            conn.close()
            return _home_response(request, recipes, str(e))
        recipe.source_url = url.strip()
        recipe.image_url = await fetch_recipe_image_url(url.strip())
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
            return _home_response(request, recipes, str(e))
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
            return _home_response(request, recipes, "Select at least one recipe or add one below.")
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
        return RedirectResponse(url="/", status_code=302)
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
    # Only checked checkboxes are submitted; unchecked ones are omitted from the form.
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

    # Recipe items: only those whose checkbox was checked (selected_indices).
    items = await get_grocery_list(recipe_id_list, portions_override or None, selected_indices)
    # Append manual extra items from the textarea (one per line).
    extra_raw = form.get("extra_items") or ""
    for line in extra_raw.splitlines():
        name = line.strip()
        if name:
            items.append({
                "name": name,
                "amount_str": "",
                "form": "other",
                "category": "other",
                "optional": False,
                "pantry_item": False,
                "source": "manual",
            })
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
    """Add a new recipe (URL or text). Redirect to home with new recipe selected."""
    conn = get_connection()
    try:
        recipes = list_recipes(conn)
    finally:
        conn.close()
    if url and url.strip():
        try:
            recipe_text = await fetch_recipe_text(url.strip())
        except httpx.HTTPStatusError as e:
            return _home_response(request, recipes, f"Could not fetch URL: {e.response.status_code}. Try pasting the recipe text instead.")
        except httpx.RequestError as e:
            return _home_response(request, recipes, f"Could not fetch URL: {e!s}. Try pasting the recipe text instead.")
    elif text and text.strip():
        recipe_text = text.strip()
    else:
        return _home_response(request, recipes, "Paste recipe text or a recipe URL.")
    try:
        recipe = await parse_recipe(recipe_text)
    except ValueError as e:
        return _home_response(request, recipes, str(e))
    if url and url.strip():
        recipe.source_url = url.strip()
        recipe.image_url = await fetch_recipe_image_url(url.strip())
    conn = get_connection()
    try:
        recipe_id = insert_recipe(conn, recipe)
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(url=f"/?new_id={recipe_id}", status_code=303)


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
        conn = get_connection()
        try:
            recipes = list_recipes(conn)
        finally:
            conn.close()
        return _home_response(request, recipes, f"Recipe {recipe_id} not found.")
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


@app.get("/recipe/{recipe_id}/edit", response_class=HTMLResponse)
async def recipe_edit_page(request: Request, recipe_id: int):
    """Minimal edit form: name, portions, instructions, source URL."""
    conn = get_connection()
    try:
        recipe = recipe_from_row(conn, recipe_id)
    finally:
        conn.close()
    if not recipe:
        conn = get_connection()
        try:
            recipes = list_recipes(conn)
        finally:
            conn.close()
        return _home_response(request, recipes, f"Recipe {recipe_id} not found.")
    ingredient_count = len(recipe.ingredients) + 1  # +1 for empty "add" row
    return templates.TemplateResponse(
        "recipe_edit.html",
        {"request": request, "recipe": recipe, "recipe_id": recipe_id, "ingredient_count": ingredient_count},
    )


@app.post("/recipe/{recipe_id}/edit", response_class=HTMLResponse)
async def recipe_edit_submit(
    request: Request,
    recipe_id: int,
    name: str = Form(...),
    portions: float = Form(4),
    instructions: str = Form(...),
    source_url: str | None = Form(None),
    ingredient_count: int = Form(0),
):
    """Update recipe (and ingredients) and redirect home."""
    form = await request.form()
    portions = max(0.25, float(portions))
    ingredients = []
    for i in range(ingredient_count):
        # Skip ingredients marked for deletion
        if form.get(f"ingredient_{i}_delete") == "1":
            continue
        iname = form.get(f"ingredient_{i}_name")
        if iname is None or not str(iname).strip():
            continue
        qty_raw = form.get(f"ingredient_{i}_qty")
        try:
            qty = float(qty_raw) if qty_raw not in (None, "") else None
        except (TypeError, ValueError):
            qty = None
        unit = form.get(f"ingredient_{i}_unit") or ""
        category = form.get(f"ingredient_{i}_category") or "other"
        optional = form.get(f"ingredient_{i}_optional") == "1"
        pantry = form.get(f"ingredient_{i}_pantry") == "1"
        form_val = form.get(f"ingredient_{i}_form") or "fresh"
        ingredients.append({
            "name": str(iname).strip(),
            "quantity_per_portion": qty,
            "unit": str(unit).strip() or None,
            "category": str(category).strip() or "other",
            "optional": optional,
            "pantry_item": pantry,
            "form": str(form_val).strip() or "fresh",
        })
    conn = get_connection()
    try:
        ok = update_recipe(conn, recipe_id, name, portions, instructions, source_url)
        if ok:
            replace_recipe_ingredients(conn, recipe_id, ingredients)
        conn.commit()
    finally:
        conn.close()
    if not ok:
        conn = get_connection()
        try:
            recipes = list_recipes(conn)
        finally:
            conn.close()
        return _home_response(request, recipes, f"Recipe {recipe_id} not found.")
    return RedirectResponse(url="/", status_code=303)


@app.post("/recipe/{recipe_id}/delete", response_class=HTMLResponse)
async def recipe_delete(request: Request, recipe_id: int):
    """Delete a recipe and redirect home."""
    conn = get_connection()
    try:
        ok = delete_recipe(conn, recipe_id)
        conn.commit()
    finally:
        conn.close()
    if not ok:
        conn = get_connection()
        try:
            recipes = list_recipes(conn)
        finally:
            conn.close()
        return _home_response(request, recipes, f"Recipe {recipe_id} not found.")
    return RedirectResponse(url="/", status_code=303)
