import os
import unittest
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

# Must be set before app.main loads app.db, so tests can never reach a real database.
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost/unused"

from pydantic import ValidationError

from app import main
from app.dietary import DietaryFilters
from app.pantry import PantryItem, pantry_items, rank_recipes
from app.schemas import PantryItemIn, UseItUpRequest

TODAY = date(2026, 11, 19)


def item(name, days=None):
    return PantryItemIn(name=name, expires=TODAY + timedelta(days=days) if days is not None else None)


def recipe(name, *ingredients, time="30 minutes", calories="400"):
    return SimpleNamespace(
        id=hash(name) % 1000, name=name, time=time, calories=calories, servings="2", cuisine=None,
        notes=None, image_url=None, instructions=[{"section": None, "steps": ["Cook."]}],
        ingredients=[{"quantity": "1", "name": i} for i in ingredients],
    )


def ranked_names(recipes, items, filters=None, limit=10):
    pantry, _ = pantry_items(items, TODAY)
    return [r["recipe"].name for r in rank_recipes(recipes, pantry, filters or DietaryFilters(), limit)]


class PantryItemTests(unittest.TestCase):
    def test_urgency_by_days_left(self):
        self.assertEqual(
            [PantryItem("x", d).urgency for d in (0, 1, 2, 3, 4, 7, 8, None)],
            [3, 3, 2, 2, 1, 1, 0, 0],
        )

    def test_expired_items_are_split_out(self):
        usable, expired = pantry_items([item("spinach", 1), item("yogurt", -1), item("rice")], TODAY)
        self.assertEqual([(p.name, p.days_left) for p in usable], [("spinach", 1), ("rice", None)])
        self.assertEqual(expired, ["yogurt"])

    def test_names_are_cleaned_and_deduplicated(self):
        usable, _ = pantry_items([item("  Baby   Spinach "), item("baby spinach", 2), item("of")], TODAY)
        self.assertEqual([p.name for p in usable], ["baby spinach"])


class RankTests(unittest.TestCase):
    recipes = [
        recipe("Rice Pilaf", "basmati rice", "onion"),
        recipe("Spinach Dal", "spinach", "lentils", "onion"),
        recipe("Creamy Spinach Pasta", "spinach", "milk", "pasta"),
        recipe("Tomato Soup", "tomatoes", "chicken stock"),
    ]

    def test_most_urgent_use_comes_first(self):
        items = [item("spinach", 1), item("milk", 2), item("onion"), item("rice")]
        self.assertEqual(ranked_names(self.recipes, items), ["Creamy Spinach Pasta", "Spinach Dal", "Rice Pilaf"])

    def test_without_expiry_dates_it_ranks_by_how_much_you_own(self):
        items = [item("onion"), item("rice"), item("spinach")]
        self.assertEqual(ranked_names(self.recipes, items)[0], "Rice Pilaf")

    def test_recipes_using_nothing_you_own_are_left_out(self):
        self.assertEqual(ranked_names(self.recipes, [item("tomatoes", 5)]), ["Tomato Soup"])
        self.assertEqual(ranked_names(self.recipes, [item("paneer", 1)]), [])

    def test_stock_does_not_use_up_the_chicken(self):
        self.assertEqual(ranked_names(self.recipes, [item("chicken", 0)]), [])

    def test_raw_food_does_not_count_for_a_leftover_ingredient(self):
        recipes = [recipe("Leftover Chicken Fried Rice", "leftover roast chicken", "rice")]
        self.assertEqual(ranked_names(recipes, [item("chicken", 0)]), [])
        self.assertEqual(ranked_names(recipes, [item("leftover chicken", 0)]), ["Leftover Chicken Fried Rice"])

    def test_expired_items_are_never_cooked_around(self):
        self.assertEqual(ranked_names(self.recipes, [item("spinach", -1)]), [])

    def test_result_details(self):
        pantry, _ = pantry_items([item("spinach", 1), item("onion")], TODAY)
        top = rank_recipes(self.recipes, pantry, DietaryFilters(), 1)[0]
        self.assertEqual(top["recipe"].name, "Spinach Dal")
        self.assertEqual(top["uses_expiring"], [{"name": "spinach", "days_left": 1}])
        self.assertEqual(top["uses"], ["spinach", "onion"])
        self.assertEqual(top["to_buy"], ["lentils"])

    def test_filters_and_limit_apply(self):
        recipes = self.recipes + [recipe("Chicken Spinach Curry", "chicken", "spinach")]
        items = [item("spinach", 0), item("chicken", 0)]
        self.assertEqual(ranked_names(recipes, items)[0], "Chicken Spinach Curry")
        self.assertNotIn("Chicken Spinach Curry", ranked_names(recipes, items, DietaryFilters(vegetarian=True)))
        self.assertEqual(len(ranked_names(recipes, items, limit=2)), 2)

    def test_near_duplicate_names_show_once(self):
        recipes = [recipe("Carrot Stir Fry", "carrots"), recipe("Carrot Stir-Fry", "carrots", "oil")]
        self.assertEqual(ranked_names(recipes, [item("carrots", 2)]), ["Carrot Stir Fry"])


class UseItUpEndpointTests(unittest.TestCase):
    def test_returns_ranked_recipes_expiring_and_expired(self):
        db = MagicMock()
        db.query.return_value.all.return_value = RankTests.recipes
        request = UseItUpRequest(
            items=[item("spinach", 1), item("onion", 10), item("milk", 3), item("yogurt", -3)], today=TODAY
        )
        response = main.use_it_up(request, db)
        self.assertEqual(response["results"][0]["recipe"].name, "Creamy Spinach Pasta")
        self.assertEqual(response["expiring"], [{"name": "spinach", "days_left": 1}, {"name": "milk", "days_left": 3}])
        self.assertEqual(response["expired"], ["yogurt"])

    def test_request_needs_items_and_today(self):
        with self.assertRaises(ValidationError):
            UseItUpRequest(items=[], today=TODAY)
        with self.assertRaises(ValidationError):
            UseItUpRequest(items=[{"name": "rice"}])


if __name__ == "__main__":
    unittest.main()
