"""Rule-based dietary checks, shared by recipe matching and the generation gate.

Rules work on ingredient names, so they also apply to recipes saved before
these filters existed. They are deliberately conservative: an ingredient that
might contain meat, animal products or gluten counts as containing it.
"""
import re
from typing import Optional

from pydantic import BaseModel, Field

from app.ingredients import ingredient_tokens

VEGETARIAN = "vegetarian"
VEGAN = "vegan"
GLUTEN_FREE = "gluten_free"


def _token_sets(*names: str) -> list[set[str]]:
    # Normalize keywords the same way as ingredient names ("noodles" -> "noodl").
    return [ingredient_tokens(name) for name in names]


_MEAT = _token_sets(
    "chicken", "beef", "pork", "lamb", "mutton", "goat", "veal", "turkey", "duck",
    "bacon", "ham", "sausage", "prosciutto", "pepperoni", "salami", "chorizo",
    "meat", "steak", "lard", "gelatin",
    "fish", "salmon", "tuna", "cod", "tilapia", "trout", "halibut", "sardine",
    "anchovy", "shrimp", "prawn", "crab", "lobster", "scallop", "clam", "mussel",
    "oyster", "squid", "octopus",
)
_ANIMAL_PRODUCTS = _token_sets(
    "egg", "milk", "butter", "buttermilk", "ghee", "cheese", "paneer", "cream",
    "yogurt", "curd", "whey", "honey", "mayonnaise", "mozzarella", "parmesan",
    "feta", "cheddar", "ricotta", "mascarpone", "cotija", "custard",
)
_GLUTEN = _token_sets(
    "wheat", "flour", "bread", "breadcrumb", "panko", "pasta", "spaghetti",
    "macaroni", "penne", "fettuccine", "linguine", "lasagna", "noodles",
    "couscous", "barley", "rye", "bulgur", "semolina", "seitan", "farro",
    "spelt", "orzo", "udon", "ramen", "soy sauce", "malt", "beer", "tortilla",
    "pita", "naan", "roti", "chapati", "cracker", "crouton", "oats",
)

# Words that make an otherwise-flagged ingredient fine, e.g. "coconut milk",
# "vegan sausage", "chickpea flour", "rice noodles".
_PLANT_BASED = {"vegan", "vegetarian", "plant", "meatless"}
_DAIRY_FREE = _PLANT_BASED | {
    "coconut", "almond", "oat", "soy", "cashew", "rice", "peanut", "cocoa",
    "tartar", "apple", "nut",
}
_GLUTEN_FREE_GRAINS = {
    "rice", "corn", "chickpea", "gram", "besan", "almond", "coconut", "buckwheat",
    "potato", "tapioca", "cassava", "quinoa", "millet", "sorghum", "tamari",
}
# Always gluten, whatever else the name says ("rice and wheat flour").
_ALWAYS_GLUTEN = ingredient_tokens("wheat rye barley seitan")


def _has_any(tokens: set[str], keyword_sets: list[set[str]]) -> bool:
    return any(keywords <= tokens for keywords in keyword_sets)


def _ingredient_name(item) -> str:
    return str(item.get("name", "") if isinstance(item, dict) else item)


def _contains_meat(tokens: set[str]) -> bool:
    return _has_any(tokens, _MEAT) and not tokens & _PLANT_BASED


def _contains_animal_product(tokens: set[str]) -> bool:
    return _has_any(tokens, _ANIMAL_PRODUCTS) and not tokens & _DAIRY_FREE


def _contains_gluten(tokens: set[str]) -> bool:
    if {"gluten", "free"} <= tokens:
        return False
    if tokens & _ALWAYS_GLUTEN:
        return True
    return _has_any(tokens, _GLUTEN) and not tokens & _GLUTEN_FREE_GRAINS


def dietary_tags(ingredients: list) -> set[str]:
    tags = {VEGETARIAN, VEGAN, GLUTEN_FREE}
    for item in ingredients or []:
        tokens = ingredient_tokens(_ingredient_name(item))
        if _contains_meat(tokens):
            tags -= {VEGETARIAN, VEGAN}
        if _contains_animal_product(tokens):
            tags.discard(VEGAN)
        if _contains_gluten(tokens):
            tags.discard(GLUTEN_FREE)
    return tags


_RANGE = r"(\d+(?:\.\d+)?)(?:\s*(?:-|–|to)\s*(\d+(?:\.\d+)?))?"
_DURATION = re.compile(_RANGE + r"\s*(hours?|hrs?|h|minutes?|mins?|m)\b", re.IGNORECASE)


def parse_minutes(text: Optional[str]) -> Optional[int]:
    """'1 hour 30 minutes' -> 90. Ranges count as their upper end."""
    if not text:
        return None
    total = 0.0
    for low, high, unit in _DURATION.findall(text):
        value = float(high or low)
        total += value * 60 if unit.lower().startswith("h") else value
    if not total:
        bare = re.search(_RANGE, text)
        if not bare:
            return None
        total = float(bare.group(2) or bare.group(1))
    return round(total) or None


def parse_calories(text: Optional[str]) -> Optional[int]:
    """'Approximately 300-350 calories per serving' -> 350."""
    if not text:
        return None
    match = re.search(_RANGE, text.replace(",", ""))
    if not match:
        return None
    return round(float(match.group(2) or match.group(1))) or None


class DietaryFilters(BaseModel):
    vegetarian: bool = False
    vegan: bool = False
    gluten_free: bool = False
    max_minutes: Optional[int] = Field(default=None, ge=1)
    max_calories: Optional[int] = Field(default=None, ge=1)

    def is_active(self) -> bool:
        return self != DietaryFilters()

    def violations(self, ingredients: list, time: Optional[str], calories: Optional[str]) -> list[str]:
        """Why a recipe fails these filters; empty if it passes."""
        problems = []
        tags = dietary_tags(ingredients)
        for wanted, tag in ((self.vegetarian, VEGETARIAN), (self.vegan, VEGAN), (self.gluten_free, GLUTEN_FREE)):
            if wanted and tag not in tags:
                problems.append(f"not {tag}")
        if self.max_minutes:
            minutes = parse_minutes(time)
            # Unknown time can't be shown to satisfy a limit, so it fails.
            if minutes is None or minutes > self.max_minutes:
                problems.append(f"time {time!r} over {self.max_minutes} min")
        if self.max_calories:
            kcal = parse_calories(calories)
            if kcal is None or kcal > self.max_calories:
                problems.append(f"calories {calories!r} over {self.max_calories}")
        return problems

    def matches(self, recipe) -> bool:
        return not self.violations(recipe.ingredients, recipe.time, recipe.calories)

    def prompt_constraints(self) -> str:
        lines = []
        if self.vegan:
            lines.append("- Vegan: no meat, seafood, eggs, dairy, honey or gelatin.")
        elif self.vegetarian:
            lines.append("- Vegetarian: no meat, poultry or seafood.")
        if self.gluten_free:
            lines.append("- Gluten-free: no wheat, barley, rye, regular pasta, bread, flour or soy sauce.")
        if self.max_minutes:
            lines.append(f"- Total time at most {self.max_minutes} minutes.")
        if self.max_calories:
            lines.append(f"- At most {self.max_calories} calories per serving.")
        if not lines:
            return ""
        return "\nThe recipe MUST meet these requirements:\n" + "\n".join(lines) + "\n"
