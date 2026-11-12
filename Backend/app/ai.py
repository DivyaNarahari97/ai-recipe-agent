# app/ai.py
import json
import logging
import os
from typing import Callable, Optional, TypeVar

import requests
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from app.dietary import DietaryFilters
from app.schemas import CUISINES, GeneratedRecipe, GeneratedSubstitutes

ModelT = TypeVar("ModelT", bound=BaseModel)

load_dotenv()

UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
logger = logging.getLogger(__name__)


def fetch_recipe_image(recipe_name: str):
    url = "https://api.unsplash.com/search/photos"

    params = {
        "query": recipe_name + " food",
        "per_page": 1,
        "client_id": UNSPLASH_ACCESS_KEY
    }

    try:
        logger.info("Fetching recipe image from Unsplash", extra={"recipe_name": recipe_name})
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data.get("results"):
            image_url = data["results"][0]["urls"]["regular"]
            logger.info("Recipe image fetched successfully", extra={"recipe_name": recipe_name})
            return image_url

        logger.warning("No recipe image found on Unsplash", extra={"recipe_name": recipe_name})
        return None
    except requests.RequestException:
        logger.exception("Failed to fetch recipe image from Unsplash")
        return None


OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral"
MAX_ATTEMPTS = 2
# Long recipes from craving prompts took over 120s on a laptop (M3) in the RAG eval.
MODEL_TIMEOUT_SECONDS = 300


class RecipeGenerationError(Exception):
    """The model was unreachable or never produced output matching the schema."""


def _call_model(prompt: str) -> str:
    payload = {
    "model": MODEL_NAME,
    "prompt": prompt,
    "stream": False,
    "format": "json"
}
    logger.info("Calling model API", extra={"model": payload["model"]})
    response = requests.post(OLLAMA_URL, json=payload, timeout=MODEL_TIMEOUT_SECONDS)
    response.raise_for_status()
    logger.info("Model API call completed")
    return response.json()["response"]


def _generate_validated(
    prompt: str,
    schema: type[ModelT],
    call_model: Callable[[str], str],
) -> ModelT:
    """Call the model and validate against `schema`, retrying once with a stricter prompt."""
    reminder = "\nREMINDER: OUTPUT JSON ONLY. NO TEXT."
    last_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        attempt_prompt = prompt if attempt == 1 else prompt + reminder
        try:
            raw_output = call_model(attempt_prompt)
        except requests.RequestException as exc:
            # A model outage won't be fixed by a stricter prompt, so don't retry.
            raise RecipeGenerationError("Model request failed") from exc

        try:
            result = schema.model_validate_json(raw_output)
        except ValidationError as exc:
            last_error = exc
            logger.warning(
                "Model output failed validation",
                extra={"schema": schema.__name__, "attempt": attempt, "error_count": exc.error_count()},
            )
            continue

        logger.info("Model output validated", extra={"schema": schema.__name__, "attempt": attempt})
        return result

    raise RecipeGenerationError(
        f"Model output failed validation after {MAX_ATTEMPTS} attempts"
    ) from last_error


def suggest_substitutes(
    ingredient: str,
    call_model: Callable[[str], str] = _call_model,
) -> list[str]:
    logger.info("Suggesting substitutes with AI", extra={"ingredient": ingredient})
    prompt = f"""
You are a professional chef.

Suggest up to 3 common ingredients a home cook could use instead of: {ingredient}
Give each as a plain ingredient name, with no explanations or notes in parentheses.

Return ONLY valid JSON in this structure:

{{"substitutes": [string]}}
"""
    result = _generate_validated(prompt, GeneratedSubstitutes, call_model)
    # The model sometimes "substitutes" the ingredient with itself.
    return [s for s in result.substitutes if s.lower() != ingredient.strip().lower()] or result.substitutes


