"""Fetch main text and main image from a recipe URL."""
import re
from urllib.parse import urljoin

import httpx
import trafilatura

# Browser-like headers so some sites don't return 403 for bots
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Match og:image or twitter:image meta tags (content="...")
_IMAGE_META_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)["\']'
    r'|<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\']',
    re.IGNORECASE,
)


async def fetch_recipe_image_url(page_url: str) -> str | None:
    """Fetch the recipe page HTML and return the main image URL (og:image or twitter:image), or None."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, headers=DEFAULT_HEADERS) as client:
            resp = await client.get(page_url)
            resp.raise_for_status()
            html = resp.text
    except (httpx.HTTPStatusError, httpx.RequestError):
        return None
    m = _IMAGE_META_RE.search(html)
    if not m:
        return None
    raw = (m.group(1) or m.group(2) or "").strip()
    if not raw or not raw.startswith(("http", "//")):
        return urljoin(page_url, raw) if raw else None
    if raw.startswith("//"):
        return "https:" + raw
    return raw


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
