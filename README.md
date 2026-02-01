# Grocery agent (Browser-Use)

Minimal [Browser-Use](https://github.com/browser-use/browser-use) agent: **jumbo.cl**, find potatoes, add to cart. No vision (minimal tokens).

## Setup (use uv)

From the repo root:

```bash
# Create venv and install (uv: https://github.com/astral-sh/uv)
uv venv --python 3.11
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv pip install -e .

# Install browser (Chromium for Browser-Use)
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

## Run

```bash
uv run run_jumbo.py
```

Or with venv active: `python run_jumbo.py`

Browser opens on jumbo.cl; the agent navigates, finds potatoes, and adds them to the cart. Task and site are in `run_jumbo.py` (no vision: `use_vision=False`).
