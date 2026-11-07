import json
import os
import unittest
from unittest.mock import MagicMock, patch

import requests

# Must be set before app.main loads app.db, so tests can never reach a real database.
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost/unused"

from fastapi import HTTPException

from app import main
from app.ai import RecipeGenerationError, generate_recipe
from app.schemas import RecipeResponse
from evals.recipe_eval import run_case, summarize

VALID = {
    "name": "Chicken Rice",
    "servings": 4,
    "time": "30 minutes",
    "calories": 450,
    "ingredients": [{"quantity": 2, "name": "chicken breasts"}, {"quantity": "1 cup", "name": "rice"}],
    "instructions": [{"section": "Cook", "steps": ["Cook everything."]}],
    "notes": "Serve hot.",
}


def without(field):
    return json.dumps({k: v for k, v in VALID.items() if k != field})


def scripted(*outputs):
    return MagicMock(side_effect=list(outputs))


class GenerateRecipeTests(unittest.TestCase):
    def test_numbers_are_coerced_to_the_string_columns(self):
        recipe = generate_recipe(["chicken"], call_model=scripted(json.dumps(VALID)))
        self.assertEqual(recipe.servings, "4")
        self.assertEqual(recipe.calories, "450")
        self.assertEqual(recipe.ingredients[0].quantity, "2")

    def test_missing_optional_fields_do_not_fail(self):
        for field in ("servings", "time", "calories", "notes"):
            recipe = generate_recipe(["chicken"], call_model=scripted(without(field)))
            self.assertIsNone(getattr(recipe, field))

    def test_retries_on_missing_required_field_then_succeeds(self):
        model = scripted(without("name"), json.dumps(VALID))
        self.assertEqual(generate_recipe(["chicken"], call_model=model).name, "Chicken Rice")
        self.assertEqual(model.call_count, 2)

    def test_rejects_shapes_the_frontend_cannot_render(self):
        bad_outputs = [
            "not json",
            without("ingredients"),
            json.dumps({**VALID, "ingredients": []}),
            json.dumps({**VALID, "ingredients": ["rice"]}),
            json.dumps({**VALID, "instructions": ["Cook."]}),
            json.dumps({**VALID, "name": "  "}),
        ]
        for bad in bad_outputs:
            with self.subTest(bad=bad), self.assertRaises(RecipeGenerationError):
                generate_recipe(["chicken"], call_model=scripted(bad, bad))

    def test_model_outage_is_not_retried(self):
        model = scripted(requests.ConnectionError())
        with self.assertRaises(RecipeGenerationError):
            generate_recipe(["chicken"], call_model=model)
        self.assertEqual(model.call_count, 1)


def fake_db():
    db = MagicMock()
    db.refresh.side_effect = lambda recipe: setattr(recipe, "id", 1)
    return db


class GenerateEndpointTests(unittest.TestCase):
    def request(self):
        return main.IngredientsRequest(ingredients=["chicken"])

    def test_image_comes_from_fetch_recipe_image(self):
        recipe = generate_recipe(["chicken"], call_model=scripted(json.dumps(VALID)))
        with patch.object(main, "generate_recipe", return_value=recipe), patch.object(
            main, "fetch_recipe_image", return_value="https://images.unsplash.com/x"
        ) as fetch:
            stored = main.ai_generate_recipe(self.request(), fake_db())

        fetch.assert_called_once_with("Chicken Rice")
        response = RecipeResponse.model_validate(stored)
        self.assertEqual(response.image_url, "https://images.unsplash.com/x")
        self.assertEqual(response.servings, "4")
        self.assertEqual(stored.ingredient_tokens, ["breast", "chicken", "rice"])

    def test_generation_failure_returns_502_and_stores_nothing(self):
        db = fake_db()
        with patch.object(main, "generate_recipe", side_effect=RecipeGenerationError("bad")):
            with self.assertRaises(HTTPException) as caught:
                main.ai_generate_recipe(self.request(), db)
        self.assertEqual(caught.exception.status_code, 502)
        db.add.assert_not_called()


class EvalScoringTests(unittest.TestCase):
    def test_retry_and_coverage_are_reported(self):
        result = run_case(
            ["chicken breast", "rice", "kale"],
            call_model=scripted("oops", json.dumps(VALID)),
        )
        self.assertEqual(result["attempts"], 2)
        self.assertFalse(result["first_attempt_json"])
        self.assertTrue(result["success"])
        self.assertEqual(result["missing"], ["kale"])
        self.assertAlmostEqual(result["coverage"], 2 / 3)

    def test_failed_cases_count_against_rates_but_not_coverage(self):
        good = run_case(["rice"], call_model=scripted(json.dumps(VALID)))
        bad = run_case(["rice"], call_model=scripted(without("name"), without("name")))
        summary = summarize([good, bad])
        self.assertEqual(summary["first_attempt_json_rate"], 1.0)
        self.assertEqual(summary["first_attempt_valid_rate"], 0.5)
        self.assertEqual(summary["success_rate_with_retry"], 0.5)
        self.assertEqual(summary["mean_coverage"], 1.0)


if __name__ == "__main__":
    unittest.main()
