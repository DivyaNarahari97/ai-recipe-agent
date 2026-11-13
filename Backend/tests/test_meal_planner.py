import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Must be set before app.main loads app.db, so tests can never reach a real database.
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost/unused"

from fastapi import HTTPException

from app import main
from app.ai import RecipeGenerationError, draft_meal_plan
from app.dietary import DietaryFilters
from app.meal_planner import (
    NoRecipesFit, PlannedDay, assemble, plan_meals, rank_options, review, shortlist, similar_names,
)
from app.schemas import MealPlanDraft, MealPlanRequest
from tests.test_ai_path import scripted

PANTRY = ["rice", "spinach", "onion"]


def recipe(recipe_id, name, *ingredients, time="30 min", calories="400 kcal"):
    return SimpleNamespace(
        id=recipe_id, name=name, cuisine="Indian", time=time, calories=calories,
        ingredients=[{"quantity": "1 cup", "name": n} for n in ingredients],
    )


SPINACH_RICE = recipe(1, "Spinach Rice", "rice", "spinach", "cilantro")
ONION_PULAO = recipe(2, "Onion Pulao", "rice", "onion", "cilantro")
CHICKEN_CURRY = recipe(3, "Chicken Curry", "chicken", "onion", "cream")
PALAK_DAL = recipe(4, "Palak Dal", "spinach", "lentils", "onion", "salt")
RECIPES = [
    SPINACH_RICE, ONION_PULAO, CHICKEN_CURRY, PALAK_DAL,
    recipe(5, "Spinach Rices", "rice", "spinach", "cilantro", "mint"),  # near-duplicate name, ranks lower
    recipe(6, "Fruit Salad", "apple", "banana"),
]


def answer(option, **new_dish):
    return MealPlanDraft(option=option, new_dish=new_dish or None)


def drafts(*outputs):
    return MagicMock(side_effect=list(outputs))


def no_generation(*_):
    raise AssertionError("generate should not be called")


def names(plan):
    return [d["recipe"].name for d in plan["days"]]


class ShortlistTests(unittest.TestCase):
    def test_ranks_by_pantry_use_and_drops_near_duplicates_and_filtered(self):
        shortlisted = [r.name for r in shortlist(RECIPES, PANTRY, DietaryFilters())]
        self.assertEqual(shortlisted[:3], ["Spinach Rice", "Onion Pulao", "Palak Dal"])
        self.assertNotIn("Spinach Rices", shortlisted)
        vegetarian = [r.name for r in shortlist(RECIPES, PANTRY, DietaryFilters(vegetarian=True))]
        self.assertNotIn("Chicken Curry", vegetarian)


class SimilarNameTests(unittest.TestCase):
    def test_same_dinner_under_another_name(self):
        for a, b in (("Indian Corn Khichdi", "Indian Corn Kichdi"), ("Vegetable Tacos", "Vegetable Stuffed Tacos"),
                     ("Chinese Carrot Stir Fry", "Chinese Stir-Fried Carrots"),
                     ("Potato and Coriander Salad", "Coriander and Potato Dish")):
            with self.subTest(a=a, b=b):
                self.assertTrue(similar_names(a, b))

    def test_different_dinners(self):
        for a, b in (("Spinach Rice", "Onion Rice"), ("Chicken Curry", "Paneer Curry"),
                     ("Paneer and Tomato Curry", "Chickpea Curry")):
            with self.subTest(a=a, b=b):
                self.assertFalse(similar_names(a, b))


class RankOptionsTests(unittest.TestCase):
    def test_best_option_shares_purchases_and_uses_the_pantry(self):
        options = rank_options(shortlist(RECIPES, PANTRY, DietaryFilters()), PANTRY, 2)
        self.assertEqual([r.name for r in options[0].recipes], ["Spinach Rice", "Onion Pulao"])
        self.assertEqual(options[0].plan["shopping_list"][0]["days"], [1, 2])  # cilantro, bought once

    def test_fewer_candidates_than_days_gives_shorter_options(self):
        options = rank_options([SPINACH_RICE], PANTRY, 3)
        self.assertEqual(len(options), 1)
        self.assertEqual(len(options[0].recipes), 1)


