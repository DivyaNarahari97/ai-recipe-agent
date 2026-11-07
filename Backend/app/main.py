import logging
import os
import re
import time
from typing import Optional

import requests
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models
from app.ai import RecipeGenerationError, fetch_recipe_image, generate_recipe
from app.db import engine, get_db
from app.ingredients import extract_normalized_ingredient_tokens
from app.schemas import RecipeCreate, RecipeResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

logger = logging.getLogger(__name__)
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")


class RecipeSearchRequest(BaseModel):
    ingredients: list[str]
    min_match: Optional[float] = 0.5   # 50% match by default
    limit: Optional[int] = 10

SUBSTITUTIONS = {
    "tomato": ["yogurt", "lemon juice", "tomato paste"],
    "milk": ["cream", "yogurt"],
    "butter": ["oil", "ghee"],
    "onion": ["shallots"],
    "potato": ["sweet potato"]
}


# =========================
# Request Schemas
# =========================
class IngredientsRequest(BaseModel):
    ingredients: list[str]


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


def _cache_key(ingredients: list[str]) -> tuple:
    cleaned = sorted({str(i).strip().lower() for i in ingredients if str(i).strip()})
    return (tuple(cleaned),)


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
    db: Session
) -> models.Recipe:
    recipe = generate_recipe(user_ingredients)
    recipe.image_url = fetch_recipe_image(recipe.name)
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


def assistant_logic(user_ingredients: list[str], db: Session):
    logger.info(
        "Assistant flow started",
        extra={"ingredient_count": len(user_ingredients)}
    )
    target_count = 3

    user_set = extract_normalized_ingredient_tokens(user_ingredients)

    cache_key = _cache_key(user_ingredients)
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

    for recipe in query.limit(target_count * 3).all():
        recipe_set = extract_normalized_ingredient_tokens(recipe.ingredients)
        if user_set.issubset(recipe_set):
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
            new_recipe = _create_and_store_ai_recipe(user_ingredients, db)
        except Exception:
            logger.exception("AI generation failed")
            break
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
    models.Base.metadata.create_all(bind=engine)
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
    logger.info("Creating manual recipe", extra={"name": recipe.name})
    ingredient_tokens = _normalize_tokens_for_storage(
        extract_normalized_ingredient_tokens(recipe.ingredients)
    )
    db_recipe = models.Recipe(
        name=recipe.name,
        servings=recipe.servings,
        time=recipe.time,
        calories=recipe.calories,
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
def get_recipes(db: Session = Depends(get_db)):
    logger.info("Listing recipes")
    recipes = db.query(models.Recipe).all()
    logger.info("Recipes listed", extra={"count": len(recipes)})
    return recipes


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
        return _create_and_store_ai_recipe(data.ingredients, db)
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

        if not recipe_set:
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

@app.post("/assistant")
def assistant(data: IngredientsRequest, db: Session = Depends(get_db)):
    logger.info("Assistant endpoint called", extra={"ingredient_count": len(data.ingredients)})
    result = assistant_logic(data.ingredients, db)
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