def _recipe_json_format(servings: str = "2-4") -> str:
    cuisines = ", ".join(f'"{c}"' for c in CUISINES)
    return f"""Return ONLY valid JSON in this structure:

{{
  "name": string,
  "cuisine": one of [{cuisines}],
  "servings": {servings},
  "time": string,
  "calories": string,
  "ingredients": [
    {{"quantity": string, "name": string}}
  ],
  "instructions": [
    {{
      "section": string,
      "steps": [string]
    }}
  ],
  "notes": string
}}
"""


def generate_recipe(
    ingredients: list[str],
    call_model: Callable[[str], str] = _call_model,
    filters: Optional[DietaryFilters] = None,
) -> GeneratedRecipe:
    logger.info(
        "Generating recipe with AI",
        extra={"ingredient_count": len(ingredients)}
    )
    prompt = f"""
You are a professional chef.

{_recipe_json_format()}
Generate realistic values based on the ingredients.

Ingredients:
{ingredients}
"""
    if filters:
        prompt += filters.prompt_constraints()
    return _generate_validated(prompt, GeneratedRecipe, call_model)


def _source_summary(recipe) -> str:
    ingredients = ", ".join(
        str(i.get("name", "")) for i in recipe.ingredients or [] if isinstance(i, dict)
    )
    details = "; ".join(
        f"{label} {value}"
        for label, value in (("cuisine", recipe.cuisine), ("time", recipe.time), ("calories", recipe.calories))
        if value
    )
    return f"- {recipe.name}" + (f" ({details})" if details else "") + f". Ingredients: {ingredients}."


def generate_from_craving(
    craving: str,
    sources: list,
    call_model: Callable[[str], str] = _call_model,
    filters: Optional[DietaryFilters] = None,
) -> GeneratedRecipe:
    """Retrieval-augmented generation: a new recipe for a craving, inspired by `sources`.

    With no sources this is plain generation from the craving, which the RAG eval
    uses as its baseline.
    """
    logger.info("Generating recipe from craving", extra={"source_count": len(sources)})
    prompt = f"""
You are a professional chef.

Create a NEW recipe for this craving: "{craving}"
"""
    if sources:
        prompt += (
            "\nThese recipes from our collection match the craving. Use them as inspiration: "
            "borrow ingredients, techniques or flavors, but do not copy any one of them.\n\n"
            + "\n".join(_source_summary(s) for s in sources)
            + "\n"
        )
    prompt += "\n" + _recipe_json_format()
    if filters:
        prompt += filters.prompt_constraints()
    return _generate_validated(prompt, GeneratedRecipe, call_model)


REFINE_FIELDS = ("name", "cuisine", "servings", "time", "calories", "ingredients", "instructions", "notes")


def refine_recipe(
    recipe,
    instruction: str,
    call_model: Callable[[str], str] = _call_model,
    previous_attempt_unchanged: bool = False,
) -> GeneratedRecipe:
    """Edit an existing recipe ("for 6 people", "spicier", "no oven") instead of starting over."""
    logger.info("Refining recipe", extra={"recipe_id": getattr(recipe, "id", None)})
    current = json.dumps({field: getattr(recipe, field, None) for field in REFINE_FIELDS}, indent=2)
    prompt = f"""
You are a professional chef editing an existing recipe.

Current recipe (JSON):
{current}

Apply this change: "{instruction}"

Keep everything the change doesn't affect exactly as it is, including the servings
({recipe.servings or "unknown"}) and the ingredient quantities.
Update everything the change does affect:
- If the servings change, update "servings" but leave the quantities of existing
  ingredients as they are; they are scaled automatically afterwards.
- Rewrite steps that use equipment or techniques the change rules out.
- Update the time and calories if they change.
Rename the recipe only if the old name would no longer be accurate.
Return the complete updated recipe, not just the changes.
"""
    if previous_attempt_unchanged:
        prompt += "\nYour previous answer returned the recipe unchanged. You must apply the change.\n"
    prompt += "\n" + _recipe_json_format(servings="number")
    return _generate_validated(prompt, GeneratedRecipe, call_model)
