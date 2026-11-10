"""Does retrieval help generation? For each craving in the search eval, generate a
recipe with the top 3 hybrid-search matches as context (RAG, like /search/generate)
and without any context, then compare:

- meets the craving: the generated recipe passes the query's relevance rule
  (rules on time and calories use the model's own estimates)
- overlap with retrieved recipes: share of the generated recipe's ingredient words
  that appear in the 3 retrieved recipes
- copies a retrieved recipe: same name, or ingredient sets at least 70% identical
  (the check /search/generate now uses to reject and retry)
- latency per generation

Reads the database, writes nothing; generated recipes are not saved.
Usage (Ollama running, from Backend/):  python -m evals.rag_eval
"""
import json
import statistics
import time
from pathlib import Path
from types import SimpleNamespace

from app.ai import MODEL_NAME, RecipeGenerationError, generate_from_craving
from app.ingredients import extract_normalized_ingredient_tokens, near_copy_of
from evals.search_eval import QUERIES, distinct, load_corpus, rankings_for

EVAL_DIR = Path(__file__).parent
SOURCES = 3
VARIANTS = ("without_retrieval", "with_retrieval")


def _as_recipe(generated) -> SimpleNamespace:
    # The relevance rules expect stored-recipe shape (ingredients as dicts).
    return SimpleNamespace(
        name=generated.name,
        ingredients=[i.model_dump() for i in generated.ingredients],
        time=generated.time,
        calories=generated.calories,
    )


def _tokens(recipe) -> set[str]:
    return extract_normalized_ingredient_tokens(recipe.ingredients)


def score(generated, sources, relevant) -> dict:
    recipe = _as_recipe(generated)
    tokens = _tokens(recipe)
    source_tokens = set().union(*(_tokens(s) for s in sources))
    return {
        "name": recipe.name,
        "ingredients": [i["name"] for i in recipe.ingredients],
        "meets_craving": bool(relevant(recipe)),
        "overlap_with_sources": len(tokens & source_tokens) / len(tokens) if tokens else 0.0,
        "copies_source": near_copy_of(recipe.name, recipe.ingredients, sources) is not None,
    }


def main() -> None:
    recipes, keyword, doc_vectors, query_vectors = load_corpus()

    rows = []
    for (query, relevant), query_vector, keyword_ids in zip(QUERIES, query_vectors, keyword):
        hybrid = rankings_for(doc_vectors, query_vector, keyword_ids)["hybrid"]
        sources = distinct([recipes[i] for i in hybrid])[:SOURCES]
        row = {"query": query, "sources": [s.name for s in sources]}
        for variant in VARIANTS:
            context = sources if variant == "with_retrieval" else []
            started = time.perf_counter()
            try:
                generated = generate_from_craving(query, context)
                result = {"success": True, **score(generated, sources, relevant)}
            except RecipeGenerationError as exc:
                result = {"success": False, "error": str(exc)}
            result["latency_seconds"] = round(time.perf_counter() - started, 2)
            row[variant] = result
            print(f"{query} | {variant}: {result.get('name')} meets={result.get('meets_craving')} "
                  f"overlap={result.get('overlap_with_sources', 0):.0%} copy={result.get('copies_source')} "
                  f"{result['latency_seconds']}s", flush=True)
        rows.append(row)

    summary = {}
    for variant in VARIANTS:
        results = [r[variant] for r in rows]
        ok = [r for r in results if r["success"]]
        summary[variant] = {
            # Failures include model-call timeouts, not just invalid output.
            "produced_recipe": len(ok) / len(results),
            "meets_craving": sum(r["meets_craving"] for r in ok) / len(ok) if ok else None,
            "overlap_with_sources": statistics.mean(r["overlap_with_sources"] for r in ok) if ok else None,
            "copies_source": sum(r["copies_source"] for r in ok) / len(ok) if ok else None,
            "latency_p50_seconds": statistics.median(r["latency_seconds"] for r in results),
        }
    (EVAL_DIR / "rag_results.json").write_text(json.dumps(
        {"model": MODEL_NAME, "sources_per_query": SOURCES, "summary": summary, "queries": rows}, indent=2
    ) + "\n")

    labels = [
        ("Produced a recipe (one retry allowed)", "produced_recipe", "pct"),
        ("Meets the craving", "meets_craving", "pct"),
        ("Ingredient overlap with retrieved recipes", "overlap_with_sources", "pct"),
        ("Copies a retrieved recipe", "copies_source", "pct"),
        ("Latency p50", "latency_p50_seconds", "sec"),
    ]
    print("\n| Metric | Without retrieval | With retrieval (RAG) |")
    print("|--------|------|------|")
    for label, key, kind in labels:
        cells = []
        for variant in VARIANTS:
            value = summary[variant][key]
            cells.append("n/a" if value is None else (f"{value:.0%}" if kind == "pct" else f"{value:.1f}s"))
        print(f"| {label} | {cells[0]} | {cells[1]} |")


if __name__ == "__main__":
    main()