class ReviewTests(unittest.TestCase):
    options = rank_options([SPINACH_RICE, ONION_PULAO, PALAK_DAL], PANTRY, 2)

    def problems(self, draft, days=2, filters=DietaryFilters(), options=None):
        return review(draft, options or self.options, days, PANTRY, filters)

    def test_plain_option_is_fine(self):
        self.assertEqual(self.problems(answer(1)), [])

    def test_new_dish_from_the_plan_is_fine(self):
        self.assertEqual(self.problems(answer(1, replace_day=2, name="Onion Soup", ingredients=["onion", "cilantro"])), [])

    def test_catches_each_kind_of_mistake(self):
        cases = [
            (answer(9), "there is no option 9; choose 1 to 3"),
            (answer(1, replace_day=5, name="Soup", ingredients=["onion"]), "replace_day must be 1 to 2"),
            (answer(1, replace_day=2, name="Spinach Rices", ingredients=["rice"]),
             "'Spinach Rices' is the same dinner as 'Spinach Rice'"),
            (answer(1, replace_day=2, name="Fish Rice", ingredients=["fish", "rice"]), "'Fish Rice' is not vegetarian"),
            (answer(1, replace_day=2, name="Onion Pulaos", ingredients=["onion", "rice"]),
             "'Onion Pulaos' is the same dinner as 'Onion Pulao'"),
            (answer(1, replace_day=2, name="Fancy Bowl", ingredients=["quinoa", "kale", "rice"]),
             "'Fancy Bowl' needs kale, quinoa, which no other dinner uses"),
        ]
        for draft, expected in cases:
            with self.subTest(expected=expected):
                found = self.problems(draft, filters=DietaryFilters(vegetarian=True))
                self.assertTrue(any(p.startswith(expected) for p in found), found)

    def test_short_options_require_a_new_dish(self):
        short = rank_options([SPINACH_RICE], PANTRY, 2)
        self.assertEqual(self.problems(answer(1), options=short), ["day 2 needs a new dish"])
        self.assertEqual(self.problems(answer(1, name="Onion Soup", ingredients=["onion"]), options=short), [])


class PlanMealsTests(unittest.TestCase):
    def plan(self, draft, generate=no_generation, recipes=RECIPES, days=2, filters=None):
        return plan_meals(PANTRY, days, recipes, generate, filters, draft=draft)

    def test_uses_the_chosen_option_without_revision(self):
        draft = drafts(answer(2))
        result = self.plan(draft)
        self.assertEqual(draft.call_count, 1)
        options_shown = draft.call_args.args[2]
        self.assertTrue(options_shown[0].startswith("Option 1: day 1: Spinach Rice (Indian); day 2: Onion Pulao"))
        self.assertIn("Buy 1: cilantro (days 1, 2)", options_shown[0])
        self.assertEqual(len(names(result)), 2)
        self.assertNotEqual(names(result), ["Spinach Rice", "Onion Pulao"])
        self.assertTrue(result["steps"][-1].startswith("Merged the shopping lists"))

    def test_revises_once_then_keeps_the_option_without_the_bad_dish(self):
        bad = answer(1, replace_day=2, name="Fish Rice", ingredients=["fish", "rice"])
        draft = drafts(bad, bad)
        result = self.plan(draft, filters=DietaryFilters(vegetarian=True))
        self.assertIn("is not vegetarian", draft.call_args.kwargs["revision"])
        self.assertEqual(names(result), ["Spinach Rice", "Onion Pulao"])
        self.assertIn("Kept option 1 without the new dish.", result["steps"])

    def test_a_good_revision_is_used(self):
        draft = drafts(answer(9), answer(1))
        result = self.plan(draft)
        self.assertEqual(draft.call_count, 2)
        self.assertEqual(names(result), ["Spinach Rice", "Onion Pulao"])

    def test_planner_outage_uses_the_top_option(self):
        result = self.plan(drafts(RecipeGenerationError("down")))
        self.assertEqual(names(result), ["Spinach Rice", "Onion Pulao"])

    def test_new_dish_is_written_checked_and_placed(self):
        draft = drafts(answer(1, replace_day=2, name="Onion Soup", ingredients=["onion", "cilantro"]))
        too_slow = recipe(None, "Onion Soup", "onion", time="2 hours")
        quick = recipe(None, "Onion Soup", "onion", "cilantro", time="20 min")
        generate = MagicMock(side_effect=[too_slow, quick])
        result = self.plan(draft, generate, filters=DietaryFilters(max_minutes=45))
        self.assertEqual(generate.call_args.args, ("Onion Soup", ["onion", "cilantro"]))
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(names(result), ["Spinach Rice", "Onion Soup"])
        self.assertTrue(result["days"][1]["new"])

    def test_written_recipe_needing_many_new_items_is_dropped(self):
        draft = drafts(answer(1, replace_day=2, name="Onion Soup", ingredients=["onion"]))
        shopping_spree = recipe(None, "Onion Soup", "onion", "leek", "cream", "thyme", "gruyere")
        result = self.plan(draft, MagicMock(return_value=shopping_spree))
        self.assertEqual(names(result), ["Spinach Rice", "Onion Pulao"])
        self.assertIn("Day 2: couldn't write a recipe for Onion Soup that fits, so kept Onion Pulao.", result["steps"])

    def test_too_few_recipes_fills_the_last_day_with_a_new_dish(self):
        draft = drafts(answer(1, name="Onion Soup", ingredients=["onion"]))
        result = self.plan(draft, MagicMock(return_value=recipe(None, "Onion Soup", "onion")), recipes=[SPINACH_RICE])
        self.assertEqual(draft.call_args.args[3], 1)  # one day missing
        self.assertEqual(names(result), ["Spinach Rice", "Onion Soup"])

    def test_nothing_fits(self):
        with self.assertRaises(NoRecipesFit):
            self.plan(drafts(), recipes=[CHICKEN_CURRY], filters=DietaryFilters(vegetarian=True))


