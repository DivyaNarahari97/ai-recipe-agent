from typing import List
from pydantic import BaseModel

class RecipeCreate(BaseModel):
    name: str
    ingredients: List[str]
    steps: List[str]
    estimated_calories: int

class RecipeResponse(RecipeCreate):
    id: int

    class Config:
        from_attributes = True
