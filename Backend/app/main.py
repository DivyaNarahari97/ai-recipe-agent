import logging
import os
import re
import time
from typing import Optional

import requests
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.ai import (
    RecipeGenerationError,
    fetch_recipe_image,
    generate_from_craving,
    generate_recipe,
    refine_recipe,
    suggest_substitutes,
)
from app.db import engine, get_db
from app.dietary import DietaryFilters
from app.embeddings import EmbeddingError
from app.ingredients import extract_normalized_ingredient_tokens, near_copy_of
from app.schemas import (
    AssistantResponse,
    CravingRecipeRequest,
    CravingRecipeResponse,
    CuisineCount,
    GeneratedRecipe,
    RecipeCreate,
    RecipeResponse,
    RefineRequest,
    RefineResponse,
    SearchRequest,
    SearchResponse,
    ShoppingListRequest,
    ShoppingListResponse,
    SubstitutionResponse,
    normalize_cuisine,
)
from app.scaling import scale_for_new_servings
from app.semantic_search import search as semantic_search
from app.shopping import build_shopping_list
from app.substitutions import lookup_substitutes, substitution_key

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

logger = logging.getLogger(__name__)
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")


class RecipeSearchRequest(BaseModel):
    ingredients: list[str]
    min_match: Optional[float] = 0.5   # 50% match by default
    limit: Optional[int] = 10
    filters: DietaryFilters = DietaryFilters()


# =========================
# Request Schemas
# =========================
class IngredientsRequest(BaseModel):
    ingredients: list[str]
    filters: DietaryFilters = DietaryFilters()


def _extract_ingredient_names(ingredients: list) -> set[str]:
    names: set[str] = set()
    for item in ingredients or []:
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip().lower()
        else:
            name = str(item).strip().lower()
        if name:
            names.add(name)
    return names


def _cache_key(ingredients: list[str], filters: DietaryFilters) -> tuple:
    cleaned = sorted({str(i).strip().lower() for i in ingredients if str(i).strip()})
    return (tuple(cleaned), filters.model_dump_json())


_RECIPES_CACHE: dict[tuple, tuple[float, list[int]]] = {}
_CACHE_TTL_SECONDS = 300


def _normalize_tokens_for_storage(tokens: set[str]) -> list[str]:
    return sorted(tokens)


def fetch_ingredient_image_from_unsplash(name: str):
    url = "https://api.unsplash.com/search/photos"

    params = {
        "query": f"fresh {name} ingredient food",  # ✅ fixed: name not ingredient
        "client_id": UNSPLASH_ACCESS_KEY,
        "per_page": 5,
        "orientation": "squarish"
    }

    try:
        logger.info("Fetching ingredient image from Unsplash", extra={"ingredient": name})
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])

        if not results:
            logger.info("No ingredient image found", extra={"ingredient": name})
            return None

        logger.info("Ingredient image fetched", extra={"ingredient": name})
        return results[0]["urls"]["regular"]
    except requests.RequestException:
        logger.exception("Unsplash request failed for ingredient image")
        return None


def _recipe_key(recipe: models.Recipe) -> str:
    return str(recipe.name or "").strip().lower()


def _create_and_store_ai_recipe(
    user_ingredients: list[str],
    db: Session,
    filters: Optional[DietaryFilters] = None,
) -> models.Recipe:
    return _store_generated_recipe(generate_recipe(user_ingredients, filters=filters), db)


def _store_generated_recipe(
    recipe: GeneratedRecipe, db: Session, image_url: Optional[str] = None
) -> models.Recipe:
    recipe.image_url = image_url or fetch_recipe_image(recipe.name)
    recipe_data = recipe.model_dump()
    ingredient_tokens = _normalize_tokens_for_storage(
        extract_normalized_ingredient_tokens(recipe_data["ingredients"])
    )

    db_recipe = models.Recipe(**recipe_data, ingredient_tokens=ingredient_tokens)
    db.add(db_recipe)
    db.commit()
    db.refresh(db_recipe)
    logger.info("AI recipe generated and stored", extra={"recipe_id": db_recipe.id})
    return db_recipe


