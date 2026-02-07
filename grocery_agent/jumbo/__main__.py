"""Entry point: python -m grocery_agent.jumbo"""
import asyncio
import logging
import sys

from dotenv import load_dotenv

from grocery_agent.jumbo import run
from grocery_agent.llm import get_browser_use_llm

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    try:
        llm = get_browser_use_llm()
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    asyncio.run(run(llm))


if __name__ == "__main__":
    main()
