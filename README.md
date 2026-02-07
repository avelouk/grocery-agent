# Grocery agent

Web app to ingest recipes and build a grocery list; jumbo.cl browser agent to add items to cart.

**Flow:** Paste recipe (or URL) → LLM parses → save to SQLite. Pick recipes for the week → checklist (LLM merges duplicates) → confirm → jumbo bot opens browser and uses the list.

---

## Setup

```bash
uv venv --python 3.11
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv pip install -e .
uvx browser-use install     # for jumbo cart
```

## Configure

`cp .env.example .env` then set:

| What | Env var | Notes |
|------|---------|--------|
| Jumbo login | `JUMBO_EMAIL`, `JUMBO_PASSWORD` | Required for the jumbo bot. |
| Web app (recipes, grocery list) | `GOOGLE_API_KEY` | [Get key](https://aistudio.google.com/app/apikey). Used for structured output. |
| Jumbo browser agent | `BROWSER_USE_API_KEY` | [Get key](https://cloud.browser-use.com/new-api-key). Preferred for the jumbo bot; falls back to Google if unset. |
| Custom browser | `BROWSER_EXECUTABLE_PATH` | Optional. Default: auto-detect Chromium on macOS. |

**TL;DR:** Set `GOOGLE_API_KEY` for the web app. Set `BROWSER_USE_API_KEY` (or `GOOGLE_API_KEY`) for the jumbo bot. Set both for full flow.

---

## Run

**Web app** — recipe ingest + grocery list:

```bash
uv run start
```

Open http://localhost:8000. Ingest recipes (paste text or URL), then use **Grocery list** to pick recipes, set portions, and get a checklist. **Confirm and add to cart** writes the list to `data/grocery_list.json` and starts the jumbo bot (logs appear in the same terminal).

**Jumbo bot only** (e.g. for testing):

```bash
uv run run_jumbo.py
# or
uv run python -m grocery_agent.jumbo
```

Browser opens on jumbo.cl; agent logs in and runs the task. With a list from the web app, it reads `data/grocery_list.json`. The bot lives in `grocery_agent.jumbo` (prompts, config, runner); `run_jumbo.py` is a thin entry point.

---

## Grocery list output (for jumbo agent)

The list is normalized and flattened. Each item: `name`, `amount_str`, `form`, `category`, `optional`, `pantry_item`. Example: `{"name": "Potato", "amount_str": "3 medium + 2 lb", "form": "fresh", ...}`.

**Get the list:**

- **Python:** `from grocery_agent.grocery_list import get_grocery_list` → `items = await get_grocery_list(recipe_ids=[1,2], portions_override={1:4}, selected_indices=[0,1])`. Sync: `get_grocery_list_sync(...)`.
- **CLI:** `uv run python -m grocery_agent.grocery_list 1 2 --portions 1=4 --selected 0 1`
- **HTTP:** `GET /api/grocery-list?ids=1,2&portion_1=4&selected=0,1` → `{"items": [...]}`
