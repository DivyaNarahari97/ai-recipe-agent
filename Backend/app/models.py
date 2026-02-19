from sqlalchemy import Column, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()

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
