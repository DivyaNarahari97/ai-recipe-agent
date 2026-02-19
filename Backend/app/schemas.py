from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class RecipeCreate(BaseModel):
    name: str
    servings: Optional[str] = None
    time: Optional[str] = None
    calories: Optional[str] = None

    ingredients: List[Dict[str, Any]]
    instructions: List[Dict[str, Any]]

    notes: Optional[str] = None
    image_url: Optional[str] = None


class RecipeResponse(RecipeCreate):
    id: int

    class Config:
        from_attributes = True
