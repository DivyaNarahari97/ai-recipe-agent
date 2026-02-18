from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db import get_db, engine
from app import models
from app.schemas import RecipeCreate, RecipeResponse
from app.ai import generate_recipe
from typing import Optional

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
        recipe_set = set(i.lower() for i in recipe.ingredients)

        matched = user_set.intersection(recipe_set)
        match_score = len(matched) / len(recipe_set)

        if match_score > 0:
            missing = list(recipe_set - user_set)

            # Substitution logic
            substitutions = {}
            for item in missing:
                if item in SUBSTITUTIONS:
                    substitutions[item] = SUBSTITUTIONS[item]

            explanation = f"You match {len(matched)} out of {len(recipe_set)} ingredients."

            if missing:
                explanation += f" You are missing: {', '.join(missing)}."

                if substitutions:
                    explanation += " Possible substitutions: "
                    for k, v in substitutions.items():
                        explanation += f"For {k}, try {', '.join(v)}. "

            ranked_recipes.append({
                "id": recipe.id,
                "name": recipe.name,
                "ingredients": recipe.ingredients,
                "steps": recipe.steps,
                "estimated_calories": recipe.estimated_calories,
                "match_score": round(match_score, 2),
                "matched_ingredients": list(matched),
                "missing_ingredients": missing,
                "substitutions": substitutions,
                "explanation": explanation
            })

    if not ranked_recipes:
        recipe_data = generate_recipe(user_ingredients)
        return {
            "source": "ai",
            "results": [recipe_data]
        }

    ranked_recipes.sort(key=lambda x: x["match_score"], reverse=True)
    top_results = ranked_recipes[:3]

    if top_results[0]["match_score"] < THRESHOLD:
        recipe_data = generate_recipe(user_ingredients)
        return {
            "source": "ai",
            "results": [recipe_data]
        }

    return {
        "source": "database",
        "results": top_results
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
        estimated_calories=recipe.estimated_calories
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

    # 2️⃣ Persist to DB
    db_recipe = models.Recipe(
        name=recipe_data["name"],
        ingredients=recipe_data["ingredients"],
        steps=recipe_data["steps"],
        estimated_calories=recipe_data["estimated_calories"]
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
    user_set = set(i.strip().lower() for i in data.ingredients if i.strip())

    recipes = db.query(models.Recipe).all()
    scored = []

    for r in recipes:
        recipe_ings = [x.strip().lower() for x in (r.ingredients or [])]
        recipe_set = set(recipe_ings)

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
