from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db import get_db, engine
from app import models
from app.schemas import RecipeCreate, RecipeResponse
from app.ai import generate_recipe


# =========================
# Request Schemas
# =========================
class IngredientsRequest(BaseModel):
    ingredients: list[str]


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
