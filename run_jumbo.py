"""
Minimal Browser-Use agent: jumbo.cl, find potatoes, add to cart.
No vision (use_vision=False) for minimal tokens.
If logged out, logs in using JUMBO_EMAIL and JUMBO_PASSWORD from .env.

LLM: set one in .env — BROWSER_USE_API_KEY (cloud.browser-use.com) or GOOGLE_API_KEY (Google AI Studio).
Browser-Use is used if both are set.
"""
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

from browser_use import Agent, Browser
from grocery_agent.llm import get_llm

load_dotenv()

SITE = "https://www.jumbo.cl"
EMAIL = os.environ.get("JUMBO_EMAIL", "")
PASSWORD = os.environ.get("JUMBO_PASSWORD", "")

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
    try:
        llm = get_llm()
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
