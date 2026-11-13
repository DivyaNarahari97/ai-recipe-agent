"""Meal-planner agent: your ingredients + N days → dinners that share ingredients, and one shopping list.

Code does the search; the model does the judgment.

1. Shortlist stored recipes that fit the dietary filters, ranked by how much of the pantry they use.
2. Try every combination of N shortlisted dinners and keep the few best: fewest items to buy,
   most of the pantry used, most purchases shared across days.
3. The model picks one of those options for variety, and may swap in one new dish to use up
   leftovers, built from the pantry and the option's shopping list.
4. Its answer is checked in code (valid option, dietary rules, no near-duplicate dinners, few extra
   purchases); problems go back to it for one revision.
5. A new dish is written as a full recipe and checked again against the filters and the shopping list.
6. The days' shopping lists are merged into one.

An earlier version let the model compose the plan from a recipe list. In the eval it bought
8 items per plan and shared 0.6 across days; a search over combinations bought 3.5 and shared 2.2.
"""
import itertools
import logging
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable, Optional

from app.ai import RecipeGenerationError, draft_meal_plan
from app.dietary import DietaryFilters
from app.ingredients import ingredient_tokens
from app.schemas import MealPlanDraft
from app.shopping import build_shopping_list

logger = logging.getLogger(__name__)

SHORTLIST_SIZE = 12
# Plans offered to the model; they're ranked, so later ones are rarely better.
OPTION_COUNT = 5
# Names this alike are the same dinner: "Indian Corn Khichdi" / "Indian Corn Kichdi" (spelling),
# "Vegetable Tacos" / "Vegetable Stuffed Tacos" (shared words). The search favours dishes that
# share ingredients, so without this it offers near-twins on consecutive nights.
SIMILAR_NAME_RATIO = 0.85
SIMILAR_NAME_WORDS = 0.5
_NAME_FILLER = {"and", "with", "in", "a", "the"}
# Items a new dish may add beyond the pantry and the rest of the plan's shopping list:
# as the model sketches it, and once written as a full recipe (which adds spices and oil).
NEW_DISH_MAX_EXTRA_ITEMS = 1
NEW_RECIPE_MAX_EXTRA_ITEMS = 3
PLAN_ROUNDS = 2
NEW_DISH_ATTEMPTS = 2

# generate(dish_name, main_ingredients) -> a recipe with .name, .ingredients, .time, .calories
Generate = Callable[[Optional[str], list[str]], object]


class NoRecipesFit(Exception):
    """No stored recipe fits the dietary filters, so there is nothing to plan from."""


def _name_key(name) -> str:
    return " ".join(str(name or "").lower().split())


def _name_words(name) -> set[str]:
    return ingredient_tokens(str(name or "")) - _NAME_FILLER


def similar_names(a, b) -> bool:
    if SequenceMatcher(None, _name_key(a), _name_key(b)).ratio() >= SIMILAR_NAME_RATIO:
        return True
    words_a, words_b = _name_words(a), _name_words(b)
    union = words_a | words_b
    return bool(union) and len(words_a & words_b) / len(union) >= SIMILAR_NAME_WORDS


def _item_key(name) -> frozenset:
    return frozenset(ingredient_tokens(str(name or "")))


def _as_dicts(ingredients) -> list[dict]:
    return [i if isinstance(i, dict) else {"name": str(i)} for i in ingredients or []]


def to_buy(ingredients, pantry: list[str]) -> dict[frozenset, str]:
    """Items to buy for these ingredients, keyed so "red onions" and "red onion" match."""
    need = build_shopping_list(_as_dicts(ingredients), pantry)["need"]
    return {key: item["name"] for item in need if (key := _item_key(item.get("name")))}


def pantry_used(ingredients, pantry: list[str]) -> list[str]:
    names = [ingredient_tokens(str(i.get("name", ""))) for i in _as_dicts(ingredients)]
    return [p for p in pantry if (owned := ingredient_tokens(p)) and any(owned <= n for n in names)]


def shortlist(recipes, pantry: list[str], filters: DietaryFilters, size: int = SHORTLIST_SIZE) -> list:
    eligible = [r for r in recipes if filters.matches(r)]
    eligible.sort(key=lambda r: (-len(pantry_used(r.ingredients, pantry)), len(to_buy(r.ingredients, pantry))))
    kept: list = []
    for recipe in eligible:
        if not any(similar_names(recipe.name, k.name) for k in kept):
            kept.append(recipe)
        if len(kept) == size:
            break
    return kept


@dataclass
class PlannedDay:
    day: int
    recipe: object
    new: bool


