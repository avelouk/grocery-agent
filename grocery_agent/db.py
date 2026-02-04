"""
SQLite DB for recipes and recipe ingredients.
Single init script creates tables; no migrations for MVP.
"""
import sqlite3
from pathlib import Path
from typing import Optional

from grocery_agent.models import Ingredient, IngredientCategory, Recipe
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
            conn.commit()
        finally:
            conn.close()
    else:
        _create_tables(conn)


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
            UNIQUE(recipe_id, name)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_recipe_ingredients_recipe_id ON recipe_ingredients(recipe_id)")


def insert_recipe(conn: sqlite3.Connection, recipe: Recipe) -> int:
    """Insert a Recipe and its ingredients; return recipe id. Computes quantity_per_portion from quantity and portions."""
    cur = conn.execute(
        "INSERT INTO recipes (name, instructions, source_url, portions) VALUES (?, ?, ?, ?)",
        (recipe.name, recipe.instructions, recipe.source_url, recipe.portions),
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
        conn.execute(
            "INSERT INTO recipe_ingredients (recipe_id, name, quantity_per_portion, unit, category) VALUES (?, ?, ?, ?, ?)",
            (recipe_id, ing.name, quantity_per_portion, unit, ing.category.value),
        )
    return recipe_id


def recipe_from_row(
    conn: sqlite3.Connection, recipe_id: int
) -> Optional[Recipe]:
    """Load a Recipe by id with its ingredients (quantity_per_portion and unit from DB)."""
    row = conn.execute(
        "SELECT id, name, instructions, source_url, portions FROM recipes WHERE id = ?",
        (recipe_id,),
    ).fetchone()
    if not row:
        return None
    portions = float(row["portions"]) if row["portions"] is not None else 4
    ing_rows = conn.execute(
        "SELECT name, quantity_per_portion, unit, category FROM recipe_ingredients WHERE recipe_id = ? ORDER BY id",
        (recipe_id,),
    ).fetchall()
    ingredients = []
    for r in ing_rows:
        qpp = r["quantity_per_portion"]
        try:
            qpp = float(qpp) if qpp is not None else None
        except (TypeError, ValueError):
            qpp = None
        ingredients.append(
            Ingredient(
                name=r["name"],
                quantity=None,
                unit=r["unit"] or None,
                category=IngredientCategory(r["category"]),
                quantity_per_portion=qpp,
            )
        )
    return Recipe(
        name=row["name"],
        portions=portions,
        ingredients=ingredients,
        instructions=row["instructions"],
        source_url=row["source_url"],
    )
