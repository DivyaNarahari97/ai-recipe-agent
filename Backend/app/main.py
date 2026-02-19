from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db import get_db, engine
from app import models
from app.schemas import RecipeCreate, RecipeResponse
from app.ai import generate_recipe, fetch_recipe_image
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

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

def assistant_logic(user_ingredients: list[str], db: Session):
    THRESHOLD = 0.6

    recipes = db.query(models.Recipe).all()
    ranked_recipes = []

    user_set = set(i.lower() for i in user_ingredients)

    for recipe in recipes:
        recipe_set = set(item["name"].lower() for item in recipe.ingredients)

        if not recipe_set:
            continue

        # Primary ingredient check
        primary = recipe.ingredients[0]["name"].lower()
        if primary not in user_set:
            continue

        matched = user_set.intersection(recipe_set)
        match_score = len(matched) / len(recipe_set)

        if match_score > 0:
            ranked_recipes.append((match_score, recipe))

    # If no DB match → call AI
    if not ranked_recipes:
        logger.info("Recipe source: AI")
        recipe_data = generate_recipe(user_ingredients)

        # Attach image
        image_url = fetch_recipe_image(recipe_data["name"])
        recipe_data["image_url"] = image_url



        # Save to DB
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
        
        return {
            "source": "ai",
            "results": [db_recipe]
        }

    # Sort by match score
    ranked_recipes.sort(key=lambda x: x[0], reverse=True)
    best_recipe = ranked_recipes[0][1]
    logger.info("Recipe source: DATABASE")
    return {
        "source": "database",
        "results": [best_recipe]
    }




def find_best_match(user_ingredients: list[str], db: Session):
    recipes = db.query(models.Recipe).all()

    best_match = None
    best_score = 0

    user_set = set(i.lower() for i in user_ingredients)

    for recipe in recipes:
        recipe_set = set(i.lower() for i in recipe.ingredients)

        intersection = user_set.intersection(recipe_set)
        score = len(intersection) / len(recipe_set)

        if score > best_score:
            best_score = score
            best_match = recipe

    return best_match, best_score




app = FastAPI()

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
    models.Base.metadata.create_all(bind=engine)


# =========================
# Health checks
# =========================
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/db-test")
def db_test(db: Session = Depends(get_db)):
    return {"db": "connected"}


# =========================
# Manual recipe CRUD
# =========================
@app.post("/recipes", response_model=RecipeResponse)
def create_recipe(
    recipe: RecipeCreate,
    db: Session = Depends(get_db)
):
    db_recipe = models.Recipe(
        name=recipe.name,
        ingredients=recipe.ingredients,
        steps=recipe.steps,
        estimated_calories=recipe.estimated_calories,
        image_url=recipe_data.get("image_url")
    )

    db.add(db_recipe)
    db.commit()
    db.refresh(db_recipe)

    return db_recipe


@app.get("/recipes", response_model=list[RecipeResponse])
def get_recipes(db: Session = Depends(get_db)):
    return db.query(models.Recipe).all()


# =========================
# AI → DB pipeline
# =========================
@app.post("/ai/generate-recipe", response_model=RecipeResponse)
def ai_generate_recipe(
    data: IngredientsRequest,
    db: Session = Depends(get_db)
):
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

    # 3️⃣ Return stored recipe
    return db_recipe

@app.post("/recipes/search", response_model=list[RecipeResponse])
def search_recipes(
    data: RecipeSearchRequest,
    db: Session = Depends(get_db)
):
    user_set = set(i.lower() for i in user_ingredients)

    recipes = db.query(models.Recipe).all()
    scored = []

    for r in recipes:
        recipe_ings = [x.strip().lower() for x in (r.ingredients or [])]
        recipe_set = set(item["name"].lower() for item in recipe.ingredients)

        if not recipe_set:
            continue

        matched = user_set.intersection(recipe_set)
        match_score = len(matched) / len(recipe_set)  # how much of recipe you can make

        if match_score >= (data.min_match or 0):
            scored.append((match_score, r))

    # sort highest match first
    scored.sort(key=lambda x: x[0], reverse=True)

    # return only recipes
    return [r for _, r in scored[: (data.limit or 10)]]

@app.post("/assistant")
def assistant(data: IngredientsRequest, db: Session = Depends(get_db)):
    result = assistant_logic(data.ingredients, db)
    return result
