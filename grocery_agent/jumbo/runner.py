"""Run the Jumbo browser agent: login, then process grocery list or fallback."""
import logging

from browser_use import Agent, Browser

from grocery_agent.grocery_list import load_grocery_list
from grocery_agent.jumbo.config import SITE, get_browser_executable, get_credentials
from grocery_agent.jumbo.prompts import (
    NON_PERISHABLE_CATEGORIES,
    build_fallback_task,
    build_item_task,
    build_login_task,
)

logger = logging.getLogger(__name__)

MAX_STEPS_LOGIN = 15
MAX_STEPS_ITEM = 20
MAX_STEPS_FALLBACK = 20


def _make_browser():
    kwargs = {"headless": False, "keep_alive": True}
    path = get_browser_executable()
    if path:
        kwargs["executable_path"] = path
    return Browser(**kwargs)


def _log_item(i: int, item: dict) -> None:
    logger.info(
        "  %d. %s %s (%s)%s",
        i,
        item.get("amount_str", ""),
        item.get("name", ""),
        item.get("form", ""),
        " [optional]" if item.get("optional") else "",
    )


async def run(llm, browser: Browser | None = None):
    """
    Load grocery list, run login, then process each item (or fallback).
    Uses use_vision=False. Caller must load_dotenv() and set up logging/LLM.
    """
    items = load_grocery_list()
    email, password = get_credentials()

    if not items:
        logger.info("No grocery list found (data/grocery_list.json missing or empty).")
        logger.info("Using fallback task: search for papas")

    if items:
        logger.info("Grocery list (%d items):", len(items))
        for i, item in enumerate(items, 1):
            _log_item(i, item)

    if browser is None:
        browser = _make_browser()

    # Login
    logger.info("=" * 60)
    logger.info("STEP 1: Login/Verify session")
    logger.info("=" * 60)
    login_task = build_login_task(SITE, email, password)
    logger.info("Login task:\n%s", login_task)

    agent = Agent(task=login_task, llm=llm, browser=browser, use_vision=False)
    await agent.run(max_steps=MAX_STEPS_LOGIN)

    # Items or fallback
    if items:
        total = len(items)
        for i, item in enumerate(items, 1):
            logger.info("")
            logger.info("=" * 60)
            logger.info("STEP %d/%d: Processing %s", i, total, item.get("name", "").upper())
            logger.info("=" * 60)

            task = build_item_task(item, i, total, NON_PERISHABLE_CATEGORIES)
            logger.info("Item task:\n%s", task)

            agent = Agent(task=task, llm=llm, browser=browser, use_vision=False)
            try:
                await agent.run(max_steps=MAX_STEPS_ITEM)
            except Exception as e:
                logger.error("Error processing item %d (%s): %s", i, item.get("name"), e)
                if item.get("optional"):
                    logger.info("Item is optional, continuing to next item...")
                else:
                    logger.warning("Item is required, but continuing anyway. Check manually.")

        logger.info("")
        logger.info("=" * 60)
        logger.info("COMPLETE: Processed %d items", total)
        logger.info("=" * 60)
    else:
        fallback_task = build_fallback_task(SITE, email, password)
        logger.info("Fallback task:\n%s", fallback_task)
        agent = Agent(task=fallback_task, llm=llm, browser=browser, use_vision=False)
        await agent.run(max_steps=MAX_STEPS_FALLBACK)
