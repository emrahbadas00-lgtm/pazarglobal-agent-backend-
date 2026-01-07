"""Shared AsyncOpenAI client factory used by service modules."""
from __future__ import annotations

from openai import AsyncOpenAI
from functools import lru_cache
import os


@lru_cache(maxsize=1)
def get_openai_client() -> AsyncOpenAI:
    """Return a cached AsyncOpenAI client instance.

    The Agents SDK already configures the OPENAI_API_KEY environment variable,
    so we simply rely on default environment resolution here to avoid passing
    redundant credentials around the codebase.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    return AsyncOpenAI(api_key=api_key)