def assistant_logic(
    user_ingredients: list[str],
    db: Session,
    filters: Optional[DietaryFilters] = None,
):
    filters = filters or DietaryFilters()
    logger.info(
        "Assistant flow started",
        extra={"ingredient_count": len(user_ingredients), "filters": filters.model_dump()}
    )
    target_count = 3

    user_set = extract_normalized_ingredient_tokens(user_ingredients)

    cache_key = _cache_key(user_ingredients, filters)
    cached = _RECIPES_CACHE.get(cache_key)
    if cached:
        cached_at, cached_ids = cached
        if time.time() - cached_at <= _CACHE_TTL_SECONDS:
            cached_recipes = db.query(models.Recipe).filter(models.Recipe.id.in_(cached_ids)).all()
            cached_map = {r.id: r for r in cached_recipes}
            ordered = [cached_map[rid] for rid in cached_ids if rid in cached_map]
            return {"source": "cache", "results": ordered}
        _RECIPES_CACHE.pop(cache_key, None)

    results: list[models.Recipe] = []
    existing_keys: set[str] = set()

    query = db.query(models.Recipe)
    if user_set:
        query = query.filter(models.Recipe.ingredient_tokens.contains(list(user_set)))

    # Filters reject candidates after the query, so only cap the scan when none are set.
    candidates = query.all() if filters.is_active() else query.limit(target_count * 3).all()
    for recipe in candidates:
        recipe_set = extract_normalized_ingredient_tokens(recipe.ingredients)
        if user_set.issubset(recipe_set) and filters.matches(recipe):
            results.append(recipe)
            existing_keys.add(_recipe_key(recipe))
        if len(results) >= target_count:
            break

    attempts = 0
    max_attempts = target_count + 4

    while len(results) < target_count and attempts < max_attempts:
        attempts += 1
        logger.info(
            "Generating additional AI recipe",
            extra={"remaining": target_count - len(results), "attempt": attempts}
        )
        try:
            new_recipe = _create_and_store_ai_recipe(user_ingredients, db, filters)
        except Exception:
            logger.exception("AI generation failed")
            break
        problems = filters.violations(new_recipe.ingredients, new_recipe.time, new_recipe.calories)
        if problems:
            # Still saved (it's a valid recipe for other searches), just not shown here.
            logger.info(
                "Generated recipe ignored dietary filters",
                extra={"recipe_id": new_recipe.id, "problems": problems},
            )
            continue
        new_key = _recipe_key(new_recipe)
        if new_key in existing_keys:
            continue
        existing_keys.add(new_key)
        results.append(new_recipe)

    _RECIPES_CACHE[cache_key] = (time.time(), [r.id for r in results if getattr(r, "id", None)])

    return {
        "source": "database+ai" if results else "ai",
        "results": results
    }





def find_best_match(user_ingredients: list[str], db: Session):
    logger.info("Finding best match", extra={"ingredient_count": len(user_ingredients)})
    recipes = db.query(models.Recipe).all()

    best_match = None
    best_score = 0

    user_set = extract_normalized_ingredient_tokens(user_ingredients)

    for recipe in recipes:
        recipe_set = extract_normalized_ingredient_tokens(recipe.ingredients)
        if not recipe_set:
            continue

        intersection = user_set.intersection(recipe_set)
        score = len(intersection) / len(recipe_set)

        if score > best_score:
            best_score = score
            best_match = recipe

    return best_match, best_score


app = FastAPI()
logger.info("FastAPI application initialized")

# 🔥 ADD CORS RIGHT HERE
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# =========================
# Startup: create tables
# =========================
@app.on_event("startup")
def startup_event():
    logger.info("Startup: creating metadata tables if needed")
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        vector_ready = True
    except Exception:
        # The rest of the app works without pgvector; only /search needs it.
        logger.exception("Startup: pgvector unavailable, semantic search disabled")
        vector_ready = False
    tables = [
        t for t in models.Base.metadata.sorted_tables
        if vector_ready or t.name != models.RecipeEmbedding.__tablename__
    ]
    models.Base.metadata.create_all(bind=engine, tables=tables)
    if vector_ready:
        try:
            # create_all doesn't add columns to an existing table. Rows left with
            # a NULL search_vector are re-indexed by the next search.
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE recipe_embeddings ADD COLUMN IF NOT EXISTS search_vector tsvector"
                ))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_recipe_embeddings_search_vector "
                    "ON recipe_embeddings USING GIN (search_vector)"
                ))
        except Exception:
            logger.exception("Startup: failed to ensure keyword search column")
    try:
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE recipes ADD COLUMN IF NOT EXISTS cuisine VARCHAR")
            )
            conn.execute(
                text("ALTER TABLE recipes ADD COLUMN IF NOT EXISTS ingredient_tokens VARCHAR[]")
            )
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS idx_recipes_cuisine ON recipes (cuisine)")
            )
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS idx_recipes_ingredient_tokens ON recipes USING GIN (ingredient_tokens)")
            )
        logger.info("Startup: ensured cuisine/token columns and indexes exist")
    except Exception:
        logger.exception("Startup: failed to ensure cuisine/token columns")

    try:
        db = Session(bind=engine)
        recipes = db.query(models.Recipe).filter(models.Recipe.ingredient_tokens == None).all()  # noqa: E711
        updated = 0
        for recipe in recipes:
            tokens = _normalize_tokens_for_storage(
                extract_normalized_ingredient_tokens(recipe.ingredients)
            )
            recipe.ingredient_tokens = tokens
            updated += 1
        if updated:
            db.commit()
            logger.info("Startup: backfilled ingredient_tokens", extra={"count": updated})
        db.close()
    except Exception:
        logger.exception("Startup: failed to backfill ingredient_tokens")


