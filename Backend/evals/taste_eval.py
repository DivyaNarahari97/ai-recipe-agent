"""Does the taste profile change what gets generated?

Two sets of cases in taste_cases.json, each with a food to avoid that suits the dish:
- ingredients: what "Get Recipe" sends (chicken, lime, rice, black beans; avoid cilantro)
- cravings:    what craving search sends ("chicken burrito bowl"; avoid cilantro), where the
               model chooses every ingredient itself

Each case runs twice:
- baseline: plain generation (generate_recipe / generate_from_craving with no sources), no profile
- profile:  the same generation through app.ai.generate_for_taste with likes ["spicy food"] and the
            case's avoid: the profile in the prompt, the avoid check in code, one retry with the reason

Metrics:
- uses avoided: the recipe uses the avoided food (TasteProfile.violations, the endpoints' own check),
                on the first try and on the final recipe
- spicy:        a chili ingredient, or chili named in the steps (same pattern the frontend uses to
                count a 👍 on a spicy dish)
Recipes are saved to taste_results.json. Nothing is stored in the DB.

Usage (Ollama running with mistral, from Backend/):  python -m evals.taste_eval
"""
import json
import re
import statistics
import time
from pathlib import Path

from app.ai import MODEL_NAME, RecipeGenerationError, generate_for_taste, generate_from_craving, generate_recipe
from app.taste import TasteProfile

EVAL_DIR = Path(__file__).parent
LIKES = ["spicy food"]

# Same as isSpicy in recipe-frontend/src/taste.js.
HOT = re.compile(
    r"\b(chil(?:i|e|li)e?s?|jalape(?:n|ñ)os?|cayenne|sriracha|gochujang|gochugaru|harissa|habaneros?|serranos?|"
    r"chipotles?|red pepper flakes|hot sauce|sambal|curry paste|bird'?s eye|scotch bonnet|piri.?piri|peri.?peri)\b",
    re.I,
)


def score(recipe, avoid: TasteProfile) -> dict:
    ingredients = [i.model_dump() for i in recipe.ingredients]
    steps = [step for section in recipe.instructions for step in section.steps]
    return {
        "uses_avoided": avoid.violations(ingredients),
        "spicy_ingredient": any(HOT.search(i["name"]) for i in ingredients),
        "spicy": any(HOT.search(text) for text in [i["name"] for i in ingredients] + steps),
        "recipe": {
            "name": recipe.name,
            "ingredients": [f"{i['quantity'] or ''} {i['name']}".strip() for i in ingredients],
            "steps": steps,
        },
    }


def run(label, make):
    started = time.perf_counter()
    try:
        result = make()
    except RecipeGenerationError as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "seconds": round(time.perf_counter() - started, 1)}
    result["seconds"] = round(time.perf_counter() - started, 1)
    print(f"  {label:8} {result['recipe']['name']!r} uses_avoided={bool(result['uses_avoided'])} "
          f"spicy={result['spicy']} attempts={result.get('attempts', 1)} {result['seconds']}s", flush=True)
    return result


def run_case(generate, avoid: str) -> dict:
    """generate(profile=None, rejected=None) -> recipe."""
    avoid_only = TasteProfile(avoids=[avoid])
    profile = TasteProfile(likes=LIKES, avoids=[avoid])

    def with_profile():
        attempts = []

        def tracked(**kwargs):
            attempts.append(generate(**kwargs))
            return attempts[-1]

        recipe, used, _ = generate_for_taste(tracked, profile)
        first = [i.model_dump() for i in attempts[0].ingredients]
        return {**score(recipe, avoid_only), "attempts": used, "first_try_uses_avoided": bool(avoid_only.violations(first))}

    return {
        "baseline": run("baseline", lambda: score(generate(), avoid_only)),
        "profile": run("profile", with_profile),
    }


def summarize(results) -> dict:
    summary = {}
    for arm in ("baseline", "profile"):
        done = [r[arm] for r in results if "error" not in r[arm]]
        summary[arm] = {
            "cases": len(done),
            "errors": len(results) - len(done),
            "uses_avoided": sum(bool(r["uses_avoided"]) for r in done),
            "spicy": sum(r["spicy"] for r in done),
            "spicy_ingredient": sum(r["spicy_ingredient"] for r in done),
            "median_seconds": statistics.median(r["seconds"] for r in done) if done else None,
        }
        if arm == "profile":
            summary[arm]["uses_avoided_first_try"] = sum(r["first_try_uses_avoided"] for r in done)
            summary[arm]["retried"] = sum(r["attempts"] > 1 for r in done)
    return summary


def main():
    cases = json.loads((EVAL_DIR / "taste_cases.json").read_text())
    out = {"model": MODEL_NAME, "likes": LIKES, "summary": {}, "cases": {}}

    results = []
    for case in cases["ingredients"]:
        print(f"{', '.join(case['ingredients'])} (avoid {case['avoid']})", flush=True)
        ingredients = case["ingredients"]
        results.append({**case, **run_case(lambda **kw: generate_recipe(ingredients, **kw), case["avoid"])})
    out["cases"]["ingredients"], out["summary"]["ingredients"] = results, summarize(results)

    results = []
    for case in cases["cravings"]:
        print(f"{case['craving']} (avoid {case['avoid']})", flush=True)
        craving = case["craving"]
        results.append({**case, **run_case(lambda **kw: generate_from_craving(craving, [], **kw), case["avoid"])})
    out["cases"]["cravings"], out["summary"]["cravings"] = results, summarize(results)

    (EVAL_DIR / "taste_results.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(out["summary"], indent=2))


if __name__ == "__main__":
    main()