class AssembleTests(unittest.TestCase):
    def test_merges_lists_and_tracks_pantry_use(self):
        result = assemble([PlannedDay(1, SPINACH_RICE, False), PlannedDay(2, PALAK_DAL, False)], PANTRY + ["tofu"])
        self.assertEqual([i["name"] for i in result["shopping_list"]], ["cilantro", "lentils"])
        self.assertEqual(result["staples"], ["salt"])
        self.assertEqual(result["pantry_used"], [
            {"ingredient": "rice", "days": [1]},
            {"ingredient": "spinach", "days": [1, 2]},
            {"ingredient": "onion", "days": [2]},
        ])
        self.assertEqual(result["pantry_unused"], ["tofu"])


class PromptTests(unittest.TestCase):
    def test_prompt_has_pantry_options_rules_and_feedback(self):
        model = scripted(json.dumps({"option": 1, "new_dish": None}))
        draft_meal_plan(["rice"], 3, ["Option 1: day 1: Spinach Rice."], 0, call_model=model,
                        filters=DietaryFilters(vegan=True), revision="Your previous answer was option 9.")
        prompt = model.call_args.args[0]
        for part in ("dinners for 3 days", "already have: rice", "Option 1: day 1: Spinach Rice.",
                     "most variety", "at most one other item", "A new dish MUST", "Vegan",
                     "Your previous answer was option 9.", '"option": number'):
            self.assertIn(part, prompt)

    def test_short_plan_asks_for_a_new_last_day(self):
        model = scripted(json.dumps({"option": 1, "new_dish": {"name": "Soup", "ingredients": ["onion"]}}))
        draft_meal_plan(["rice"], 3, ["Option 1: ..."], 1, call_model=model)
        self.assertIn("only cover 2 days, so add a new dish for day 3", model.call_args.args[0])


class EndpointTests(unittest.TestCase):
    def test_cleans_pantry_and_passes_filters(self):
        db = MagicMock()
        db.query.return_value.all.return_value = RECIPES
        with patch.object(main, "plan_meals", return_value="plan") as planner:
            request = MealPlanRequest(ingredients=[" Rice", "rice", "spinach "], days=2,
                                      filters=DietaryFilters(vegan=True))
            self.assertEqual(main.meal_plan(request, db), "plan")
        args = planner.call_args.args
        self.assertEqual(args[0], ["rice", "spinach"])
        self.assertEqual(args[1], 2)
        self.assertTrue(args[4].vegan)

    def test_errors_map_to_status_codes(self):
        for error, status in ((RecipeGenerationError("x"), 502), (NoRecipesFit(), 422)):
            with self.subTest(status=status), patch.object(main, "plan_meals", side_effect=error):
                with self.assertRaises(HTTPException) as caught:
                    main.meal_plan(MealPlanRequest(ingredients=["rice"]), MagicMock())
                self.assertEqual(caught.exception.status_code, status)

    def test_blank_ingredients_are_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            main.meal_plan(MealPlanRequest(ingredients=["  "]), MagicMock())
        self.assertEqual(caught.exception.status_code, 400)

    def test_days_are_limited(self):
        with self.assertRaises(ValueError):
            MealPlanRequest(ingredients=["rice"], days=8)


if __name__ == "__main__":
    unittest.main()
