"""
LLM resolution from env: Browser-Use or Google (Gemini).
Shared by run_jumbo and the web app.
"""
import os

from browser_use import ChatBrowserUse, ChatGoogle


def get_llm():
    """Return the configured LLM. Raises ValueError if no API key is set."""
    if os.environ.get("BROWSER_USE_API_KEY"):
        return ChatBrowserUse()
    if os.environ.get("GOOGLE_API_KEY"):
        model = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
        return ChatGoogle(model=model)
    raise ValueError("Set BROWSER_USE_API_KEY or GOOGLE_API_KEY in .env")
