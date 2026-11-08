"""Run fixed ingredient sets through generate_recipe and report quality and latency.

Usage (Ollama running, from Backend/):  python -m evals.recipe_eval
Prints a markdown table and writes per-case detail to evals/results.json.
"""
import json
import math
import platform
import statistics
import time
from pathlib import Path

from pydantic import ValidationError

from app.ai import MODEL_NAME, RecipeGenerationError, _call_model, generate_recipe
from app.ingredients import extract_normalized_ingredient_tokens, ingredient_tokens
from app.schemas import GeneratedRecipe

EVAL_DIR = Path(__file__).parent


def missing_ingredients(requested: list[str], recipe: GeneratedRecipe) -> list[str]:
    """Requested items whose tokens don't all appear in the recipe's ingredient list."""
    recipe_tokens = extract_normalized_ingredient_tokens(recipe.model_dump()["ingredients"])
    return [item for item in requested if not ingredient_tokens(item) <= recipe_tokens]


def _is_json(raw: str) -> bool:
    try:
        json.loads(raw)
        return True
    except ValueError:
        return False


def _is_valid_recipe(raw: str) -> bool:
    try:
        GeneratedRecipe.model_validate_json(raw)
        return True
    except ValidationError:
        return False


def run_case(requested: list[str], call_model=_call_model) -> dict:
    raw_outputs: list[str] = []

    def recording_call(prompt: str) -> str:
        raw = call_model(prompt)
        raw_outputs.append(raw)
        return raw

    started = time.perf_counter()
    recipe = None
    error = None
    try:
        recipe = generate_recipe(requested, call_model=recording_call)
    except RecipeGenerationError as exc:
        error = str(exc)
    latency = time.perf_counter() - started

    missing = missing_ingredients(requested, recipe) if recipe else None
    return {
        "requested": requested,
        "attempts": len(raw_outputs),
        "first_attempt_json": bool(raw_outputs) and _is_json(raw_outputs[0]),
        "first_attempt_valid": bool(raw_outputs) and _is_valid_recipe(raw_outputs[0]),
        "success": recipe is not None,
        "coverage": None if recipe is None else 1 - len(missing) / len(requested),
        "missing": missing,
        "latency_seconds": round(latency, 2),
        "error": error,
        "recipe_name": recipe.name if recipe else None,
        "cuisine": recipe.cuisine if recipe else None,
        "recipe_ingredients": [i.name for i in recipe.ingredients] if recipe else None,
        "rejected_outputs": [raw for raw in raw_outputs if not _is_valid_recipe(raw)],
    }


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[math.ceil(fraction * len(ordered)) - 1]


def summarize(results: list[dict]) -> dict:
    total = len(results)
    succeeded = [r for r in results if r["success"]]
    latencies = [r["latency_seconds"] for r in results]
    return {
        "cases": total,
        "first_attempt_json_rate": sum(r["first_attempt_json"] for r in results) / total,
        "first_attempt_valid_rate": sum(r["first_attempt_valid"] for r in results) / total,
        "success_rate_with_retry": len(succeeded) / total,
        "mean_coverage": (
            statistics.mean(r["coverage"] for r in succeeded) if succeeded else None
        ),
        "full_coverage_rate": (
            sum(r["coverage"] == 1 for r in succeeded) / len(succeeded) if succeeded else None
        ),
        # Tagged = one of the named cuisines, not missing and not the "Other" fallback.
        "cuisine_tagged_rate": (
            sum(r["cuisine"] not in (None, "Other") for r in succeeded) / len(succeeded)
            if succeeded else None
        ),
        "latency_p50_seconds": _percentile(latencies, 0.5),
        "latency_p95_seconds": _percentile(latencies, 0.95),
    }


def _pct(value) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def to_markdown(summary: dict) -> str:
    rows = [
        ("Cases", summary["cases"]),
        ("Valid JSON, first attempt", _pct(summary["first_attempt_json_rate"])),
        ("Passes schema, first attempt", _pct(summary["first_attempt_valid_rate"])),
        ("Passes schema, with one retry", _pct(summary["success_rate_with_retry"])),
        ("Mean ingredient coverage", _pct(summary["mean_coverage"])),
        ("Recipes using every requested ingredient", _pct(summary["full_coverage_rate"])),
        ("Tagged with a named cuisine", _pct(summary["cuisine_tagged_rate"])),
        ("Latency p50 per case", f"{summary['latency_p50_seconds']:.1f}s"),
        ("Latency p95 per case", f"{summary['latency_p95_seconds']:.1f}s"),
    ]
    lines = ["| Metric | Result |", "|--------|--------|"]
    lines += [f"| {name} | {value} |" for name, value in rows]
    return "\n".join(lines)


def main() -> None:
    cases = json.loads((EVAL_DIR / "cases.json").read_text())

    # Load the model first so the cold start doesn't count as the first case's latency.
    _call_model("Return the JSON object {}")

    results = []
    for index, requested in enumerate(cases, start=1):
        result = run_case(requested)
        results.append(result)
        print(
            f"[{index}/{len(cases)}] {', '.join(requested)}: "
            f"success={result['success']} attempts={result['attempts']} "
            f"coverage={_pct(result['coverage'])} {result['latency_seconds']}s",
            flush=True,
        )

    summary = summarize(results)
    output = {
        "model": MODEL_NAME,
        "machine": platform.machine(),
        "summary": summary,
        "results": results,
    }
    (EVAL_DIR / "results.json").write_text(json.dumps(output, indent=2) + "\n")
    print("\n" + to_markdown(summary))


if __name__ == "__main__":
    main()
