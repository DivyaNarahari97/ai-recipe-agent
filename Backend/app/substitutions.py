"""Hand-picked ingredient substitutions, checked before asking the LLM."""
from typing import Optional

from app.ingredients import ingredient_tokens

SUBSTITUTIONS = {
    "tomato": ["yogurt", "lemon juice", "tomato paste"],
    "milk": ["cream", "yogurt"],
    "butter": ["oil", "ghee"],
    "onion": ["shallots"],
    "potato": ["sweet potato"],
}


def substitution_key(name: str) -> str:
    """Normalized key, so "2 Large Tomatoes" and "tomato" share one entry."""
    return " ".join(sorted(ingredient_tokens(name)))


_BY_KEY = {substitution_key(name): subs for name, subs in SUBSTITUTIONS.items()}


def lookup_substitutes(name: str) -> Optional[list[str]]:
    # Exact key match only: a partial match would offer "oil, ghee" for "peanut butter"
    # or "cream" for "coconut milk". Anything else falls through to the LLM.
    return _BY_KEY.get(substitution_key(name))
