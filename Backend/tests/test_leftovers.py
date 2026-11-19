import json
import os
import unittest
from unittest.mock import MagicMock, patch

# Must be set before app.main loads app.db, so tests can never reach a real database.
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost/unused"

from fastapi import HTTPException

from app import main
from app.ai import RecipeGenerationError, generate_from_leftovers
from app.dietary import DietaryFilters
from app.leftovers import (
    LEFTOVER_ATTEMPTS,
    NoLeftovers,
    add_safety_note,
    extra_ingredients,
    leftover_problems,
    mark_leftovers,
    parse_leftovers,
)
from app.schemas import GeneratedRecipe, LeftoversRequest
from tests.test_ai_path import VALID, scripted


def parsed(text):
    return [(l.text, l.name) for l in parse_leftovers(text)]


def names(*items):
    return [{"name": item} for item in items]


def recipe(name="Chicken Fried Rice", ingredients=("leftover rice", "leftover roast chicken, shredded", "eggs")):
    return GeneratedRecipe.model_validate_json(json.dumps({
        **VALID,
        "name": name,
        "ingredients": [{"quantity": "1 cup", "name": i} for i in ingredients],
    }))


CHICKEN_AND_RICE = "I have half a roast chicken and rice"


class ParseLeftoversTests(unittest.TestCase):
    def test_splits_a_sentence_and_keeps_the_amount(self):
        self.assertEqual(parsed(CHICKEN_AND_RICE), [("half a roast chicken", "chicken"), ("rice", "rice")])

    def test_drops_lead_ins_and_tails(self):
        self.assertEqual(
            parsed("leftover pasta and some steamed broccoli from last night"),
            [("pasta", "pasta"), ("steamed broccoli", "broccoli")],
        )
        self.assertEqual(
            parsed("There is some rotisserie chicken, a bowl of mashed potatoes & cold rice left over"),
            [("rotisserie chicken", "chicken"), ("a bowl of mashed potatoes", "potatoes"), ("cold rice", "rice")],
        )

    def test_lines_and_plus_signs_separate_items(self):
        self.assertEqual(
            parsed("I've got leftover chili\nhalf a baguette\nsour cream"),
            [("chili", "chili"), ("half a baguette", "baguette"), ("sour cream", "sour cream")],
        )
        self.assertEqual(parsed("pulled pork + coleslaw"), [("pulled pork", "pork"), ("coleslaw", "coleslaw")])

    def test_containers_are_amounts_not_food(self):
        self.assertEqual(
            parsed("half a pot of chili and a tray of roasted vegetables"),
            [("half a pot of chili", "chili"), ("a tray of roasted vegetables", "vegetables")],
        )

    def test_dishes_named_with_and_stay_whole(self):
        self.assertEqual(parsed("mac and cheese, 2 hot dogs"), [("mac and cheese", "mac cheese"), ("2 hot dogs", "hot dogs")])

    def test_duplicates_collapse(self):
        self.assertEqual(parsed("rice, cold rice"), [("rice", "rice")])

    def test_nothing_usable_raises(self):
        for text in ("", "leftovers", "some"):
            with self.subTest(text=text), self.assertRaises(NoLeftovers):
                parse_leftovers(text)


class LeftoverProblemsTests(unittest.TestCase):
    leftovers = parse_leftovers(CHICKEN_AND_RICE)

    def problems(self, name, *ingredients):
        return leftover_problems(name, names(*ingredients), self.leftovers)

    def test_a_new_dish_using_everything_passes(self):
        self.assertEqual(
            self.problems("Chicken Fried Rice", "cooked rice", "roast chicken, shredded", "eggs", "frozen peas",
                          "soy sauce", "scallions", "garlic", "vegetable oil"),
            [],
        )

    def test_a_missing_leftover_is_named(self):
        problems = self.problems("Chicken Tacos", "shredded chicken", "tortillas", "salsa")
        self.assertEqual(len(problems), 1)
        self.assertIn("leaves out: rice", problems[0])

    def test_stock_is_not_the_leftover_chicken(self):
        problems = self.problems("Rice Soup", "chicken stock", "rice", "carrots")
        self.assertIn("leaves out: half a roast chicken", problems[0])

    def test_the_same_meal_reheated_is_rejected(self):
        for name in ("Roast Chicken and Rice", "Chicken & Rice Bowl", "Leftover Chicken with Rice"):
            with self.subTest(name=name):
                problems = self.problems(name, "chicken", "rice")
                self.assertTrue(any("reheated" in p for p in problems), problems)

    def test_plurals_match_singulars(self):
        veg = parse_leftovers("roasted vegetables and couscous")
        self.assertEqual(leftover_problems("Couscous Salad", names("leftover roasted vegetable", "couscous"), veg), [])
        reheated = leftover_problems("Roasted Vegetable and Couscous Dish", names("roasted vegetables", "couscous"), veg)
        self.assertTrue(any("reheated" in p for p in reheated), reheated)

    def test_too_much_shopping_is_rejected(self):
        problems = self.problems("Chicken Burrito Bowl", "leftover chicken", "rice", "black beans", "corn",
                                 "avocado", "salsa", "cheese")
        self.assertEqual(len(problems), 1)
        self.assertIn("needs 5 ingredients", problems[0])

    def test_pantry_staples_are_not_shopping(self):
        self.assertEqual(
            extra_ingredients(names("leftover rice", "salt", "olive oil", "garlic cloves", "chili powder",
                                    "chicken stock", "eggs"), self.leftovers),
            ["chicken stock", "eggs"],
        )

    def test_prep_notes_dont_make_a_staple_an_extra(self):
        self.assertEqual(
            extra_ingredients(names("medium onion, finely diced", "scallions, chopped", "ground ginger"), self.leftovers),
            ["scallions", "ground ginger"],
        )


