"""Ingredient name normalization shared by recipe matching and the eval."""
import re

_IGNORED_INGREDIENT_WORDS = {
    "fresh",
    "small",
    "medium",
    "large",
    "chopped",
    "diced",
    "sliced",
    "minced",
    "ground",
    "to",
    "taste",
    "cup",
    "cups",
    "tbsp",
    "tsp",
    "tablespoon",
    "tablespoons",
    "teaspoon",
    "teaspoons",
    "gram",
    "grams",
    "ml",
    "kg",
    "g",
    "oz",
    "of",
}


def _normalize_word(word: str) -> str:
    token = word.strip().lower()
    if not token:
        return ""
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("es") and len(token) > 4:
        return token[:-2]
    if token.endswith("s") and len(token) > 3:
        return token[:-1]
    return token


def ingredient_tokens(name: str) -> set[str]:
    words = re.findall(r"[a-zA-Z]+", name.lower())
    tokens: set[str] = set()
    for word in words:
        if word in _IGNORED_INGREDIENT_WORDS:
            continue
        normalized = _normalize_word(word)
        if normalized and normalized not in _IGNORED_INGREDIENT_WORDS:
            tokens.add(normalized)
    return tokens


def extract_normalized_ingredient_tokens(ingredients: list) -> set[str]:
    tokens: set[str] = set()
    for item in ingredients or []:
        if isinstance(item, dict):
            raw_name = str(item.get("name", "")).strip()
        else:
            raw_name = str(item).strip()
        if raw_name:
            tokens.update(ingredient_tokens(raw_name))
    return tokens
