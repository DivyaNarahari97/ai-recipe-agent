# app/ai.py
import json
import logging
import os
import re

import requests
from dotenv import load_dotenv

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


def _extract_json(text: str) -> dict:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        logger.error("Model output did not contain JSON")
        raise ValueError("No JSON found in model output")
    return json.loads(match.group())


def _call_model(prompt: str) -> str:
    payload = {
    "model": "mistral",
    "prompt": prompt,
    "stream": False,
    "format": "json"
}
    logger.info("Calling model API", extra={"model": payload["model"]})
    response = requests.post(OLLAMA_URL, json=payload, timeout=120)
    response.raise_for_status()
    logger.info("Model API call completed")
    return response.json()["response"]


def generate_recipe(ingredients: list[str]) -> dict:
    logger.info(
        "Generating recipe with AI",
        extra={"ingredient_count": len(ingredients)}
    )
    prompt = f"""
You are a professional chef.

Return ONLY valid JSON in this structure:

{{
  "name": string,
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

    # First attempt
    raw_output = _call_model(prompt)

    try:
        recipe = _extract_json(raw_output)
        logger.info("Recipe JSON parsed on first attempt")
        return recipe
    except Exception:
        logger.warning("First JSON parsing attempt failed, retrying with stricter prompt")
        # Retry once with stricter reminder
        retry_prompt = prompt + "\nREMINDER: OUTPUT JSON ONLY. NO TEXT."
        raw_output = _call_model(retry_prompt)
        recipe = _extract_json(raw_output)
        logger.info("Recipe JSON parsed on retry")
        return recipe
