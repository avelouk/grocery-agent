"""
Minimal Browser-Use agent: jumbo.cl, find potatoes, add to cart.
No vision (use_vision=False) for minimal tokens.
If logged out, logs in using JUMBO_EMAIL and JUMBO_PASSWORD from .env.
"""
import asyncio
import os
from dotenv import load_dotenv

from browser_use import Agent, Browser, ChatBrowserUse

load_dotenv()

SITE = "https://www.jumbo.cl"
EMAIL = os.environ.get("JUMBO_EMAIL", "")
PASSWORD = os.environ.get("JUMBO_PASSWORD", "")

TASK = f"""Go to {SITE}.
If the site shows you are logged out or asks you to sign in, log in first: use email "{EMAIL}" and password "{PASSWORD}". Then continue.
Find potatoes and add them to the cart. Then stop."""


async def main():
    llm = ChatBrowserUse()
    browser = Browser(headless=False, keep_alive=True)

    agent = Agent(
        task=TASK,
        llm=llm,
        browser=browser,
        use_vision=False,
    )
    await agent.run(max_steps=20)


if __name__ == "__main__":
    asyncio.run(main())
