"""Does planning help? For each pantry, plan 3 dinners three ways and compare the shopping:

- best matches: the 3 recipes that use the most of the pantry, picked independently
  (what you'd get without planning)
- top option: the planner's search alone, with no model: the best-ranked combination
- agent: the meal-planner agent (the model picks among the top options for variety and
  may swap in a new dish)
- fewest purchases: the combination that buys the fewest items, ignoring everything else

Metrics: items to buy, items shared by 2+ dinners, share of the pantry used, near-twin
dinner pairs (names alike, e.g. "Vegetable Tacos" / "Vegetable Stuffed Tacos"), and for the agent: valid plan (right number of distinct dinners, filters met),
new dishes, revisions, latency.

Reads the database, writes nothing; new dishes are generated but not saved.
Usage (Ollama running, from Backend/):  python -m evals.meal_plan_eval
"""
import itertools
import json
import statistics
import time
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv

load_dotenv(".env")

from app import models  # noqa: E402
from app.ai import MODEL_NAME, RecipeGenerationError, generate_recipe  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.dietary import DietaryFilters  # noqa: E402
from app.meal_planner import (  # noqa: E402
    PlannedDay, assemble, plan_meals, rank_options, shortlist, similar_names,
)

EVAL_DIR = Path(__file__).parent
DAYS = 3
CASES = [
    (["rice", "spinach", "onion", "tomato", "garlic"], DietaryFilters()),
    (["chicken", "potato", "onion", "garlic", "lemon"], DietaryFilters()),
    (["pasta", "tomato", "basil", "garlic", "cheese"], DietaryFilters()),
    (["eggs", "bread", "milk", "cheese", "spinach"], DietaryFilters()),
    (["chickpeas", "onion", "tomato", "cumin", "rice"], DietaryFilters(vegetarian=True)),
    (["tofu", "broccoli", "soy sauce", "ginger", "rice"], DietaryFilters(vegan=True)),
    (["potato", "carrot", "peas", "onion"], DietaryFilters(gluten_free=True)),
    (["paneer", "capsicum", "onion", "tomato"], DietaryFilters(max_minutes=45)),
]
METHODS = ("best_matches", "top_option", "agent", "fewest_purchases")


def metrics(plan: dict, pantry: list[str]) -> dict:
    return {
        "dinners": [d["recipe"].name for d in plan["days"]],
        "items_to_buy": len(plan["shopping_list"]),
        "shared_items": sum(len(i["days"]) > 1 for i in plan["shopping_list"]),
        "pantry_used": len(plan["pantry_used"]) / len(pantry),
        "near_twins": sum(similar_names(a.name, b.name) for a, b in itertools.combinations(
            [d["recipe"] for d in plan["days"]], 2)),
    }


def fixed_plan(recipes, pantry) -> dict:
    return assemble([PlannedDay(day, r, False) for day, r in enumerate(recipes, 1)], pantry)


def fewest_purchases(candidates, pantry) -> dict:
    plans = (fixed_plan(combo, pantry) for combo in itertools.combinations(candidates, DAYS))
    return min(plans, key=lambda p: (len(p["shopping_list"]), -len(p["pantry_used"])))


def generate_unsaved(filters):
    def generate(dish_name, ingredients):
        recipe = generate_recipe(ingredients, filters=filters, dish_name=dish_name)
        return SimpleNamespace(id=None, name=recipe.name, time=recipe.time, calories=recipe.calories,
                               ingredients=[i.model_dump() for i in recipe.ingredients])
    return generate


def main() -> None:
    db = SessionLocal()
    recipes = db.query(models.Recipe).all()
    db.close()

    rows = []
    for pantry, filters in CASES:
        candidates = shortlist(recipes, pantry, filters)
        row = {"pantry": pantry, "filters": filters.model_dump(exclude_defaults=True)}
        row["best_matches"] = metrics(fixed_plan(candidates[:DAYS], pantry), pantry)
        row["top_option"] = metrics(rank_options(candidates, pantry, DAYS)[0].plan, pantry)
        row["fewest_purchases"] = metrics(fewest_purchases(candidates, pantry), pantry)

        started = time.perf_counter()
        try:
            plan = plan_meals(pantry, DAYS, recipes, generate_unsaved(filters), filters)
            result = {"success": True, **metrics(plan, pantry)}
            dinners = [d["recipe"] for d in plan["days"]]
            result["valid"] = (
                len(dinners) == DAYS
                and len({r.name.lower() for r in dinners}) == DAYS
                and all(filters.matches(r) for r in dinners)
            )
            result["new_dishes"] = sum(d["new"] for d in plan["days"])
            result["revised"] = any("asked for a revision" in s for s in plan["steps"])
            result["dropped_new_dish"] = any("couldn't write a recipe" in s or "without the new dish" in s
                                             for s in plan["steps"])
            result["steps"] = plan["steps"]
        except RecipeGenerationError as exc:
            result = {"success": False, "error": str(exc)}
        result["latency_seconds"] = round(time.perf_counter() - started, 1)
        row["agent"] = result
        rows.append(row)
        print(f"{', '.join(pantry)} | " + " | ".join(
            f"{m}: buy {row[m].get('items_to_buy')} shared {row[m].get('shared_items')}" for m in METHODS
        ) + f" | {result['latency_seconds']}s", flush=True)

    def mean(method, key):
        values = [r[method][key] for r in rows if r[method].get("success", True)]
        return statistics.mean(values) if values else None

    agent_runs = [r["agent"] for r in rows if r["agent"]["success"]]
    summary = {
        method: {key: mean(method, key) for key in ("items_to_buy", "shared_items", "pantry_used", "near_twins")}
        for method in METHODS
    }
    summary["agent"].update({
        "produced_plan": len(agent_runs) / len(rows),
        "valid_plan": sum(r["valid"] for r in agent_runs) / len(agent_runs) if agent_runs else None,
        "new_dishes": sum(r["new_dishes"] for r in agent_runs),
        "revised": sum(r["revised"] for r in agent_runs),
        "dropped_new_dish": sum(r["dropped_new_dish"] for r in agent_runs),
        "latency_p50_seconds": statistics.median(r["agent"]["latency_seconds"] for r in rows),
    })
    (EVAL_DIR / "meal_plan_results.json").write_text(json.dumps(
        {"model": MODEL_NAME, "days": DAYS, "summary": summary, "cases": rows}, indent=2
    ) + "\n")

    print("\n| Metric | Best matches | Top option (search only) | Agent | Fewest purchases |")
    print("|--------|------|------|------|------|")
    for label, key, kind in (("Items to buy", "items_to_buy", "num"),
                             ("Items shared by 2+ dinners", "shared_items", "num"),
                             ("Pantry used", "pantry_used", "pct"),
                             ("Near-twin dinner pairs", "near_twins", "num")):
        cells = [summary[m][key] for m in METHODS]
        print(f"| {label} | " + " | ".join(
            "n/a" if v is None else (f"{v:.0%}" if kind == "pct" else f"{v:.1f}") for v in cells) + " |")
    print(json.dumps({k: v for k, v in summary["agent"].items()
                      if k not in ("items_to_buy", "shared_items", "pantry_used", "near_twins")}, indent=2))


if __name__ == "__main__":
    main()
