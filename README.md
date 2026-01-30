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

Copy env example and set an API key:

```bash
cp .env.example .env
# Edit .env: set OPENAI_API_KEY=sk-... (or BROWSER_USE_API_KEY if you use ChatBrowserUse)
```

## Run

```bash
uv run run_jumbo.py
```

Or with venv active: `python run_jumbo.py`

Browser opens on jumbo.cl; the agent navigates, finds potatoes, and adds them to the cart. Task and site are in `run_jumbo.py` (no vision: `use_vision=False`).

## Optional: ChatBrowserUse

For their recommended model (fast, low cost), get a key at [cloud.browser-use.com](https://cloud.browser-use.com/new-api-key), set `BROWSER_USE_API_KEY` in `.env`, and in `run_jumbo.py` use:

```python
from browser_use import ChatBrowserUse
llm = ChatBrowserUse()
```

instead of `ChatOpenAI`.
