"""
SQLite DB for recipes and recipe ingredients.
Single init script creates tables; no migrations for MVP.
"""
import sqlite3
from pathlib import Path
from typing import Optional

from grocery_agent.models import Ingredient, IngredientCategory, IngredientForm, Recipe
from grocery_agent.quantity_parser import parse_quantity

# Default DB path: project root / data / grocery.db
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "grocery.db"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Return a connection to the SQLite DB; create file and tables if needed."""
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> None:
    """Create recipes and recipe_ingredients tables if they do not exist."""
    if conn is None:
        conn = get_connection(db_path)
        try:
            _create_tables(conn)
            _ensure_image_url_column(conn)
            conn.commit()
        finally:
            conn.close()
    else:
        _create_tables(conn)
        _ensure_image_url_column(conn)


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            instructions TEXT NOT NULL,
            source_url TEXT,
            portions REAL NOT NULL DEFAULT 4,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recipe_ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            quantity_per_portion REAL,
            unit TEXT,
            category TEXT NOT NULL DEFAULT 'other',
            optional INTEGER NOT NULL DEFAULT 0,
            pantry_item INTEGER NOT NULL DEFAULT 0,
            form TEXT NOT NULL DEFAULT 'fresh',
            UNIQUE(recipe_id, name)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_recipe_ingredients_recipe_id ON recipe_ingredients(recipe_id)")


def _ensure_image_url_column(conn: sqlite3.Connection) -> None:
    """Add image_url column to recipes if missing (for existing DBs)."""
    cols = [row[1] for row in conn.execute("PRAGMA table_info(recipes)").fetchall()]
    if "image_url" not in cols:
        conn.execute("ALTER TABLE recipes ADD COLUMN image_url TEXT")


def insert_recipe(conn: sqlite3.Connection, recipe: Recipe) -> int:
    """Insert a Recipe and its ingredients; return recipe id. Computes quantity_per_portion from quantity and portions."""
    image_url = getattr(recipe, "image_url", None) or None
    cur = conn.execute(
        "INSERT INTO recipes (name, instructions, source_url, portions, image_url) VALUES (?, ?, ?, ?, ?)",
        (recipe.name, recipe.instructions, recipe.source_url, recipe.portions, image_url),
    )
    recipe_id = cur.lastrowid
    portions = recipe.portions or 4
    if portions <= 0:
        portions = 4
    for ing in recipe.ingredients:
        qty = parse_quantity(ing.quantity)
        if qty is not None:
            quantity_per_portion = qty / portions
            unit = ing.unit or ""
        else:
            quantity_per_portion = None
            unit = (ing.unit or "to taste").strip() or "to taste"
        optional = 1 if getattr(ing, "optional", False) else 0
        pantry_item = 1 if getattr(ing, "pantry_item", False) else 0
        form_val = getattr(ing, "form", IngredientForm.FRESH)
        form_str = form_val.value if hasattr(form_val, "value") else str(form_val)
        conn.execute(
            "INSERT INTO recipe_ingredients (recipe_id, name, quantity_per_portion, unit, category, optional, pantry_item, form) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (recipe_id, ing.name, quantity_per_portion, unit, ing.category.value, optional, pantry_item, form_str),
        )
    return recipe_id


def update_recipe(
    conn: sqlite3.Connection,
    recipe_id: int,
    name: str,
    portions: float,
    instructions: str,
    source_url: str | None = None,
) -> bool:
    """Update recipe name, portions, instructions, source_url. Returns True if recipe existed."""
    cur = conn.execute(
        "UPDATE recipes SET name = ?, portions = ?, instructions = ?, source_url = ? WHERE id = ?",
        (name.strip(), portions, instructions.strip(), source_url.strip() if source_url else None, recipe_id),
    )
    return cur.rowcount > 0


def replace_recipe_ingredients(
    conn: sqlite3.Connection,
    recipe_id: int,
    ingredients: list[dict],
) -> None:
    """
    Replace all ingredients for a recipe. ingredients: list of dicts with
    name, quantity_per_portion (float|None), unit (str), category (str), optional (bool), pantry_item (bool), form (str).
    """
    conn.execute("DELETE FROM recipe_ingredients WHERE recipe_id = ?", (recipe_id,))
    for ing in ingredients:
        name = (ing.get("name") or "").strip()
        if not name:
            continue
        qpp = ing.get("quantity_per_portion")
        if qpp is not None:
            try:
                qpp = float(qpp)
            except (TypeError, ValueError):
                qpp = None
        unit = (ing.get("unit") or "").strip() or None
        category = (ing.get("category") or "other").strip().lower()
        if category not in [e.value for e in IngredientCategory]:
            category = "other"
        optional = bool(ing.get("optional"))
        pantry_item = bool(ing.get("pantry_item"))
        form = (ing.get("form") or "fresh").strip().lower()
        if form not in [e.value for e in IngredientForm]:
            form = "fresh"
        conn.execute(
            """INSERT INTO recipe_ingredients (recipe_id, name, quantity_per_portion, unit, category, optional, pantry_item, form)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (recipe_id, name, qpp, unit, category, 1 if optional else 0, 1 if pantry_item else 0, form),
        )


