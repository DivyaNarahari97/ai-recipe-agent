# app/ai.py
import logging
import os
from typing import Callable, TypeVar

import requests
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

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
    response = requests.post(OLLAMA_URL, json=payload, timeout=120)
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


def generate_recipe(
    ingredients: list[str],
    call_model: Callable[[str], str] = _call_model,
) -> GeneratedRecipe:
    logger.info(
        "Generating recipe with AI",
        extra={"ingredient_count": len(ingredients)}
    )
    cuisines = ", ".join(f'"{c}"' for c in CUISINES)
    prompt = f"""
You are a professional chef.

Return ONLY valid JSON in this structure:

{{
  "name": string,
  "cuisine": one of [{cuisines}],
  "servings": 2-4,
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

Generate realistic values based on the ingredients.

Ingredients:
{ingredients}
"""
    return _generate_validated(prompt, GeneratedRecipe, call_model)