# =========================
# Health checks
# =========================
@app.get("/health")
def health():
    logger.info("Health check called")
    return {"status": "ok"}


@app.get("/db-test")
def db_test(db: Session = Depends(get_db)):
    logger.info("DB test endpoint called")
    return {"db": "connected"}


# =========================
# Manual recipe CRUD
# =========================
@app.post("/recipes", response_model=RecipeResponse)
def create_recipe(
    recipe: RecipeCreate,
    db: Session = Depends(get_db)
):
    # "name" is a reserved LogRecord attribute; passing it in `extra` raises KeyError.
    logger.info("Creating manual recipe", extra={"recipe_name": recipe.name})
    ingredient_tokens = _normalize_tokens_for_storage(
        extract_normalized_ingredient_tokens(recipe.ingredients)
    )
    db_recipe = models.Recipe(
        name=recipe.name,
        servings=recipe.servings,
        time=recipe.time,
        calories=recipe.calories,
        cuisine=recipe.cuisine,
        ingredient_tokens=ingredient_tokens,
        ingredients=recipe.ingredients,
        instructions=recipe.instructions,
        notes=recipe.notes,
        image_url=recipe.image_url
    )

    db.add(db_recipe)
    db.commit()
    db.refresh(db_recipe)
    logger.info("Recipe created", extra={"recipe_id": db_recipe.id})

    return db_recipe


@app.get("/recipes", response_model=list[RecipeResponse])
def get_recipes(cuisine: Optional[str] = None, db: Session = Depends(get_db)):
    logger.info("Listing recipes", extra={"cuisine": cuisine})
    query = db.query(models.Recipe)
    if cuisine:
        wanted = normalize_cuisine(cuisine)
        stored = [raw for raw, _ in _stored_cuisine_counts(db) if normalize_cuisine(raw) == wanted]
        query = query.filter(models.Recipe.cuisine.in_(stored))
    recipes = query.order_by(models.Recipe.id.desc()).all()
    logger.info("Recipes listed", extra={"count": len(recipes)})
    return recipes


def _stored_cuisine_counts(db: Session) -> list[tuple[str, int]]:
    # Older rows hold non-canonical values ("italian"), so callers group by
    # normalize_cuisine() rather than trusting the stored spelling.
    return (
        db.query(models.Recipe.cuisine, func.count(models.Recipe.id))
        .filter(models.Recipe.cuisine.isnot(None))
        .group_by(models.Recipe.cuisine)
        .all()
    )


@app.get("/cuisines", response_model=list[CuisineCount])
def get_cuisines(db: Session = Depends(get_db)):
    """Cuisines that have at least one recipe, most recipes first."""
    counts: dict[str, int] = {}
    for raw, n in _stored_cuisine_counts(db):
        canonical = normalize_cuisine(raw)
        if canonical:
            counts[canonical] = counts.get(canonical, 0) + n
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [CuisineCount(cuisine=cuisine, count=n) for cuisine, n in ordered]


# =========================
# AI → DB pipeline
# =========================
@app.post("/ai/generate-recipe", response_model=RecipeResponse)
def ai_generate_recipe(
    data: IngredientsRequest,
    db: Session = Depends(get_db)
):
    logger.info("AI recipe generation endpoint called", extra={"ingredient_count": len(data.ingredients)})
    try:
        return _create_and_store_ai_recipe(data.ingredients, db, data.filters)
    except RecipeGenerationError as exc:
        logger.exception("AI recipe generation failed")
        raise HTTPException(status_code=502, detail="Recipe generation failed") from exc

