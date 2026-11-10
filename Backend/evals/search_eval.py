"""Retrieval eval for craving search, run over the recipes in your database.

Each query has a rule for what counts as relevant (e.g. "light" = at most 350 kcal),
so no hand labels are needed. Reports precision@5 against the base rate (what a
random pick would score) for vector search, Postgres keyword search, and the
hybrid of both that /search uses. Also reports how many queries the single most
frequent recipe shows up in, the "one dish matches everything" problem. Like
/search, results keep one recipe per name. Reads the database, writes nothing.

Usage (Ollama running, from Backend/):  python -m evals.search_eval
"""
import json
from collections import Counter
from pathlib import Path

import numpy as np

from app import models
from app.db import SessionLocal
from app.dietary import VEGAN, dietary_tags, parse_calories, parse_minutes
from app.embeddings import DOCUMENT_PREFIX, EMBED_MODEL, QUERY_PREFIX, _SPICY, embed, recipe_document
from app.ingredients import extract_normalized_ingredient_tokens
from sqlalchemy import text

from app.semantic_search import (
    CANDIDATES,
    KEYWORD_RANK_NORMALIZATION,
    KEYWORD_TSQUERY_SQL,
    dedupe_key,
    reciprocal_rank_fusion,
)

K = 5
EVAL_DIR = Path(__file__).parent


def _tokens(recipe) -> set[str]:
    return extract_normalized_ingredient_tokens(recipe.ingredients)


def _light(recipe) -> bool:
    kcal = parse_calories(recipe.calories)
    return kcal is not None and kcal <= 350


def _spicy(recipe) -> bool:
    return bool(_tokens(recipe) & _SPICY)


QUERIES = [
    ("something light for lunch", _light),
    ("a quick snack I can make in a few minutes",
     lambda r: (parse_minutes(r.time) or 10**6) <= 20),
    ("something with a spicy kick", _spicy),
    ("a plant-based meal without any animal products",
     lambda r: VEGAN in dietary_tags(r.ingredients)),
    ("creamy, cheesy comfort food",
     lambda r: bool(_tokens(r) & {"cheese", "cream", "paneer", "mozzarella", "parmesan"})),
    ("a warming Indian curry",
     lambda r: bool(_tokens(r) & {"garam", "masala", "turmeric", "curry"})),
    ("something with chicken", lambda r: "chicken" in _tokens(r)),
    ("a fresh crunchy salad", lambda r: "salad" in r.name.lower()),
    ("something sweet for dessert",
     lambda r: bool(_tokens(r) & {"sugar", "honey", "jaggery", "chocolate", "maple"})),
    ("light and spicy for a cold night", lambda r: _light(r) and _spicy(r)),
]


def _normalize(vectors) -> np.ndarray:
    matrix = np.asarray(vectors, dtype=float)
    return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)


def _embed_all(texts: list[str], batch: int = 32) -> np.ndarray:
    vectors = []
    for start in range(0, len(texts), batch):
        vectors.extend(embed(texts[start:start + batch]))
    return _normalize(vectors)


def distinct(recipes_in_rank_order: list) -> list:
    seen, result = set(), []
    for recipe in recipes_in_rank_order:
        if dedupe_key(recipe) not in seen:
            seen.add(dedupe_key(recipe))
            result.append(recipe)
    return result


def precision_at_k(ranked: list, relevant) -> float:
    return sum(relevant(r) for r in ranked[:K]) / K


def keyword_ranking(db, documents: list[str], query: str) -> list[int]:
    """Postgres full-text ranking of in-memory documents, same SQL as /search; no writes."""
    rows = db.execute(
        text(
            "SELECT t.idx FROM unnest(CAST(:docs AS text[])) WITH ORDINALITY AS t(doc, idx), "
            f"{KEYWORD_TSQUERY_SQL} AS q "
            "WHERE to_tsvector('english', t.doc) @@ q "
            f"ORDER BY ts_rank_cd(to_tsvector('english', t.doc), q, {KEYWORD_RANK_NORMALIZATION}) DESC, t.idx "
            "LIMIT :limit"
        ),
        {"docs": documents, "query": query, "limit": CANDIDATES},
    ).all()
    return [idx - 1 for (idx,) in rows]  # ORDINALITY is 1-based


METHODS = ("vector", "keyword", "hybrid")


def load_corpus():
    """Stored recipes, their documents and keyword rankings for QUERIES, and doc vectors."""
    db = SessionLocal()
    try:
        recipes = db.query(models.Recipe).order_by(models.Recipe.id).all()
        documents = [recipe_document(r) for r in recipes]
        keyword = [keyword_ranking(db, documents, q) for q, _ in QUERIES]
    finally:
        db.close()
    doc_vectors = _embed_all([DOCUMENT_PREFIX + d for d in documents])
    query_vectors = _normalize(embed([QUERY_PREFIX + q for q, _ in QUERIES]))
    return recipes, keyword, doc_vectors, query_vectors


def rankings_for(doc_vectors, query_vector, keyword_ids) -> dict[str, list[int]]:
    vector_ids = [int(i) for i in np.argsort(-(doc_vectors @ query_vector))[:CANDIDATES]]
    return {
        "vector": vector_ids,
        "keyword": keyword_ids,
        "hybrid": [i for i, _ in reciprocal_rank_fusion(vector_ids, keyword_ids)],
    }


def main() -> None:
    recipes, keyword, doc_vectors, query_vectors = load_corpus()
    unique = distinct(recipes)

    rows = []
    appearances = {method: Counter() for method in METHODS}
    for (query, relevant), query_vector, keyword_ids in zip(QUERIES, query_vectors, keyword):
        rankings = rankings_for(doc_vectors, query_vector, keyword_ids)
        row = {"query": query, "base_rate": sum(relevant(r) for r in unique) / len(unique)}
        for method, ids in rankings.items():
            ranked = distinct([recipes[i] for i in ids])
            # Fewer than K results (keyword search can match little) count as misses.
            row[method] = precision_at_k(ranked, relevant)
            row[f"{method}_top"] = [r.name for r in ranked[:K]]
            appearances[method].update(dedupe_key(r) for r in ranked[:K])
        rows.append(row)

    mean = {key: sum(r[key] for r in rows) / len(rows) for key in ("base_rate", *METHODS)}
    most_frequent = {}
    for method, counts in appearances.items():
        name, count = counts.most_common(1)[0]
        most_frequent[method] = {"recipe": name, "queries": count}
    (EVAL_DIR / "search_results.json").write_text(json.dumps(
        {"model": EMBED_MODEL, "recipes": len(recipes), "distinct": len(unique), "k": K,
         "mean": mean, "most_frequent_in_top_k": most_frequent, "queries": rows}, indent=2
    ) + "\n")

    print(f"| Query | Random pick | Vector P@{K} | Keyword P@{K} | Hybrid P@{K} |")
    print("|-------|------|------|------|------|")
    for r in rows:
        print(f"| {r['query']} | {r['base_rate']:.0%} | {r['vector']:.0%} | {r['keyword']:.0%} | {r['hybrid']:.0%} |")
    print(f"| **Mean** | **{mean['base_rate']:.0%}** | **{mean['vector']:.0%}** | "
          f"**{mean['keyword']:.0%}** | **{mean['hybrid']:.0%}** |")
    print("\nMost frequent recipe in top-5 lists:")
    for method, info in most_frequent.items():
        print(f"  {method}: {info['recipe']} ({info['queries']}/{len(QUERIES)} queries)")
    print(f"\n{len(recipes)} recipes ({len(unique)} distinct names), {EMBED_MODEL}")


if __name__ == "__main__":
    main()
