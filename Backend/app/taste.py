"""Taste profile from thumbs up/down ("likes spicy food", "avoids cilantro") that conditions generation.

The browser derives the profile from the cook's ratings and sends it with each request.
Likes only steer the prompt. Avoids are also checked in code, because a model told
"no cilantro" still sprinkles it on as a garnish; a recipe that uses one is retried.
"""
import re

from pydantic import BaseModel, Field, field_validator

from app.ingredients import ingredient_tokens

MAX_LIKES = 12
MAX_AVOIDS = 20

# Other names for the same food, so "avoids cilantro" also catches "fresh coriander leaves".
# Ground coriander and coriander seed are a different spice, which cilantro-haters are usually fine with.
_SAME_FOOD = (
    ("cilantro", "coriander leaves", "coriander leaf", "fresh coriander", "chinese parsley"),
    ("scallion", "green onion", "spring onion"),
    ("eggplant", "aubergine", "brinjal"),
    ("zucchini", "courgette"),
    ("shrimp", "prawn"),
    ("chickpea", "garbanzo"),
    ("bell pepper", "capsicum"),
)


def _clean(value: str) -> str:
    return " ".join(str(value).split()).strip(" .,;").lower()


def _names_for(avoid: str) -> list[set[str]]:
    """Token sets that count as the avoided food: its own name plus known other names."""
    own = ingredient_tokens(avoid)
    names = [own]
    for group in _SAME_FOOD:
        if any(ingredient_tokens(name) == own for name in group):
            names += [ingredient_tokens(name) for name in group]
    return [n for n in names if n]


class TasteProfile(BaseModel):
    likes: list[str] = Field(default_factory=list, max_length=MAX_LIKES)
    avoids: list[str] = Field(default_factory=list, max_length=MAX_AVOIDS)

    @field_validator("likes", "avoids")
    @classmethod
    def _tidy(cls, values: list[str]) -> list[str]:
        cleaned = [_clean(v)[:60] for v in values]
        return list(dict.fromkeys(v for v in cleaned if v))

    def is_empty(self) -> bool:
        return not self.likes and not self.avoids

    def allowing(self, wanted: list[str]) -> "TasteProfile":
        """Drop avoids the cook asked for themselves: listing mushrooms means they want mushrooms today."""
        asked = [ingredient_tokens(str(w)) for w in wanted]
        kept = [
            a for a in self.avoids
            if not any(names and tokens and (names <= tokens or tokens <= names)
                       for names in _names_for(a) for tokens in asked)
        ]
        return TasteProfile(likes=self.likes, avoids=kept)

    def violations(self, ingredients: list) -> list[str]:
        """Avoided foods the recipe uses, as reasons the model can act on; empty if none."""
        problems = []
        for avoid in self.avoids:
            names = _names_for(avoid)
            for item in ingredients or []:
                raw = str(item.get("name", "") if isinstance(item, dict) else item)
                quantity = str(item.get("quantity") or "") if isinstance(item, dict) else ""
                tokens = ingredient_tokens(raw)
                if _is_coriander_spice(avoid, raw, quantity):
                    continue
                if any(n <= tokens for n in names):
                    problems.append(f"it uses {raw.strip()!r}, and the cook avoids {avoid}")
                    break
        return problems

    def prompt_text(self, subject: str = "The recipe") -> str:
        if self.is_empty():
            return ""
        lines = ["\nThe cook's taste, learned from recipes they rated:"]
        if self.likes:
            lines.append(
                f"- They like: {', '.join(self.likes)}. Lean toward these where they suit the "
                "ingredients and the dish; don't force them in."
            )
        if self.avoids:
            lines.append(
                f"- {subject} must NOT use: {', '.join(self.avoids)}. Not even as a garnish or "
                "an optional ingredient. Use something else instead."
            )
        return "\n".join(lines) + "\n"


def _is_coriander_spice(avoid: str, raw: str, quantity: str) -> bool:
    """'ground coriander', 'coriander seeds' and '1 tsp coriander' are the spice, not the cilantro herb."""
    if ingredient_tokens(avoid) != ingredient_tokens("cilantro") or not re.search(r"\bcoriander\b", raw, re.I):
        return False
    if re.search(r"\b(leaf|leaves|sprigs?|fresh|chopped|handful|bunch)\b", f"{raw} {quantity}", re.I):
        return False
    return bool(re.search(r"\b(ground|seeds?|powder)\b", raw, re.I) or re.search(r"\b(tsp|teaspoons?)\b", quantity, re.I))
