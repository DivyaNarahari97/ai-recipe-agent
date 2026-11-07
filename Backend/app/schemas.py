import logging
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)
logger.debug("Schemas module loaded")

class RecipeCreate(BaseModel):
    name: str
    servings: Optional[str] = None
    time: Optional[str] = None
    calories: Optional[str] = None

    ingredients: List[Dict[str, Any]]
    instructions: List[Dict[str, Any]]

    notes: Optional[str] = None
    image_url: Optional[str] = None


class GeneratedIngredient(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True, str_strip_whitespace=True)

    name: str = Field(min_length=1)
    quantity: Optional[str] = None


class GeneratedInstructionSection(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    section: Optional[str] = None
    steps: List[str] = Field(min_length=1)


class GeneratedRecipe(RecipeCreate):
    """LLM output contract: the fields the frontend reads must have the right shape."""

    # The model often returns numbers here (e.g. "servings": 4); the DB stores strings.
    model_config = ConfigDict(coerce_numbers_to_str=True, str_strip_whitespace=True)

    name: str = Field(min_length=1)
    ingredients: List[GeneratedIngredient] = Field(min_length=1)
    instructions: List[GeneratedInstructionSection] = Field(min_length=1)


class RecipeResponse(RecipeCreate):
    id: int

    class Config:
        from_attributes = True
