import logging
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.dietary import DietaryFilters, dietary_tags

logger = logging.getLogger(__name__)
logger.debug("Schemas module loaded")

# Fixed list so the browse filter doesn't split "Italian" / "italian" / "Italian-American".
CUISINES = (
    "American",
    "Chinese",
    "French",
    "Greek",
    "Indian",
    "Italian",
    "Japanese",
    "Korean",
    "Mediterranean",
    "Mexican",
    "Middle Eastern",
    "Thai",
    "Other",
)
_CUISINE_LOOKUP = {c.lower(): c for c in CUISINES}


def normalize_cuisine(value: Any) -> Optional[str]:
    """Map to a canonical cuisine; unknown labels become "Other" rather than failing."""
    if not isinstance(value, str) or not value.strip():
        return None
    return _CUISINE_LOOKUP.get(value.strip().lower(), "Other")


class RecipeCreate(BaseModel):
    name: str
    servings: Optional[str] = None
    time: Optional[str] = None
    calories: Optional[str] = None
    cuisine: Optional[str] = None

    ingredients: List[Dict[str, Any]]
    instructions: List[Dict[str, Any]]

    notes: Optional[str] = None
    image_url: Optional[str] = None

    @field_validator("cuisine", mode="before")
    @classmethod
    def _normalize_cuisine(cls, value):
        return normalize_cuisine(value)


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


class GeneratedSubstitutes(BaseModel):
    """LLM output contract for ingredient swaps."""

    substitutes: List[str] = Field(min_length=1)

    @field_validator("substitutes")
    @classmethod
    def _clean(cls, values: List[str]) -> List[str]:
        cleaned: List[str] = []
        for value in values:
            value = value.strip()
            if value and value.lower() not in {c.lower() for c in cleaned}:
                cleaned.append(value)
        if not cleaned:
            raise ValueError("no usable substitutes")
        return cleaned[:3]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=6, ge=1, le=20)
    filters: DietaryFilters = DietaryFilters()


class SubstitutionResponse(BaseModel):
    ingredient: str
    substitutes: List[str]
    source: str  # "dict", "cache" or "ai"


class CuisineCount(BaseModel):
    cuisine: str
    count: int


class RecipeResponse(RecipeCreate):
    id: int

    class Config:
        from_attributes = True

    @computed_field
    @property
    def dietary_tags(self) -> List[str]:
        return sorted(dietary_tags(self.ingredients))


class AssistantResponse(BaseModel):
    source: str
    results: List[RecipeResponse]


class SearchHit(BaseModel):
    score: float  # reciprocal-rank-fusion score, higher is better
    recipe: RecipeResponse


class SearchResponse(BaseModel):
    query: str
    results: List[SearchHit]


class CravingRecipeRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    filters: DietaryFilters = DietaryFilters()


class RecipeRef(BaseModel):
    id: int
    name: str


class CravingRecipeResponse(BaseModel):
    recipe: RecipeResponse
    inspired_by: List[RecipeRef]


class ShoppingListRequest(BaseModel):
    have: List[str] = []


class ShoppingListResponse(BaseModel):
    need: List[Dict[str, Any]]
    have: List[Dict[str, Any]]
    staples: List[Dict[str, Any]]
