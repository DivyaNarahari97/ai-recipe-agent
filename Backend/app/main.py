import logging
import os
from typing import Optional

import requests
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models
from app.ai import fetch_recipe_image, generate_recipe
from app.db import engine, get_db
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


def assistant_logic(user_ingredients: list[str], db: Session):
    logger.info("Assistant flow started", extra={"ingredient_count": len(user_ingredients)})

    recipes = db.query(models.Recipe).all()
    user_set = set(i.lower() for i in user_ingredients)

    matching_recipes = []

    for recipe in recipes:
        recipe_set = _extract_ingredient_names(recipe.ingredients)

        # Check if recipe contains ALL user ingredients
        if user_set.issubset(recipe_set):
            matching_recipes.append(recipe)

    # If full match found → return first one
    if matching_recipes:
        logger.info("Assistant matched recipe from database")
        return {
            "source": "database",
            "results": [matching_recipes[0]]
        }

    # Otherwise call AI
    logger.info("No full DB match, generating recipe via AI")
    recipe_data = generate_recipe(user_ingredients)

    image_url = fetch_recipe_image(recipe_data["name"])
    recipe_data["image_url"] = image_url

    db_recipe = models.Recipe(
        name=recipe_data["name"],
        servings=recipe_data["servings"],
        time=recipe_data["time"],
        calories=recipe_data["calories"],
        ingredients=recipe_data["ingredients"],
        instructions=recipe_data["instructions"],
        notes=recipe_data["notes"],
        image_url=recipe_data.get("image_url")
    )

    db.add(db_recipe)
    db.commit()
    db.refresh(db_recipe)
    logger.info("AI recipe generated and stored", extra={"recipe_id": db_recipe.id})

    return {
        "source": "ai",
        "results": [db_recipe]
    }





def find_best_match(user_ingredients: list[str], db: Session):
    logger.info("Finding best match", extra={"ingredient_count": len(user_ingredients)})
    recipes = db.query(models.Recipe).all()

    best_match = None
    best_score = 0

    user_set = set(i.lower() for i in user_ingredients)

    for recipe in recipes:
        recipe_set = _extract_ingredient_names(recipe.ingredients)
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
    db_recipe = models.Recipe(
        name=recipe.name,
        servings=recipe.servings,
        time=recipe.time,
        calories=recipe.calories,
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
    # 1️⃣ Call AI
    recipe_data = generate_recipe(data.ingredients)

    # 2️⃣ Generate dynamic image URL
    image_query = recipe_data["name"].replace(" ", "+")
    recipe_data["image_url"] = f"https://source.unsplash.com/1200x800/?{image_query},food"

    # 3️⃣ Save to DB
    db_recipe = models.Recipe(
    name=recipe_data["name"],
    servings=recipe_data["servings"],
    time=recipe_data["time"],
    calories=recipe_data["calories"],
    ingredients=recipe_data["ingredients"],
    instructions=recipe_data["instructions"],
    notes=recipe_data["notes"],
    image_url=recipe_data.get("image_url")
)

    db.add(db_recipe)
    db.commit()
    db.refresh(db_recipe)
    logger.info("AI recipe stored", extra={"recipe_id": db_recipe.id})

    # 3️⃣ Return stored recipe
    return db_recipe

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
    user_set = set(i.lower() for i in data.ingredients)

    recipes = db.query(models.Recipe).all()
    scored = []

    for r in recipes:
        recipe_set = _extract_ingredient_names(r.ingredients)

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
