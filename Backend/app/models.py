import logging

from sqlalchemy import Column, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()
logger = logging.getLogger(__name__)
logger.debug("Models module loaded")

class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)

    servings = Column(String)
    time = Column(String)
    calories = Column(String)

    cuisine = Column(String)
    ingredient_tokens = Column(ARRAY(String))

    ingredients = Column(JSONB, nullable=False)
    instructions = Column(JSONB, nullable=False)

    notes = Column(String)
    image_url = Column(String)

class IngredientSubstitution(Base):
    """LLM-suggested substitutes, cached by normalized ingredient key."""

    __tablename__ = "ingredient_substitutions"

    id = Column(Integer, primary_key=True, index=True)
    ingredient_key = Column(String, unique=True, index=True, nullable=False)
    substitutes = Column(ARRAY(String), nullable=False)


class IngredientImage(Base):
    __tablename__ = "ingredient_images"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    image_url = Column(String)