def assemble(planned: list[PlannedDay], pantry: list[str]) -> dict:
    """The plan as the API returns it, with one shopping list for all days."""
    shopping: dict[frozenset, dict] = {}
    staples: dict[str, str] = {}
    for entry in planned:
        split = build_shopping_list(_as_dicts(entry.recipe.ingredients), pantry)
        for item in split["need"]:
            key = _item_key(item.get("name"))
            if not key:
                continue
            merged = shopping.setdefault(key, {"name": item["name"], "quantities": [], "days": []})
            if item.get("quantity"):
                merged["quantities"].append(str(item["quantity"]))
            if entry.day not in merged["days"]:
                merged["days"].append(entry.day)
        for item in split["staples"]:
            name = str(item.get("name", "")).strip()
            if ingredient_tokens(name):
                staples.setdefault(name.lower(), name)

    used = {p: [e.day for e in planned if p in pantry_used(e.recipe.ingredients, pantry)] for p in pantry}
    return {
        "days": [
            {"day": e.day, "recipe": e.recipe, "new": e.new, "uses_pantry": pantry_used(e.recipe.ingredients, pantry)}
            for e in planned
        ],
        # Items several days share first: those are the point of planning ahead.
        "shopping_list": sorted(shopping.values(), key=lambda i: (-len(i["days"]), i["name"].lower())),
        "staples": sorted(staples.values(), key=str.lower),
        "pantry_used": [{"ingredient": p, "days": d} for p, d in used.items() if d],
        "pantry_unused": [p for p, d in used.items() if not d],
    }


def plan_cost(plan: dict) -> tuple:
    """Lower is better. Every pantry item used and every purchase shared offsets one purchase."""
    buy = len(plan["shopping_list"])
    shared = sum(len(item["days"]) > 1 for item in plan["shopping_list"])
    return (buy - len(plan["pantry_used"]) - shared, buy)


@dataclass
class Option:
    recipes: list
    plan: dict


def rank_options(candidates: list, pantry: list[str], days: int, count: int = OPTION_COUNT) -> list[Option]:
    size = min(days, len(candidates))
    if not size:
        return []
    options = []
    for combo in itertools.combinations(candidates, size):
        plan = assemble([PlannedDay(d, r, False) for d, r in enumerate(combo, 1)], pantry)
        options.append(Option(list(combo), plan))
    options.sort(key=lambda o: plan_cost(o.plan))
    return options[:count]


def _option_text(number: int, option: Option) -> str:
    dinners = "; ".join(
        f"day {d}: {r.name}" + (f" ({r.cuisine})" if getattr(r, "cuisine", None) else "")
        for d, r in enumerate(option.recipes, 1)
    )
    buys = ", ".join(
        i["name"] + (f" (days {', '.join(map(str, i['days']))})" if len(i["days"]) > 1 else "")
        for i in option.plan["shopping_list"]
    ) or "nothing"
    uses = ", ".join(u["ingredient"] for u in option.plan["pantry_used"]) or "nothing"
    unused = ", ".join(option.plan["pantry_unused"]) or "nothing"
    return (f"Option {number}: {dinners}.\n  Buy {len(option.plan['shopping_list'])}: {buys}.\n"
            f"  Uses their: {uses}. Leaves unused: {unused}.")


def review(draft: MealPlanDraft, options: list[Option], days: int, pantry: list[str],
           filters: DietaryFilters) -> list[str]:
    """Problems with the model's answer; empty if it can be used as is."""
    if draft.option > len(options):
        return [f"there is no option {draft.option}; choose 1 to {len(options)}"]
    option = options[draft.option - 1]
    missing = days - len(option.recipes)
    dish = draft.new_dish
    if dish is None:
        return [f"day {days} needs a new dish"] if missing else []

    problems = []
    if not missing and dish.replace_day not in range(1, days + 1):
        problems.append(f"replace_day must be 1 to {days}")
    keep = [r for d, r in enumerate(option.recipes, 1) if missing or d != dish.replace_day]
    # Including the dinner it replaces: swapping in a near-copy of it changes nothing.
    for recipe in option.recipes:
        if similar_names(dish.name, recipe.name):
            problems.append(f"{dish.name!r} is the same dinner as {recipe.name!r}")
    diet_only = DietaryFilters(vegetarian=filters.vegetarian, vegan=filters.vegan, gluten_free=filters.gluten_free)
    problems += [f"{dish.name!r} is {v}" for v in diet_only.violations(_as_dicts(dish.ingredients), None, None)]
    extra = _extra_items(dish.ingredients, keep, pantry)
    if len(extra) > NEW_DISH_MAX_EXTRA_ITEMS:
        problems.append(
            f"{dish.name!r} needs {', '.join(extra)}, which no other dinner uses; "
            "build it from their ingredients and the option's shopping list"
        )
    return problems


