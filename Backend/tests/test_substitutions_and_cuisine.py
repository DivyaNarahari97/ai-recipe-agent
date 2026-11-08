import json
import os
import unittest
from unittest.mock import MagicMock, patch

# Must be set before app.main loads app.db, so tests can never reach a real database.
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost/unused"

from fastapi import HTTPException

from app import main
from app.ai import RecipeGenerationError, generate_recipe, suggest_substitutes
from app.schemas import RecipeCreate
from app.substitutions import lookup_substitutes
from tests.test_ai_path import VALID, scripted


def db_with_cached(row=None):
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = row
    return db


class DictLookupTests(unittest.TestCase):
    def test_matches_plurals_and_case(self):
        self.assertEqual(lookup_substitutes("Tomatoes"), ["yogurt", "lemon juice", "tomato paste"])
        self.assertEqual(lookup_substitutes("fresh onion"), ["shallots"])

    def test_does_not_match_compound_ingredients(self):
        for name in ("peanut butter", "coconut milk", "tomato paste", "sweet potato"):
            with self.subTest(name=name):
                self.assertIsNone(lookup_substitutes(name))


class SubstitutionEndpointTests(unittest.TestCase):
    def test_dict_hit_skips_cache_and_llm(self):
        db = db_with_cached()
        with patch.object(main, "suggest_substitutes") as llm:
            result = main.get_substitutions("butter", db)
        self.assertEqual((result.source, result.substitutes), ("dict", ["oil", "ghee"]))
        llm.assert_not_called()
        db.query.assert_not_called()

    def test_cached_answer_skips_llm(self):
        db = db_with_cached(MagicMock(substitutes=["arugula"]))
        with patch.object(main, "suggest_substitutes") as llm:
            result = main.get_substitutions("Spinach", db)
        self.assertEqual((result.source, result.substitutes), ("cache", ["arugula"]))
        db.query.return_value.filter_by.assert_called_once_with(ingredient_key="spinach")
        llm.assert_not_called()

    def test_llm_answer_is_cached_under_normalized_key(self):
        db = db_with_cached()
        with patch.object(main, "suggest_substitutes", return_value=["kale", "chard"]):
            result = main.get_substitutions("Baby Spinach", db)
        self.assertEqual((result.source, result.substitutes), ("ai", ["kale", "chard"]))
        stored = db.add.call_args.args[0]
        self.assertEqual((stored.ingredient_key, stored.substitutes), ("baby spinach", ["kale", "chard"]))
        db.commit.assert_called_once()

    def test_llm_failure_returns_502_and_caches_nothing(self):
        db = db_with_cached()
        with patch.object(main, "suggest_substitutes", side_effect=RecipeGenerationError("x")):
            with self.assertRaises(HTTPException) as caught:
                main.get_substitutions("spinach", db)
        self.assertEqual(caught.exception.status_code, 502)
        db.add.assert_not_called()

    def test_empty_name_is_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            main.get_substitutions("2 cups", db_with_cached())
        self.assertEqual(caught.exception.status_code, 400)


class SuggestSubstitutesTests(unittest.TestCase):
    def test_cleans_model_output(self):
        output = json.dumps({"substitutes": [" Kale ", "kale", "", "spinach", "chard", "arugula", "beet greens"]})
        self.assertEqual(suggest_substitutes("spinach", call_model=scripted(output)), ["Kale", "chard"])

    def test_retries_then_fails_on_empty_list(self):
        empty = json.dumps({"substitutes": []})
        model = scripted(empty, empty)
        with self.assertRaises(RecipeGenerationError):
            suggest_substitutes("spinach", call_model=model)
        self.assertEqual(model.call_count, 2)


class CuisineTests(unittest.TestCase):
    def test_generated_cuisine_is_normalized(self):
        cases = {"italian": "Italian", " MIDDLE EASTERN ": "Middle Eastern", "Fusion": "Other", "": None, 7: None}
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                recipe = generate_recipe(["x"], call_model=scripted(json.dumps({**VALID, "cuisine": raw})))
                self.assertEqual(recipe.cuisine, expected)

    def test_cuisine_list_merges_legacy_spellings(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.group_by.return_value.all.return_value = [
            ("italian", 2), ("Italian", 1), ("indian", 3), ("Fusion", 1),
        ]
        result = [(c.cuisine, c.count) for c in main.get_cuisines(db)]
        self.assertEqual(result, [("Indian", 3), ("Italian", 3), ("Other", 1)])

    def test_cuisine_filter_includes_legacy_spellings(self):
        db = MagicMock()
        with patch.object(main, "_stored_cuisine_counts", return_value=[("italian", 2), ("Italian", 1), ("indian", 3)]):
            main.get_recipes(cuisine="ITALIAN", db=db)
        condition = db.query.return_value.filter.call_args.args[0]
        self.assertEqual(condition.right.value, ["italian", "Italian"])

    def test_missing_cuisine_is_allowed(self):
        recipe = generate_recipe(["x"], call_model=scripted(json.dumps(VALID)))
        self.assertIsNone(recipe.cuisine)

    def test_prompt_lists_the_allowed_cuisines(self):
        model = scripted(json.dumps(VALID))
        generate_recipe(["x"], call_model=model)
        self.assertIn('"Middle Eastern"', model.call_args.args[0])

    def test_generated_recipe_stores_cuisine(self):
        recipe = generate_recipe(["x"], call_model=scripted(json.dumps({**VALID, "cuisine": "thai"})))
        db = MagicMock()
        db.refresh.side_effect = lambda r: setattr(r, "id", 1)
        with patch.object(main, "generate_recipe", return_value=recipe), patch.object(
            main, "fetch_recipe_image", return_value=None
        ):
            stored = main.ai_generate_recipe(main.IngredientsRequest(ingredients=["x"]), db)
        self.assertEqual(stored.cuisine, "Thai")

    def test_manual_recipe_keeps_cuisine_and_no_longer_crashes_logging(self):
        db = MagicMock()
        db.refresh.side_effect = lambda r: setattr(r, "id", 1)
        payload = RecipeCreate(**{**VALID, "servings": "4", "calories": "450", "cuisine": "greek"})
        stored = main.create_recipe(payload, db)
        self.assertEqual(stored.cuisine, "Greek")


if __name__ == "__main__":
    unittest.main()
