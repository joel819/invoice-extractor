from functools import lru_cache

from app.config import get_settings


@lru_cache
def get_llm_extractor():
    """The Groq extractor, or None in demo mode (no GROQ_API_KEY)."""
    s = get_settings()
    if s.demo_mode:
        return None
    from app.extract.llm_extractor import GroqExtractor

    return GroqExtractor(s)