class MarkAndNoteTests(unittest.TestCase):
    def test_leftover_ingredients_are_labelled(self):
        dish = recipe(ingredients=("rice", "cooked chicken", "chicken stock", "eggs"))
        mark_leftovers(dish.ingredients, parse_leftovers(CHICKEN_AND_RICE))
        self.assertEqual([i.name for i in dish.ingredients], ["leftover rice", "cooked chicken", "chicken stock", "eggs"])

    def test_safety_note_is_added_after_the_models_note(self):
        self.assertTrue(add_safety_note("Serve hot.").startswith("Serve hot.\n\nLeftovers:"))
        self.assertIn("165°F", add_safety_note(None))


class LeftoverPromptTests(unittest.TestCase):
    def test_prompt_lists_leftovers_as_cooked_and_limits_shopping(self):
        model = scripted(json.dumps(VALID))
        generate_from_leftovers(["half a roast chicken", "rice"], call_model=model, max_extra=4)
        prompt = model.call_args.args[0]
        self.assertIn("- half a roast chicken\n- rice", prompt)
        self.assertIn("already cooked", prompt)
        self.assertIn("at most 4 other ingredients", prompt)
        self.assertNotIn("rejected", prompt)

    def test_retry_prompt_carries_the_reasons(self):
        model = scripted(json.dumps(VALID))
        generate_from_leftovers(["rice"], call_model=model, rejected=["it leaves out: rice", "not vegetarian"])
        self.assertIn("rejected because it leaves out: rice; and not vegetarian", model.call_args.args[0])

    def test_filters_go_into_the_prompt(self):
        model = scripted(json.dumps(VALID))
        generate_from_leftovers(["rice"], call_model=model, filters=DietaryFilters(vegan=True))
        self.assertIn("Vegan", model.call_args.args[0])


class LeftoverEndpointTests(unittest.TestCase):
    def run_endpoint(self, outputs, text=CHICKEN_AND_RICE, filters=None):
        request = LeftoversRequest(leftovers=text, filters=filters or DietaryFilters())
        with patch.object(main, "generate_from_leftovers", side_effect=outputs) as generate, \
                patch.object(main, "_store_generated_recipe", side_effect=lambda r, db: r) as store:
            result = main.transform_leftovers(request, MagicMock())
        return result, generate, store

    def test_returns_the_dish_with_leftovers_marked_and_a_safety_note(self):
        result, generate, store = self.run_endpoint([recipe(ingredients=("rice", "roast chicken", "eggs", "peas"))])
        self.assertEqual(generate.call_count, 1)
        dish = result["recipe"]
        self.assertEqual([i.name for i in dish.ingredients], ["leftover rice", "leftover roast chicken", "eggs", "peas"])
        self.assertIn("165°F", dish.notes)
        self.assertEqual(result["leftovers"], [{"text": "half a roast chicken", "name": "chicken"},
                                               {"text": "rice", "name": "rice"}])
        self.assertEqual(result["to_buy"], ["eggs", "peas"])

    def test_retries_with_the_reasons_then_succeeds(self):
        reheated = recipe(name="Roast Chicken and Rice", ingredients=("chicken", "rice"))
        result, generate, _ = self.run_endpoint([reheated, recipe()])
        self.assertEqual(generate.call_count, 2)
        self.assertIsNone(generate.call_args_list[0].kwargs["rejected"])
        self.assertIn("reheated", generate.call_args_list[1].kwargs["rejected"][0])
        self.assertEqual(result["recipe"].name, "Chicken Fried Rice")

    def test_gives_up_with_422_and_stores_nothing(self):
        missing_rice = recipe(name="Chicken Tacos", ingredients=("leftover chicken", "tortillas"))
        with patch.object(main, "generate_from_leftovers", side_effect=[missing_rice] * LEFTOVER_ATTEMPTS), \
                patch.object(main, "_store_generated_recipe") as store, \
                self.assertRaises(HTTPException) as caught:
            main.transform_leftovers(LeftoversRequest(leftovers=CHICKEN_AND_RICE), MagicMock())
        self.assertEqual(caught.exception.status_code, 422)
        store.assert_not_called()

    def test_filters_are_checked_on_the_dish(self):
        with_bacon = recipe(ingredients=("leftover rice", "leftover tofu", "bacon"))
        vegetarian = DietaryFilters(vegetarian=True)
        result, generate, _ = self.run_endpoint(
            [with_bacon, recipe(ingredients=("leftover rice", "leftover tofu", "peas"))],
            text="tofu and rice", filters=vegetarian,
        )
        self.assertEqual(generate.call_count, 2)
        self.assertIn("not vegetarian", generate.call_args_list[1].kwargs["rejected"])

    def test_leftovers_that_break_the_diet_are_refused_before_calling_the_model(self):
        with patch.object(main, "generate_from_leftovers") as generate, self.assertRaises(HTTPException) as caught:
            main.transform_leftovers(
                LeftoversRequest(leftovers=CHICKEN_AND_RICE, filters=DietaryFilters(vegetarian=True)), MagicMock()
            )
        self.assertEqual(caught.exception.status_code, 422)
        self.assertIn("aren't vegetarian", caught.exception.detail)
        generate.assert_not_called()

    def test_no_food_in_the_text_is_a_400(self):
        with self.assertRaises(HTTPException) as caught:
            main.transform_leftovers(LeftoversRequest(leftovers="leftovers"), MagicMock())
        self.assertEqual(caught.exception.status_code, 400)

    def test_generation_failure_is_a_502(self):
        with self.assertRaises(HTTPException) as caught:
            self.run_endpoint(RecipeGenerationError("down"))
        self.assertEqual(caught.exception.status_code, 502)


if __name__ == "__main__":
    unittest.main()
