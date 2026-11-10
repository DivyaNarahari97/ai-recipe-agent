"""Text embeddings via Ollama, and the text each recipe is embedded as."""
import hashlib
import logging

import requests

from app.dietary import GLUTEN_FREE, VEGAN, VEGETARIAN, dietary_tags, parse_calories, parse_minutes
from app.ingredients import extract_normalized_ingredient_tokens, ingredient_tokens

logger = logging.getLogger(__name__)

OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768

# nomic-embed-text is trained with these task prefixes; leaving them off hurts retrieval.
QUERY_PREFIX = "search_query: "
DOCUMENT_PREFIX = "search_document: "

_MAX_DOCUMENT_CHARS = 2000
_DIET_WORDS = {VEGETARIAN: "vegetarian", VEGAN: "vegan", GLUTEN_FREE: "gluten-free"}
# Normalized like ingredient names, so plurals match ("chillies" -> "chilly").
_SPICY = ingredient_tokens(
    "chili chilies chilli chillies chile chiles cayenne jalapeno jalapenos "
    "sriracha gochujang harissa chipotle"
)


class EmbeddingError(Exception):
    """The embedding model was unreachable or returned something unusable."""


def embed(texts: list[str]) -> list[list[float]]:
    try:
        response = requests.post(
            OLLAMA_EMBED_URL, json={"model": EMBED_MODEL, "input": texts}, timeout=120
        )
        response.raise_for_status()
        vectors = response.json()["embeddings"]
    except (requests.RequestException, KeyError, ValueError) as exc:
        raise EmbeddingError("Embedding request failed") from exc
    if len(vectors) != len(texts) or any(len(v) != EMBED_DIM for v in vectors):
        raise EmbeddingError("Embedding response had the wrong shape")
    return vectors


def descriptors(recipe) -> list[str]:
    """Plain words for properties an embedding can't infer from numbers like "250 kcal"."""
    words = []
    kcal = parse_calories(recipe.calories)
    minutes = parse_minutes(recipe.time)
    if kcal is not None and kcal <= 350:
        words.append("light")
    if kcal is not None and kcal >= 600:
        words.append("hearty")
    if minutes is not None and minutes <= 20:
        words.append("quick")
    if extract_normalized_ingredient_tokens(recipe.ingredients) & _SPICY:
        words.append("spicy")
    return words


def recipe_document(recipe, include_descriptors: bool = True) -> str:
    ingredients = ", ".join(str(i.get("name", "")) for i in recipe.ingredients or [] if isinstance(i, dict))
    steps = " ".join(
        step for section in recipe.instructions or [] if isinstance(section, dict)
        for step in section.get("steps") or []
    )
    tags = [_DIET_WORDS[t] for t in sorted(dietary_tags(recipe.ingredients))]
    parts = [
        f"{recipe.name}.",
        f"Cuisine: {recipe.cuisine}." if recipe.cuisine else "",
        f"Dietary: {', '.join(tags)}." if tags else "",
        f"Style: {', '.join(descriptors(recipe))}." if include_descriptors and descriptors(recipe) else "",
        f"Time: {recipe.time}." if recipe.time else "",
        f"Calories: {recipe.calories}." if recipe.calories else "",
        f"Ingredients: {ingredients}.",
        f"Notes: {recipe.notes}" if recipe.notes else "",
        f"Steps: {steps}" if steps else "",
    ]
    return " ".join(p for p in parts if p)[:_MAX_DOCUMENT_CHARS]


def content_hash(document: str) -> str:
    return hashlib.sha256(f"{EMBED_MODEL}\n{document}".encode()).hexdigest()