@app.post("/recipes/search", response_model=list[RecipeResponse])
def search_recipes(
    data: RecipeSearchRequest,
    db: Session = Depends(get_db)
):
    logger.info(
        "Recipe search called",
        extra={
            "ingredient_count": len(data.ingredients),
            "min_match": data.min_match,
            "limit": data.limit
        }
    )
    user_set = extract_normalized_ingredient_tokens(data.ingredients)

    query = db.query(models.Recipe)
    if user_set:
        query = query.filter(models.Recipe.ingredient_tokens.contains(list(user_set)))
    recipes = query.all()
    scored = []

    for r in recipes:
        recipe_set = extract_normalized_ingredient_tokens(r.ingredients)

        if not recipe_set or not data.filters.matches(r):
            continue

        matched = user_set.intersection(recipe_set)
        match_score = len(matched) / len(recipe_set)  # how much of recipe you can make

        if match_score >= (data.min_match or 0):
            scored.append((match_score, r))

    # sort highest match first
    scored.sort(key=lambda x: x[0], reverse=True)

    # return only recipes
    results = [r for _, r in scored[: (data.limit or 10)]]
    logger.info("Recipe search completed", extra={"result_count": len(results)})
    return results

@app.post("/assistant", response_model=AssistantResponse)
def assistant(data: IngredientsRequest, db: Session = Depends(get_db)):
    logger.info("Assistant endpoint called", extra={"ingredient_count": len(data.ingredients)})
    result = assistant_logic(data.ingredients, db, data.filters)
    logger.info("Assistant endpoint completed", extra={"source": result.get("source")})
    return result

@app.get("/ingredient-image")
def get_ingredient_image(name: str, db: Session = Depends(get_db)):
    logger.info("Ingredient image requested", extra={"ingredient": name})

    name = name.lower()

    # 1️⃣ Check if already stored
    existing = db.query(models.IngredientImage).filter_by(name=name).first()

    if existing:
        logger.info("Ingredient image served from cache", extra={"ingredient": name})
        return {"image_url": existing.image_url}

    # 2️⃣ Fetch from Unsplash
    image_url = fetch_ingredient_image_from_unsplash(name)

    if not image_url:
        logger.info("Ingredient image not available", extra={"ingredient": name})
        return {"image_url": None}

    # 3️⃣ Save to DB
    new_image = models.IngredientImage(
        name=name,
        image_url=image_url
    )

    db.add(new_image)
    db.commit()
    logger.info("Ingredient image cached", extra={"ingredient": name})

    return {"image_url": image_url}


@app.get("/substitutions", response_model=SubstitutionResponse)
def get_substitutions(ingredient: str, db: Session = Depends(get_db)):
    logger.info("Substitutions requested", extra={"ingredient": ingredient})
    key = substitution_key(ingredient)
    if not key:
        raise HTTPException(status_code=400, detail="Ingredient name is empty")

    # 1️⃣ Hand-picked list
    substitutes = lookup_substitutes(ingredient)
    if substitutes:
        return SubstitutionResponse(ingredient=ingredient, substitutes=substitutes, source="dict")

    # 2️⃣ Previously generated
    cached = db.query(models.IngredientSubstitution).filter_by(ingredient_key=key).first()
    if cached:
        return SubstitutionResponse(ingredient=ingredient, substitutes=cached.substitutes, source="cache")

    # 3️⃣ Ask the LLM and cache the answer
    try:
        substitutes = suggest_substitutes(ingredient)
    except RecipeGenerationError as exc:
        logger.exception("AI substitution failed")
        raise HTTPException(status_code=502, detail="Could not suggest substitutes") from exc

    db.add(models.IngredientSubstitution(ingredient_key=key, substitutes=substitutes))
    try:
        db.commit()
    except IntegrityError:
        # A concurrent request cached the same ingredient first; this answer is still valid.
        db.rollback()
    return SubstitutionResponse(ingredient=ingredient, substitutes=substitutes, source="ai")


