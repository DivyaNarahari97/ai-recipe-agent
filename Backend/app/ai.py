# app/ai.py
import requests
import json
import re
import os
import requests
from dotenv import load_dotenv

load_dotenv()

UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")


def fetch_recipe_image(recipe_name: str):
    url = "https://api.unsplash.com/search/photos"

    params = {
        "query": recipe_name + " food",
        "per_page": 1,
        "client_id": UNSPLASH_ACCESS_KEY
    }

    response = requests.get(url, params=params)

    if response.status_code == 200:
        data = response.json()
        if data["results"]:
            return data["results"][0]["urls"]["regular"]

    return None


OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral"


def _extract_json(text: str) -> dict:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("No JSON found in model output")
    return json.loads(match.group())


def _call_model(prompt: str) -> str:
    payload = {
    "model": "mistral",
    "prompt": prompt,
    "stream": False,
    "format": "json"
}
    response = requests.post(OLLAMA_URL, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()["response"]


def generate_recipe(ingredients: list[str]) -> dict:
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
        return _extract_json(raw_output)
    except Exception:
        # Retry once with stricter reminder
        retry_prompt = prompt + "\nREMINDER: OUTPUT JSON ONLY. NO TEXT."
        raw_output = _call_model(retry_prompt)
        return _extract_json(raw_output)
