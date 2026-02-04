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

Copy env example and set the required values:

```bash
cp .env.example .env
```

**Required:**
- **LLM:** set one in `.env` — `BROWSER_USE_API_KEY` ([get key](https://cloud.browser-use.com/new-api-key)) or `GOOGLE_API_KEY` ([get key](https://aistudio.google.com/app/apikey)). If both are set, Browser-Use is used.
- **Jumbo credentials:** `JUMBO_EMAIL` and `JUMBO_PASSWORD`

**Optional:**
- **Browser:** `BROWSER_EXECUTABLE_PATH` — custom browser executable path (e.g., Ungoogled Chromium). If not set, auto-detects Ungoogled Chromium at `/Applications/Chromium.app/Contents/MacOS/Chromium` on macOS, otherwise uses browser-use default.
- `GEMINI_MODEL` — override Gemini model (default: gemini-flash-latest).

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
