"""
LLM resolution from env. Two use cases:

- get_browser_use_llm(): for browser automation (run_jumbo). Requires BROWSER_USE_API_KEY.
  Prefers Browser-Use; falls back to get_generic_llm() (Google) if only GOOGLE_API_KEY is set.

- get_generic_llm(): for structured output (recipe parsing, ingredient normalization).
  Uses Google (Gemini), which supports arbitrary Pydantic models. Requires GOOGLE_API_KEY.

- get_llm(): alias for get_generic_llm() for backward compatibility.
"""
import os

from browser_use import ChatBrowserUse, ChatGoogle


def get_browser_use_llm():
    """Return an LLM for browser automation (run_jumbo). Prefers Browser-Use API; falls back to Google if only GOOGLE_API_KEY is set."""
    if os.environ.get("BROWSER_USE_API_KEY"):
        return ChatBrowserUse()
    return get_generic_llm()


def get_generic_llm():
    """
    Return an LLM that supports arbitrary structured output (Pydantic models).
    Used for recipe parsing and ingredient normalization. Requires GOOGLE_API_KEY.
    """
    if not os.environ.get("GOOGLE_API_KEY"):
        raise ValueError(
            "Set GOOGLE_API_KEY in .env for recipe parsing and ingredient normalization. "
            "Get a key at https://aistudio.google.com/app/apikey"
        )
    model = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
    return ChatGoogle(model=model)


def get_llm():
    """Alias for get_generic_llm(). Use get_browser_use_llm() for run_jumbo."""
    return get_generic_llm()