def _extra_items(ingredients, other_recipes: list, pantry: list[str]) -> list[str]:
    """What these ingredients add to the shopping list of the other dinners."""
    planned = set().union(*(to_buy(r.ingredients, pantry) for r in other_recipes))
    return sorted(name for key, name in to_buy(ingredients, pantry).items() if key not in planned)


def _describe(draft: MealPlanDraft) -> str:
    text = f"option {draft.option}"
    if draft.new_dish:
        dish = draft.new_dish
        where = f" for day {dish.replace_day}" if dish.replace_day else ""
        text += f" with a new dish{where}: {dish.name} ({', '.join(dish.ingredients)})"
    return text


def plan_meals(
    pantry: list[str],
    days: int,
    recipes: list,
    generate: Generate,
    filters: Optional[DietaryFilters] = None,
    draft: Callable[..., MealPlanDraft] = draft_meal_plan,
) -> dict:
    filters = filters or DietaryFilters()
    candidates = shortlist(recipes, pantry, filters)
    if not candidates:
        raise NoRecipesFit()
    options = rank_options(candidates, pantry, days)
    missing = days - len(options[0].recipes)
    steps = [
        f"Shortlisted {len(candidates)} stored recipes that fit your preferences, "
        "ranked by how many of your ingredients they use.",
        f"Compared every combination of {len(options[0].recipes)} of them and kept the {len(options)} that "
        "buy the fewest items while using the most of your ingredients and sharing purchases across days.",
    ]

    texts = [_option_text(n, o) for n, o in enumerate(options, 1)]
    chosen: Optional[MealPlanDraft] = None
    revision = None
    for round_number in range(1, PLAN_ROUNDS + 1):
        try:
            answer = draft(pantry, days, texts, missing, filters=filters, revision=revision)
        except RecipeGenerationError:
            logger.exception("Meal plan draft failed", extra={"round": round_number})
            steps.append("The planner model didn't answer; used the top-ranked option.")
            break
        problems = review(answer, options, days, pantry, filters)
        if not problems:
            chosen = answer
            steps.append(f"The planner chose {_describe(answer)}.")
            break
        steps.append(f"The planner chose {_describe(answer)}, but: {'; '.join(problems)}.")
        if round_number < PLAN_ROUNDS:
            steps.append("Sent that back and asked for a revision.")
            revision = (f"Your previous answer was {_describe(answer)}. Problems:\n"
                        + "\n".join(f"- {p}" for p in problems) + "\nAnswer again.")
        elif answer.option <= len(options):
            # Keep its choice of option; only the new dish was wrong.
            chosen = MealPlanDraft(option=answer.option)
            steps.append(f"Kept option {answer.option} without the new dish.")

    option = options[chosen.option - 1] if chosen else options[0]
    planned = [PlannedDay(d, r, False) for d, r in enumerate(option.recipes, 1)]
    dish = chosen.new_dish if chosen else None
    if dish:
        day = days if missing else dish.replace_day
        others = [p.recipe for p in planned if p.day != day]
        recipe = _write_new_dish(dish.name, dish.ingredients, others, pantry, generate, filters)
        if recipe is not None:
            steps.append(f"Day {day}: wrote the full recipe for {recipe.name}.")
            planned = [p for p in planned if p.day != day] + [PlannedDay(day, recipe, True)]
            planned.sort(key=lambda p: p.day)
        else:
            kept = f"kept {option.recipes[day - 1].name}" if not missing else "left the day out"
            steps.append(f"Day {day}: couldn't write a recipe for {dish.name} that fits, so {kept}.")
    elif missing:
        steps.append(f"Only {len(option.recipes)} stored recipes fit your preferences, so the plan is shorter.")

    plan = assemble(planned, pantry)
    shared = sum(len(item["days"]) > 1 for item in plan["shopping_list"])
    steps.append(
        f"Merged the shopping lists: {len(plan['shopping_list'])} items to buy, "
        f"{shared} of them used on more than one day."
    )
    plan["steps"] = steps
    return plan


def _write_new_dish(name: str, ingredients: list[str], others: list, pantry: list[str],
                    generate: Generate, filters: DietaryFilters):
    for attempt in range(1, NEW_DISH_ATTEMPTS + 1):
        try:
            recipe = generate(name, ingredients)
        except RecipeGenerationError:
            logger.exception("New dish generation failed")
            return None
        problems = filters.violations(recipe.ingredients, recipe.time, recipe.calories)
        extra = _extra_items(recipe.ingredients, others, pantry)
        if len(extra) > NEW_RECIPE_MAX_EXTRA_ITEMS:
            problems.append(f"needs {len(extra)} items no other dinner uses")
        if not problems:
            return recipe
        logger.info("New dish rejected", extra={"attempt": attempt, "problems": problems})
    return None
