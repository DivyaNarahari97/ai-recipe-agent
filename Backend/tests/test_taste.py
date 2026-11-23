import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Must be set before app.main loads app.db, so tests can never reach a real database.
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost/unused"

from fastapi import HTTPException
from pydantic import ValidationError

from app import main
from app.ai import generate_recipe
from app.dietary import DietaryFilters
from app.leftovers import make_leftover_dish, parse_leftovers
from app.meal_planner import plan_meals, shortlist
from app.schemas import GeneratedRecipe, MealPlanDraft
from app.taste import TasteProfile
from tests.test_ai_path import VALID, scripted

NO_CILANTRO = TasteProfile(likes=["spicy food"], avoids=["cilantro"])


def ing(*names):
    return [{"quantity": "1", "name": n} for n in names]


def generated(name="Chicken Rice", *ingredients):
    return GeneratedRecipe(**{**VALID, "name": name, "ingredients": ing(*(ingredients or ("chicken", "rice")))})


class ViolationTests(unittest.TestCase):
    def test_finds_the_avoided_food_and_its_other_names(self):
        for name in ("cilantro", "Fresh cilantro, chopped", "coriander leaves", "fresh coriander", "chopped coriander"):
            with self.subTest(name=name):
                self.assertTrue(NO_CILANTRO.violations(ing("rice", name)))

    def test_coriander_spice_is_not_cilantro(self):
        self.assertEqual(NO_CILANTRO.violations(ing("ground coriander", "coriander seeds")), [])
        self.assertEqual(NO_CILANTRO.violations([{"quantity": "1 tsp", "name": "coriander"}]), [])
        # Avoiding coriander itself still rules out the spice.
        self.assertTrue(TasteProfile(avoids=["coriander"]).violations(ing("ground coriander")))

    def test_matches_plurals_and_dishes_made_from_it(self):
        profile = TasteProfile(avoids=["mushroom"])
        self.assertTrue(profile.violations(ing("cremini mushrooms")))
        self.assertTrue(profile.violations(ing("mushroom broth")))
        self.assertEqual(profile.violations(ing("rice", "onion")), [])

    def test_reason_names_the_ingredient(self):
        self.assertEqual(
            NO_CILANTRO.violations(ing("rice", "cilantro for garnish")),
            ["it uses 'cilantro for garnish', and the cook avoids cilantro"],
        )

    def test_foods_asked_for_today_are_allowed(self):
        self.assertEqual(NO_CILANTRO.allowing(["chicken", "Cilantro"]).avoids, [])
        self.assertEqual(NO_CILANTRO.allowing(["fresh coriander"]).avoids, [])
        self.assertEqual(NO_CILANTRO.allowing(["something with cilantro and lime"]).avoids, [])
        self.assertEqual(NO_CILANTRO.allowing(["chicken"]).avoids, ["cilantro"])

    def test_profile_is_tidied_and_capped(self):
        profile = TasteProfile(likes=["  Spicy   food ", "spicy food", ""], avoids=["Cilantro."])
        self.assertEqual((profile.likes, profile.avoids), (["spicy food"], ["cilantro"]))
        with self.assertRaises(ValidationError):
            TasteProfile(avoids=[f"food {i}" for i in range(30)])


class PromptTests(unittest.TestCase):
    def test_profile_goes_into_the_prompt(self):
        model = scripted(json.dumps(VALID))
        generate_recipe(["chicken"], call_model=model, profile=NO_CILANTRO)
        prompt = model.call_args.args[0]
        self.assertIn("They like: spicy food", prompt)
        self.assertIn("must NOT use: cilantro", prompt)

    def test_no_profile_leaves_the_prompt_alone(self):
        plain, empty = scripted(json.dumps(VALID)), scripted(json.dumps(VALID))
        generate_recipe(["chicken"], call_model=plain)
        generate_recipe(["chicken"], call_model=empty, profile=TasteProfile())
        self.assertEqual(plain.call_args.args[0], empty.call_args.args[0])

    def test_rejection_reason_goes_into_the_retry(self):
        model = scripted(json.dumps(VALID))
        generate_recipe(["chicken"], call_model=model, rejected=["it uses 'cilantro', and the cook avoids cilantro"])
        self.assertIn("rejected because it uses 'cilantro'", model.call_args.args[0])


def stored_db():
    db = MagicMock()
    db.refresh.side_effect = lambda r: setattr(r, "id", 1)
    return db


class GenerateEndpointTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(main, "fetch_recipe_image", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_retries_once_with_the_reason(self):
        attempts = [generated("Chicken Rice", "chicken", "cilantro"), generated("Chicken Rice", "chicken", "parsley")]
        with patch.object(main, "generate_recipe", side_effect=attempts) as gen:
            recipe = main.ai_generate_recipe(
                main.IngredientsRequest(ingredients=["chicken"], profile=NO_CILANTRO), stored_db()
            )
        self.assertEqual([i["name"] for i in recipe.ingredients], ["chicken", "parsley"])
        self.assertIsNone(gen.call_args_list[0].kwargs["rejected"])
        self.assertIn("avoids cilantro", gen.call_args_list[1].kwargs["rejected"][0])

    def test_gives_up_with_422_when_the_retry_still_uses_it(self):
        with patch.object(main, "generate_recipe", return_value=generated("X", "chicken", "cilantro")) as gen:
            with self.assertRaises(HTTPException) as caught:
                main.ai_generate_recipe(main.IngredientsRequest(ingredients=["chicken"], profile=NO_CILANTRO), stored_db())
        self.assertEqual((caught.exception.status_code, gen.call_count), (422, 2))

    def test_asking_for_the_food_overrides_the_avoid(self):
        with patch.object(main, "generate_recipe", return_value=generated("X", "chicken", "cilantro")) as gen:
            main.ai_generate_recipe(
                main.IngredientsRequest(ingredients=["chicken", "cilantro"], profile=NO_CILANTRO), stored_db()
            )
        self.assertEqual(gen.call_count, 1)
        self.assertEqual(gen.call_args.kwargs["profile"].avoids, [])


class AssistantTests(unittest.TestCase):
    def test_stored_recipes_with_an_avoided_food_are_skipped(self):
        main._RECIPES_CACHE.clear()
        with_cilantro = SimpleNamespace(id=1, name="Cilantro Rice", time="20 min", calories="300",
                                        ingredients=ing("rice", "cilantro"))
        plain = SimpleNamespace(id=2, name="Lemon Rice", time="20 min", calories="300", ingredients=ing("rice", "lemon"))
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [with_cilantro, plain]
        with patch.object(main, "_create_and_store_ai_recipe", side_effect=RuntimeError("stop")):
            result = main.assistant_logic(["rice"], db, profile=TasteProfile(avoids=["cilantro"]))
        self.assertEqual([r.name for r in result["results"]], ["Lemon Rice"])

    def test_profile_is_part_of_the_cache_key(self):
        self.assertNotEqual(main._cache_key(["rice"], DietaryFilters()),
                            main._cache_key(["rice"], DietaryFilters(), NO_CILANTRO))


class CravingTests(unittest.TestCase):
    def test_avoided_food_is_retried_with_the_reason(self):
        attempts = [generated("Taco Bowl", "beans", "cilantro"), generated("Taco Bowl", "beans", "lime")]
        db = stored_db()
        with patch.object(main, "semantic_search", return_value=[]), \
                patch.object(main, "fetch_recipe_image", return_value=None), \
                patch.object(main, "generate_from_craving", side_effect=attempts) as gen:
            response = main.generate_for_craving(
                main.CravingRecipeRequest(query="tacos", profile=NO_CILANTRO), db
            )
        self.assertEqual([i["name"] for i in response["recipe"].ingredients], ["beans", "lime"])
        self.assertIn("avoids cilantro", gen.call_args_list[1].kwargs["rejected"][0])


class LeftoverTests(unittest.TestCase):
    def test_leftover_dish_is_checked_against_the_profile(self):
        leftovers = parse_leftovers("leftover rice")
        attempts = [generated("Fried Rice", "leftover rice", "egg", "cilantro"),
                    generated("Fried Rice", "leftover rice", "egg", "scallions")]
        generate = MagicMock(side_effect=attempts)
        recipe, used = make_leftover_dish(leftovers, DietaryFilters(), generate, profile=NO_CILANTRO)
        self.assertEqual(used, 2)
        self.assertIs(generate.call_args.kwargs["profile"], NO_CILANTRO)
        self.assertTrue(any("avoids cilantro" in r for r in generate.call_args.kwargs["rejected"]))


class MealPlanTests(unittest.TestCase):
    recipes = [
        SimpleNamespace(id=1, name="Cilantro Rice", time="20 min", calories="300", ingredients=ing("rice", "cilantro")),
        SimpleNamespace(id=2, name="Spinach Dal", time="20 min", calories="300", ingredients=ing("spinach", "lentils")),
        SimpleNamespace(id=3, name="Rice Pilaf", time="20 min", calories="300", ingredients=ing("rice", "onion")),
    ]

    def test_shortlist_skips_avoided_foods(self):
        names = [r.name for r in shortlist(self.recipes, ["rice"], DietaryFilters(), profile=TasteProfile(avoids=["cilantro"]))]
        self.assertNotIn("Cilantro Rice", names)

    def test_new_dish_is_not_given_the_avoided_food(self):
        draft = MagicMock(return_value=MealPlanDraft(
            option=1, new_dish={"name": "Rice Bowl", "ingredients": ["rice", "cilantro"]}
        ))
        dish = SimpleNamespace(id=9, name="Rice Bowl", time="20 min", calories="300", ingredients=ing("rice", "onion"))
        generate = MagicMock(return_value=dish)
        plan_meals(["rice", "spinach", "onion"], 3, self.recipes, generate, DietaryFilters(), draft=draft,
                   profile=TasteProfile(avoids=["cilantro"]))
        self.assertEqual(generate.call_args.args, ("Rice Bowl", ["rice"]))
        self.assertIn("profile", draft.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
