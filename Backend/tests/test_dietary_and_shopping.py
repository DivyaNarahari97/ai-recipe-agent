import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Must be set before app.main loads app.db, so tests can never reach a real database.
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost/unused"

from fastapi import HTTPException

from app import main
from app.ai import generate_recipe
from app.dietary import DietaryFilters, dietary_tags, parse_calories, parse_minutes
from app.schemas import RecipeResponse
from app.shopping import build_shopping_list
from tests.test_ai_path import VALID, scripted


def ing(*names):
    return [{"name": n} for n in names]


class DietaryTagTests(unittest.TestCase):
    def tags(self, *names):
        return dietary_tags(ing(*names))

    def test_plain_vegetables_get_every_tag(self):
        self.assertEqual(self.tags("carrots", "rice", "olive oil"), {"vegetarian", "vegan", "gluten_free"})

    def test_meat_and_seafood(self):
        for name in ("chicken breasts", "ground beef", "fish sauce", "shrimp", "chicken broth"):
            with self.subTest(name=name):
                self.assertNotIn("vegetarian", self.tags(name))
                self.assertNotIn("vegan", self.tags(name))

    def test_animal_products_are_vegetarian_not_vegan(self):
        for name in ("eggs", "unsalted butter", "ghee", "paneer", "honey", "grated parmesan cheese"):
            with self.subTest(name=name):
                self.assertEqual(self.tags(name), {"vegetarian", "gluten_free"})

    def test_plant_based_lookalikes(self):
        for name in ("coconut milk", "peanut butter", "almond milk", "vegan sausage", "eggplant", "cream of tartar"):
            with self.subTest(name=name):
                self.assertIn("vegan", self.tags(name))

    def test_gluten(self):
        for name in ("all-purpose flour", "pasta", "soy sauce", "egg noodles", "whole wheat bread"):
            with self.subTest(name=name):
                self.assertNotIn("gluten_free", self.tags(name))

    def test_gluten_free_lookalikes(self):
        for name in ("chickpea flour (besan)", "corn flour", "rice noodles", "tamari soy sauce", "gluten-free pasta"):
            with self.subTest(name=name):
                self.assertIn("gluten_free", self.tags(name))

    def test_wheat_is_never_excused(self):
        self.assertNotIn("gluten_free", self.tags("rice and wheat flour"))

    def test_response_exposes_tags(self):
        recipe = RecipeResponse(**{**VALID, "id": 1, "servings": "4", "calories": "450"})
        self.assertEqual(recipe.dietary_tags, ["gluten_free"])  # chicken, rice


class ParsingTests(unittest.TestCase):
    def test_minutes(self):
        cases = {
            "30 minutes": 30, "20 min": 20, "1 hour": 60, "1 hour 30 minutes": 90,
            "1.5 hours": 90, "20-30 minutes": 30, "Prep 10 mins, cook 25 mins": 35,
            "45": 45, "about an hour": None, "": None, None: None,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_minutes(text), expected)

    def test_calories(self):
        cases = {
            "Approximately 250 calories per serving": 250, "350 kcal (approx.)": 350,
            "300-350 calories per serving": 350, "1,200 kcal": 1200, "unknown": None, None: None,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_calories(text), expected)


class FilterTests(unittest.TestCase):
    def recipe(self, names=("rice", "carrots"), time="30 minutes", calories="400 kcal"):
        return SimpleNamespace(ingredients=ing(*names), time=time, calories=calories)

    def test_no_filters_match_everything(self):
        self.assertFalse(DietaryFilters().is_active())
        self.assertTrue(DietaryFilters().matches(self.recipe(("chicken",), time=None)))

    def test_each_filter(self):
        self.assertFalse(DietaryFilters(vegetarian=True).matches(self.recipe(("chicken",))))
        self.assertFalse(DietaryFilters(vegan=True).matches(self.recipe(("eggs",))))
        self.assertFalse(DietaryFilters(gluten_free=True).matches(self.recipe(("pasta",))))
        self.assertFalse(DietaryFilters(max_minutes=20).matches(self.recipe()))
        self.assertTrue(DietaryFilters(max_minutes=30).matches(self.recipe()))
        self.assertFalse(DietaryFilters(max_calories=300).matches(self.recipe()))

    def test_unknown_time_or_calories_fail_a_limit(self):
        self.assertFalse(DietaryFilters(max_minutes=60).matches(self.recipe(time=None)))
        self.assertFalse(DietaryFilters(max_calories=900).matches(self.recipe(calories="varies")))

    def test_prompt_only_changes_when_filters_are_set(self):
        plain, filtered = scripted(json.dumps(VALID)), scripted(json.dumps(VALID))
        generate_recipe(["x"], call_model=plain)
        generate_recipe(["x"], call_model=filtered, filters=DietaryFilters(vegan=True, max_minutes=20))
        self.assertNotIn("MUST", plain.call_args.args[0])
        prompt = filtered.call_args.args[0]
        self.assertIn("Vegan", prompt)
        self.assertIn("at most 20 minutes", prompt)