@app.post("/recipes/{recipe_id}/shopping-list", response_model=ShoppingListResponse)
def get_shopping_list(recipe_id: int, data: ShoppingListRequest, db: Session = Depends(get_db)):
    recipe = db.get(models.Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    logger.info("Shopping list requested", extra={"recipe_id": recipe_id, "have_count": len(data.have)})
    return build_shopping_list(recipe.ingredients, data.have)


@app.post("/search", response_model=SearchResponse)
def search_by_craving(data: SearchRequest, db: Session = Depends(get_db)):
    """Semantic search: "something light and spicy for a cold night"."""
    logger.info("Semantic search", extra={"query_length": len(data.query), "limit": data.limit})
    try:
        hits = semantic_search(db, data.query, data.limit, data.filters)
    except EmbeddingError as exc:
        logger.exception("Semantic search failed")
        raise HTTPException(status_code=502, detail="Semantic search is unavailable") from exc
    return {
        "query": data.query,
        "results": [{"score": round(score, 4), "recipe": recipe} for recipe, score in hits],
    }


# Inspiration recipes passed to the model; more makes the prompt slower without clear gains.
CRAVING_SOURCE_COUNT = 3
# Generations allowed when the model ignores the dietary filters or copies a source.
CRAVING_ATTEMPTS = 2


@app.post("/search/generate", response_model=CravingRecipeResponse)
def generate_for_craving(data: CravingRecipeRequest, db: Session = Depends(get_db)):
    """RAG: retrieve the best matches for a craving, then generate a new recipe from them."""
    logger.info("Craving recipe requested", extra={"query_length": len(data.query)})
    try:
        hits = semantic_search(db, data.query, CRAVING_SOURCE_COUNT, data.filters)
    except EmbeddingError as exc:
        logger.exception("Retrieval for craving recipe failed")
        raise HTTPException(status_code=502, detail="Semantic search is unavailable") from exc
    sources = [recipe for recipe, _ in hits]

    for attempt in range(1, CRAVING_ATTEMPTS + 1):
        try:
            recipe = generate_from_craving(data.query, sources, filters=data.filters)
        except RecipeGenerationError as exc:
            logger.exception("Craving recipe generation failed")
            raise HTTPException(status_code=502, detail="Recipe generation failed") from exc
        ingredients = [i.model_dump() for i in recipe.ingredients]
        problems = data.filters.violations(ingredients, recipe.time, recipe.calories)
        copied = near_copy_of(recipe.name, ingredients, sources)
        if copied:
            # The prompt asks for a new recipe; the RAG eval caught one that wasn't.
            problems.append(f"too similar to {copied!r}")
        if not problems:
            break
        logger.info("Craving recipe rejected", extra={"attempt": attempt, "problems": problems})
    else:
        raise HTTPException(
            status_code=422,
            detail="Couldn't generate a new recipe that fits; try rewording the craving or loosening your preferences",
        )

    return {
        "recipe": _store_generated_recipe(recipe, db),
        "inspired_by": [{"id": s.id, "name": s.name} for s in sources],
    }


# One retry when the model hands back the recipe without applying the change.
REFINE_ATTEMPTS = 2


def _recipe_content(servings, time_, calories, ingredients, instructions, notes) -> tuple:
    """What a refinement should change; the name alone doesn't count."""
    def norm(value):
        return " ".join(str(value or "").lower().split())

    return (
        norm(servings), norm(time_), norm(calories), norm(notes),
        sorted((norm(i.get("quantity")), norm(i.get("name"))) for i in ingredients or [] if isinstance(i, dict)),
        [[norm(step) for step in s.get("steps") or []] for s in instructions or [] if isinstance(s, dict)],
    )


def _unchanged(source: models.Recipe, refined: GeneratedRecipe) -> bool:
    data = refined.model_dump()
    return _recipe_content(
        source.servings, source.time, source.calories, source.ingredients, source.instructions, source.notes
    ) == _recipe_content(
        data["servings"], data["time"], data["calories"], data["ingredients"], data["instructions"], data["notes"]
    )


@app.post("/recipes/{recipe_id}/refine", response_model=RefineResponse)
def refine(recipe_id: int, data: RefineRequest, db: Session = Depends(get_db)):
    """Edit a recipe conversationally ("for 6 people", "spicier") and save the result as a new recipe.

    The original stays as it was, so favorites and history snapshots still point at it.
    """
    source = db.get(models.Recipe, recipe_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    logger.info("Recipe refinement requested", extra={"recipe_id": recipe_id})

    for attempt in range(1, REFINE_ATTEMPTS + 1):
        try:
            refined = refine_recipe(source, data.instruction, previous_attempt_unchanged=attempt > 1)
        except RecipeGenerationError as exc:
            logger.exception("Recipe refinement failed")
            raise HTTPException(status_code=502, detail="Recipe refinement failed") from exc
        if not _unchanged(source, refined):
            break
        logger.info("Refinement returned the recipe unchanged", extra={"attempt": attempt})
    else:
        raise HTTPException(status_code=422, detail="Couldn't apply that change; try rewording it")

    scaled = scale_for_new_servings(source, refined)
    if scaled:
        logger.info("Scaled quantities the model left unscaled", extra={"count": scaled})

    # Same dish, so keep its photo instead of searching for a new one.
    stored = _store_generated_recipe(refined, db, image_url=source.image_url)
    return {"recipe": stored, "refined_from": {"id": source.id, "name": source.name}}
