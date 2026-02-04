"""
Minimal Browser-Use agent: jumbo.cl, find potatoes, add to cart.
No vision (use_vision=False) for minimal tokens.
If logged out, logs in using JUMBO_EMAIL and JUMBO_PASSWORD from .env.

Grocery list: when started from the web app (Confirm and add to cart), the list is written to
data/grocery_list.json. Load it via load_grocery_list() — GROCERY_ITEMS is available for the task.
Each item has: name, amount_str, form, category, optional, pantry_item.

LLM: set one in .env — BROWSER_USE_API_KEY (cloud.browser-use.com) or GOOGLE_API_KEY (Google AI Studio).
Browser-Use is used if both are set.
"""
import asyncio
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

from browser_use import Agent, Browser
from grocery_agent.grocery_list import load_grocery_list
from grocery_agent.llm import get_browser_use_llm

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

SITE = "https://www.jumbo.cl"
EMAIL = os.environ.get("JUMBO_EMAIL", "")
PASSWORD = os.environ.get("JUMBO_PASSWORD", "")

# Loaded at startup from data/grocery_list.json (written by web app on Confirm).
# TODO: Use GROCERY_ITEMS in TASK so the agent adds these items to the cart instead of the hardcoded "papas".
#       Each item has: name, amount_str, form, category, optional, pantry_item. Build the task text from this list.
GROCERY_ITEMS: list[dict] | None = None

TASK = f"""Go to {SITE}.
If the site shows you are logged out or asks you to sign in, log in first: use email "{EMAIL}" and password "{PASSWORD}". Then continue.
Find papas and add them to the cart. Then stop."""

def get_browser_executable():
    """Get browser executable path from env var or auto-detect Ungoogled Chromium."""
    # Check environment variable first
    env_path = os.environ.get("BROWSER_EXECUTABLE_PATH")
    if env_path and Path(env_path).exists():
        return env_path
    
    # Auto-detect Ungoogled Chromium at common macOS location
    default_path = Path("/Applications/Chromium.app/Contents/MacOS/Chromium")
    if default_path.exists():
        return str(default_path)
    
    # Return None to use browser-use default
    return None


async def main():
    global GROCERY_ITEMS
    GROCERY_ITEMS = load_grocery_list()
    if GROCERY_ITEMS:
        logger.info("Grocery list (%d items):", len(GROCERY_ITEMS))
        for i, item in enumerate(GROCERY_ITEMS, 1):
            logger.info(
                "  %d. %s %s (%s)%s",
                i,
                item.get("amount_str", ""),
                item.get("name", ""),
                item.get("form", ""),
                " [optional]" if item.get("optional") else "",
            )
    else:
        logger.info("No grocery list found (data/grocery_list.json missing or empty).")
    try:
        llm = get_browser_use_llm()
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    browser_kwargs = {"headless": False, "keep_alive": True}
    executable_path = get_browser_executable()
    if executable_path:
        browser_kwargs["executable_path"] = executable_path
    browser = Browser(**browser_kwargs)

    agent = Agent(
        task=TASK,
        llm=llm,
        browser=browser,
        use_vision=False,
    )
    await agent.run(max_steps=20)


if __name__ == "__main__":
    asyncio.run(main())
