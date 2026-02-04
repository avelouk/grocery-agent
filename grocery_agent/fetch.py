"""Fetch main text from a recipe URL."""
import httpx
import trafilatura

# Browser-like headers so some sites don't return 403 for bots
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


async def fetch_recipe_text(url: str) -> str:
    """Fetch URL and return main article/recipe text (strip HTML, ads, nav)."""
    async with httpx.AsyncClient(follow_redirects=True, headers=DEFAULT_HEADERS) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        html = resp.text
    extracted = trafilatura.extract(html, include_comments=False, include_tables=False)
    if not extracted or not extracted.strip():
        return resp.text[:50000]  # fallback: raw text truncated
    return extracted.strip()
