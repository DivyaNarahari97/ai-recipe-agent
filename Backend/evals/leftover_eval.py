"""Does the leftover flow make a new dish that uses the leftovers?

For each case in leftover_cases.json, two runs with the same leftovers:
- baseline: the app's plain "Get Recipe" generation (app.ai.generate_recipe), given the leftover names
- leftover: the leftover flow (app.leftovers.make_leftover_dish): leftover prompt, code checks,
            one retry with the reasons

Metrics, using the same code checks the endpoint uses (app.leftovers):
- uses all:   every leftover is an ingredient
- new dish:   the name isn't just the leftovers ("Roast Chicken and Rice")
- to buy:     ingredients beyond the leftovers and pantry staples (limit 4)
- passes:     all three, on the final recipe
- recooked:   steps that cook a leftover from raw ("cook the rice according to package
              instructions", "grill the salmon for 10 minutes"). The app's checks can't see
              this; it's a phrase heuristic here, so its hits were also checked by hand.
Recipes are saved to leftover_results.json. Nothing is stored in the DB.

Usage (Ollama running with mistral, from Backend/):  python -m evals.leftover_eval
"""
import json
import statistics
import time
from pathlib import Path

from app.ai import MODEL_NAME, RecipeGenerationError, generate_from_leftovers, generate_recipe
from app.dietary import DietaryFilters
from app.leftovers import (
    MAX_EXTRA_INGREDIENTS,
    DishRejected,
    extra_ingredients,
    leftover_problems,
    make_leftover_dish,
    parse_leftovers,
)

EVAL_DIR = Path(__file__).parent

# Phrases that mean starting from raw, when the same step names a leftover.
FROM_RAW = (
    "according to package", "package instructions", "soak", "pressure cook", "rinse",
    "roll out", "grill for", "steam ", "until tender", "boil",
)


def recooked_steps(steps: list[str], leftovers) -> list[str]:
    words = {w for l in leftovers for w in l.name.split()}
    return [
        step for step in steps
        if any(p in step.lower() for p in FROM_RAW) and any(w in step.lower() for w in words)
    ]


def score(recipe, leftovers) -> dict:
    ingredients = [i.model_dump() for i in recipe.ingredients]
    problems = leftover_problems(recipe.name, ingredients, leftovers)
    extras = extra_ingredients(ingredients, leftovers)
    steps = [step for section in recipe.instructions for step in section.steps]
    return {
        "recooked": recooked_steps(steps, leftovers),
        "uses_all": not any("leaves out" in p for p in problems),
        "new_dish": not any("reheated" in p for p in problems),
        "to_buy": len(extras),
        "passes": not problems,
        "problems": problems,
        "recipe": {
            "name": recipe.name,
            "servings": recipe.servings,
            "ingredients": [f"{i['quantity'] or ''} {i['name']}".strip() for i in ingredients],
            "steps": steps,
        },
    }


def run(label, make):
    started = time.perf_counter()
    try:
        result = make()
    except (RecipeGenerationError, DishRejected) as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "seconds": round(time.perf_counter() - started, 1)}
    result["seconds"] = round(time.perf_counter() - started, 1)
    print(f"  {label:9} {result['recipe']['name']!r} passes={result['passes']} to_buy={result['to_buy']} "
          f"recooked={len(result['recooked'])} attempts={result.get('attempts', 1)} {result['seconds']}s")
    return result


def main():
    cases = json.loads((EVAL_DIR / "leftover_cases.json").read_text())
    results = []
    for case in cases:
        print(case["text"])
        leftovers = parse_leftovers(case["text"])

        def baseline():
            return score(generate_recipe([l.text for l in leftovers]), leftovers)

        def leftover_flow():
            # make_leftover_dish raises DishRejected if both attempts fail; score the last one anyway.
            attempts = []

            def generate(*args, **kwargs):
                attempts.append(generate_from_leftovers(*args, **kwargs))
                return attempts[-1]

            try:
                make_leftover_dish(leftovers, DietaryFilters(), generate=generate)
            except DishRejected:
                pass
            return {**score(attempts[-1], leftovers), "attempts": len(attempts)}

        results.append({
            "text": case["text"],
            "leftovers": [l.text for l in leftovers],
            "baseline": run("baseline", baseline),
            "leftover": run("leftover", leftover_flow),
        })

    summary = {}
    for arm in ("baseline", "leftover"):
        done = [r[arm] for r in results if "error" not in r[arm]]
        summary[arm] = {
            "cases": len(done),
            "errors": len(results) - len(done),
            "uses_all": sum(r["uses_all"] for r in done),
            "new_dish": sum(r["new_dish"] for r in done),
            f"to_buy_within_{MAX_EXTRA_INGREDIENTS}": sum(r["to_buy"] <= MAX_EXTRA_INGREDIENTS for r in done),
            "passes": sum(r["passes"] for r in done),
            "recooks_a_leftover": sum(bool(r["recooked"]) for r in done),
            "median_to_buy": statistics.median(r["to_buy"] for r in done) if done else None,
            "median_seconds": statistics.median(r["seconds"] for r in done) if done else None,
        }
        if arm == "leftover":
            summary[arm]["passed_first_try"] = sum(r["passes"] and r["attempts"] == 1 for r in done)

    out = {"model": MODEL_NAME, "summary": summary, "cases": results}
    (EVAL_DIR / "leftover_results.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
