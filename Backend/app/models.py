import logging

from sqlalchemy import Column, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
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

    ingredients = Column(JSONB, nullable=False)
    instructions = Column(JSONB, nullable=False)

    notes = Column(String)
    image_url = Column(String)

class IngredientImage(Base):
    __tablename__ = "ingredient_images"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    image_url = Column(String)