def stored(recipe_id, names, time="20 minutes"):
    return SimpleNamespace(
        id=recipe_id, name=f"Recipe {recipe_id}", ingredients=ing(*names), time=time, calories="300 kcal"
    )


class AssistantFilterTests(unittest.TestCase):
    def setUp(self):
        main._RECIPES_CACHE.clear()

    def run_assistant(self, db_recipes, generated, filters):
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = db_recipes
        db.query.return_value.filter.return_value.limit.return_value.all.return_value = db_recipes
        with patch.object(main, "_create_and_store_ai_recipe", side_effect=generated) as create:
            result = main.assistant_logic(["rice"], db, filters)
        return [r.id for r in result["results"]], create

    def test_database_matches_are_filtered(self):
        ids, _ = self.run_assistant(
            [stored(1, ["rice", "chicken"]), stored(2, ["rice", "peas"]), stored(3, ["rice", "tofu"]), stored(4, ["rice", "beans"])],
            generated=[],
            filters=DietaryFilters(vegetarian=True),
        )
        self.assertEqual(ids, [2, 3, 4])

    def test_generated_recipe_breaking_filters_is_not_returned(self):
        ids, create = self.run_assistant(
            [],
            generated=[stored(10, ["rice", "beef"]), stored(11, ["rice", "peas"]),
                       stored(12, ["rice", "kale"]), stored(13, ["rice", "corn"])],
            filters=DietaryFilters(vegetarian=True),
        )
        self.assertEqual(ids, [11, 12, 13])
        self.assertEqual(create.call_args.args[2], DietaryFilters(vegetarian=True))

    def test_filters_are_part_of_the_cache_key(self):
        recipes = [stored(1, ["rice", "chicken"]), stored(2, ["rice", "peas"]), stored(3, ["rice", "tofu"])]
        self.run_assistant(recipes, [], DietaryFilters())
        self.assertNotEqual(
            main._cache_key(["rice"], DietaryFilters()), main._cache_key(["rice"], DietaryFilters(vegan=True))
        )


class ShoppingListTests(unittest.TestCase):
    INGREDIENTS = [
        {"quantity": "2", "name": "chicken breasts"},
        {"quantity": "1 cup", "name": "basmati rice"},
        {"quantity": "1 tsp", "name": "salt"},
        {"quantity": "", "name": "to taste"},
        {"quantity": "1 tbsp", "name": "black beans"},
        {"quantity": "2 cups", "name": "hot water"},
    ]

    def names(self, result, group):
        return [i["name"] for i in result[group]]

    def test_splits_need_have_and_staples(self):
        result = build_shopping_list(self.INGREDIENTS, ["Chicken", "rice"])
        self.assertEqual(self.names(result, "have"), ["chicken breasts", "basmati rice"])
        self.assertEqual(self.names(result, "staples"), ["salt", "to taste", "hot water"])
        self.assertEqual(self.names(result, "need"), ["black beans"])

    def test_nothing_on_hand(self):
        result = build_shopping_list(self.INGREDIENTS, [])
        self.assertEqual(self.names(result, "need"), ["chicken breasts", "basmati rice", "black beans"])

    def test_endpoint_404s_for_unknown_recipe(self):
        db = MagicMock()
        db.get.return_value = None
        with self.assertRaises(HTTPException) as caught:
            main.get_shopping_list(99, main.ShoppingListRequest(have=[]), db)
        self.assertEqual(caught.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
