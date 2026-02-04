# Grocery agent

Recipe ingest (web UI) + jumbo.cl cart (Browser-Use). Small web app: paste recipe or URL → LLM → SQLite → show recipe.

## Setup (use uv)

From the repo root:

```bash
uv venv --python 3.11
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv pip install -e .

# For jumbo.cl cart only: install browser
uvx browser-use install
```

## Configure

```bash
cp .env.example .env
```

Set one LLM key in `.env`: `BROWSER_USE_API_KEY` or `GOOGLE_API_KEY`. Optional: `GEMINI_MODEL`, `JUMBO_EMAIL`, `JUMBO_PASSWORD`.

## Run

**Web app (recipe ingest):**

```bash
uv run start
```

Then open http://localhost:8000 — paste recipe text or a recipe URL, submit; the app fetches (if URL), calls the LLM once, saves to SQLite (`data/grocery.db`), and shows the structured recipe.

**Jumbo.cl cart:**

```bash
uv run run_jumbo.py
```

Browser opens on jumbo.cl; the agent finds potatoes and adds them to the cart (no vision).
