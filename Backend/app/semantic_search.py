"""Search recipes by what someone is craving: pgvector similarity + Postgres full-text
search, merged with reciprocal rank fusion (RRF)."""
import logging
from typing import Optional

from sqlalchemy import func, or_, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import models
from app.dietary import DietaryFilters
from app.embeddings import (
    DOCUMENT_PREFIX,
    EMBED_MODEL,
    QUERY_PREFIX,
    content_hash,
    embed,
    recipe_document,
)

logger = logging.getLogger(__name__)

_BATCH_SIZE = 32
# Each ranker contributes this many candidates before fusion, deduping and filters.
CANDIDATES = 50
# Standard RRF constant; larger values flatten the gap between rank 1 and rank 10.
RRF_K = 60

# OR the query's words together: plainto_tsquery ANDs them, and a craving like
# "light and spicy for a cold night" would then match almost nothing.
KEYWORD_TSQUERY_SQL = (
    "CAST(replace(CAST(plainto_tsquery('english', :query) AS text), '&', '|') AS tsquery)"
)
# ts_rank_cd normalization 1: divide by log(document length), so long recipes
# don't win just by containing more words.
KEYWORD_RANK_NORMALIZATION = 1


def _embed_and_store(db: Session, recipes: list[models.Recipe]) -> int:
    for start in range(0, len(recipes), _BATCH_SIZE):
        batch = recipes[start:start + _BATCH_SIZE]
        documents = [recipe_document(r) for r in batch]
        vectors = embed([DOCUMENT_PREFIX + d for d in documents])
        for recipe, document, vector in zip(batch, documents, vectors):
            values = {
                "recipe_id": recipe.id,
                "model": EMBED_MODEL,
                "content_hash": content_hash(document),
                "embedding": vector,
                "search_vector": func.to_tsvector("english", document),
            }
            stmt = insert(models.RecipeEmbedding).values(**values)
            db.execute(stmt.on_conflict_do_update(
                index_elements=[models.RecipeEmbedding.recipe_id],
                set_={k: stmt.excluded[k] for k in values if k != "recipe_id"},
            ))
        db.commit()
    return len(recipes)


def index_missing(db: Session) -> int:
    """Index recipes with no vector yet (or no keyword index, from before hybrid search)."""
    missing = (
        db.query(models.Recipe)
        .outerjoin(models.RecipeEmbedding, models.RecipeEmbedding.recipe_id == models.Recipe.id)
        .filter(or_(
            models.RecipeEmbedding.recipe_id.is_(None),
            models.RecipeEmbedding.search_vector.is_(None),
        ))
        .all()
    )
    if missing:
        logger.info("Indexing recipes for search", extra={"count": len(missing)})
    return _embed_and_store(db, missing)


def reindex_stale(db: Session) -> int:
    """Re-embed recipes whose text or embedding model changed since they were indexed."""
    stored = {e.recipe_id: e.content_hash for e in db.query(models.RecipeEmbedding).all()}
    stale = [
        r for r in db.query(models.Recipe).all()
        if stored.get(r.id) != content_hash(recipe_document(r))
    ]
    return _embed_and_store(db, stale)


def reciprocal_rank_fusion(*rankings: list[int], k: int = RRF_K) -> list[tuple[int, float]]:
    """Merge ranked id lists: score = sum of 1 / (k + rank) over the lists an id appears in.

    Returns (id, score) pairs, best first. Ties keep first-seen order.
    """
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: -pair[1])


def _vector_ranking(db: Session, query: str) -> list[int]:
    query_vector = embed([QUERY_PREFIX + query])[0]
    distance = models.RecipeEmbedding.embedding.cosine_distance(query_vector)
    rows = (
        db.query(models.RecipeEmbedding.recipe_id)
        .filter(models.RecipeEmbedding.model == EMBED_MODEL)
        .order_by(distance)
        .limit(CANDIDATES)
        .all()
    )
    return [recipe_id for (recipe_id,) in rows]


def _keyword_ranking(db: Session, query: str) -> list[int]:
    rows = db.execute(
        text(
            f"SELECT recipe_id FROM recipe_embeddings, {KEYWORD_TSQUERY_SQL} AS q "
            "WHERE search_vector @@ q "
            f"ORDER BY ts_rank_cd(search_vector, q, {KEYWORD_RANK_NORMALIZATION}) DESC, recipe_id "
            "LIMIT :limit"
        ),
        {"query": query, "limit": CANDIDATES},
    ).all()
    return [recipe_id for (recipe_id,) in rows]


def dedupe_key(recipe) -> str:
    return " ".join(str(recipe.name or "").lower().split())


def search(
    db: Session,
    query: str,
    limit: int = 6,
    filters: Optional[DietaryFilters] = None,
) -> list[tuple[models.Recipe, float]]:
    """Best distinct recipes for a craving, as (recipe, RRF score) pairs."""
    filters = filters or DietaryFilters()
    index_missing(db)

    fused = reciprocal_rank_fusion(_vector_ranking(db, query), _keyword_ranking(db, query))
    ids = [recipe_id for recipe_id, _ in fused]
    recipes = {r.id: r for r in db.query(models.Recipe).filter(models.Recipe.id.in_(ids)).all()}
    return _best_distinct(
        [(recipes[i], score) for i, score in fused if i in recipes], filters, limit
    )


def _best_distinct(rows, filters: DietaryFilters, limit: int) -> list[tuple[models.Recipe, float]]:
    # The table holds near-identical copies of some recipes; without this they
    # crowd every result list (the retrieval eval showed one dish in 23 of 50 slots).
    hits, seen = [], set()
    for recipe, score in rows:
        key = dedupe_key(recipe)
        if key in seen or not filters.matches(recipe):
            continue
        seen.add(key)
        hits.append((recipe, score))
        if len(hits) == limit:
            break
    return hits
