import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Must be set before app.main loads app.db, so tests can never reach a real database.
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost/unused"

from fastapi import HTTPException

from app import main
from app.ai import RecipeGenerationError, refine_recipe
from app.schemas import GeneratedRecipe, RefineRequest
from tests.test_ai_path import VALID, scripted


def stored(**overrides):
    """A stored recipe matching VALID, the way the DB returns it (strings, dicts)."""
    fields = {
        "id": 7, "name": "Chicken Rice", "cuisine": None, "servings": "4", "time": "30 minutes",
        "calories": "450", "notes": "Serve hot.", "image_url": "https://img/chicken.jpg",
        "ingredients": [{"quantity": "2", "name": "chicken breasts"}, {"quantity": "1 cup", "name": "rice"}],
        "instructions": [{"section": "Cook", "steps": ["Cook everything."]}],
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def generated(**overrides):
    return GeneratedRecipe.model_validate_json(json.dumps({**VALID, **overrides}))


SIX_SERVINGS = {"servings": 6, "ingredients": [{"quantity": 3, "name": "chicken breasts"},
                                               {"quantity": "1.5 cups", "name": "rice"}]}


class RefinePromptTests(unittest.TestCase):
    def test_prompt_carries_the_current_recipe_and_the_change(self):
        model = scripted(json.dumps(VALID))
        refine_recipe(stored(), "make it for 6 people", call_model=model)
        prompt = model.call_args.args[0]
        self.assertIn('Apply this change: "make it for 6 people"', prompt)
        self.assertIn('"name": "chicken breasts"', prompt)
        self.assertIn('"servings": "4"', prompt)
        self.assertIn("including the servings\n(4)", prompt)
        self.assertIn("they are scaled automatically", prompt)
        self.assertIn('"cuisine": one of', prompt)
        # The new-recipe "2-4 servings" hint would pull edits back to 2-4 servings.
        self.assertIn('"servings": number', prompt)
        self.assertNotIn("2-4", prompt)
        self.assertNotIn("previous answer", prompt)

    def test_retry_prompt_says_the_last_answer_was_unchanged(self):
        model = scripted(json.dumps(VALID))
        refine_recipe(stored(), "spicier", call_model=model, previous_attempt_unchanged=True)
        self.assertIn("returned the recipe unchanged", model.call_args.args[0])

    def test_instruction_must_not_be_blank(self):
        for bad in ("", "   "):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                RefineRequest(instruction=bad)


class UnchangedTests(unittest.TestCase):
    def test_same_content_counts_as_unchanged(self):
        # Numbers vs strings, case, whitespace and a new name alone don't count as a change.
        self.assertTrue(main._unchanged(stored(), generated(name="Chicken Rice Bowl")))
        self.assertTrue(main._unchanged(stored(name="chicken rice "), generated()))

    def test_real_edits_count_as_changed(self):
        for change in (SIX_SERVINGS, {"time": "20 minutes"},
                       {"instructions": [{"section": "Cook", "steps": ["Pan-fry everything."]}]}):
            with self.subTest(change=change):
                self.assertFalse(main._unchanged(stored(), generated(**change)))


class RefineEndpointTests(unittest.TestCase):
    def run_endpoint(self, outputs, source=None):
        db = MagicMock()
        db.get.return_value = source if source is not None else stored()
        with patch.object(main, "refine_recipe", side_effect=outputs) as refine, \
                patch.object(main, "_store_generated_recipe", return_value="stored") as store:
            result = main.refine(7, RefineRequest(instruction="make it for 6 people"), db)
        return result, refine, store

    def test_stores_the_edit_as_a_new_recipe_with_the_original_photo(self):
        result, refine, store = self.run_endpoint([generated(**SIX_SERVINGS)])
        self.assertEqual(refine.call_args.args[1], "make it for 6 people")
        self.assertEqual(store.call_args.args[0].servings, "6")
        # The model already scaled these, so they aren't scaled again.
        self.assertEqual([i.quantity for i in store.call_args.args[0].ingredients], ["3", "1.5 cups"])
        self.assertEqual(store.call_args.kwargs["image_url"], "https://img/chicken.jpg")
        self.assertEqual(result, {"recipe": "stored", "refined_from": {"id": 7, "name": "Chicken Rice"}})

    def test_scales_quantities_the_model_left_alone(self):
        _, _, store = self.run_endpoint([generated(servings=6)])
        self.assertEqual([i.quantity for i in store.call_args.args[0].ingredients], ["3", "1 1/2 cup"])

    def test_retries_once_when_nothing_changed(self):
        _, refine, store = self.run_endpoint([generated(), generated(**SIX_SERVINGS)])
        self.assertEqual(refine.call_count, 2)
        self.assertTrue(refine.call_args.kwargs["previous_attempt_unchanged"])
        store.assert_called_once()

    def test_gives_up_with_422_and_stores_nothing(self):
        with patch.object(main, "_store_generated_recipe") as store, self.assertRaises(HTTPException) as caught:
            self.run_endpoint([generated()] * main.REFINE_ATTEMPTS)
        self.assertEqual(caught.exception.status_code, 422)
        store.assert_not_called()

    def test_missing_recipe_returns_404(self):
        db = MagicMock()
        db.get.return_value = None
        with self.assertRaises(HTTPException) as caught:
            main.refine(99, RefineRequest(instruction="spicier"), db)
        self.assertEqual(caught.exception.status_code, 404)

    def test_generation_failure_returns_502(self):
        with self.assertRaises(HTTPException) as caught:
            self.run_endpoint(RecipeGenerationError("x"))
        self.assertEqual(caught.exception.status_code, 502)


if __name__ == "__main__":
    unittest.main()
