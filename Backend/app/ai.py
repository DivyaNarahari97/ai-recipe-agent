# app/ai.py
import requests
import json
import re

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral"


def _extract_json(text: str) -> dict:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("No JSON found in model output")
    return json.loads(match.group())


def _call_model(prompt: str) -> str:
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False
    }
    response = requests.post(OLLAMA_URL, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()["response"]


def generate_recipe(ingredients: list[str]) -> dict:
    prompt = f"""
You are a JSON API.

You MUST respond with valid JSON ONLY.
DO NOT add any text before or after JSON.

If you cannot comply, return an EMPTY JSON object: {{}}.

JSON schema:
{{
  "name": string,
  "ingredients": list of strings,
  "steps": list of strings,
  "estimated_calories": number
}}

Rules:
- Use ONLY the provided ingredients
- Steps must be short, clear actions
- DO NOT number steps
- One action per step
- Do NOT include cooking tips or explanations
- Calories must be a realistic estimate

Ingredients:
{", ".join(ingredients)}
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