def recipe_from_row(
    conn: sqlite3.Connection, recipe_id: int
) -> Optional[Recipe]:
    """Load a Recipe by id with its ingredients (quantity_per_portion and unit from DB)."""
    row = conn.execute(
        "SELECT id, name, instructions, source_url, portions, image_url FROM recipes WHERE id = ?",
        (recipe_id,),
    ).fetchone()
    if not row:
        return None
    portions = float(row["portions"]) if row["portions"] is not None else 4
    ing_rows = conn.execute(
        "SELECT name, quantity_per_portion, unit, category, optional, pantry_item, form FROM recipe_ingredients WHERE recipe_id = ? ORDER BY id",
        (recipe_id,),
    ).fetchall()
    ingredients = []
    for r in ing_rows:
        qpp = r["quantity_per_portion"]
        try:
            qpp = float(qpp) if qpp is not None else None
        except (TypeError, ValueError):
            qpp = None
        optional = bool(r["optional"]) if "optional" in r.keys() else False
        pantry_item = bool(r["pantry_item"]) if "pantry_item" in r.keys() else False
        form_str = r["form"] if "form" in r.keys() and r["form"] else "fresh"
        try:
            form_enum = IngredientForm(form_str)
        except ValueError:
            form_enum = IngredientForm.FRESH
        ingredients.append(
            Ingredient(
                name=r["name"],
                quantity=None,
                unit=r["unit"] or None,
                category=IngredientCategory(r["category"]),
                quantity_per_portion=qpp,
                optional=optional,
                pantry_item=pantry_item,
                form=form_enum,
            )
        )
    return Recipe(
        name=row["name"],
        portions=portions,
        ingredients=ingredients,
        instructions=row["instructions"],
        source_url=row["source_url"],
        image_url=row["image_url"] if "image_url" in row.keys() and row["image_url"] else None,
    )


def delete_recipe(conn: sqlite3.Connection, recipe_id: int) -> bool:
    """Delete a recipe and its ingredients (CASCADE). Returns True if recipe existed."""
    cur = conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
    return cur.rowcount > 0


def list_recipes(conn: sqlite3.Connection) -> list[dict]:
    """Return all saved recipes as [{id, name, portions, image_url?}, ...] for the grocery-list picker."""
    rows = conn.execute(
        "SELECT id, name, portions, image_url FROM recipes ORDER BY name"
    ).fetchall()
    result = []
    for r in rows:
        rec = {"id": r["id"], "name": r["name"], "portions": float(r["portions"]) if r["portions"] is not None else 4}
        if "image_url" in r.keys() and r["image_url"]:
            rec["image_url"] = r["image_url"]
        result.append(rec)
    return result
