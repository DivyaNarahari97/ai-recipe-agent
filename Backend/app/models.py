from sqlalchemy import Column, Integer, String, ARRAY
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    ingredients = Column(ARRAY(String), nullable=False)
    steps = Column(ARRAY(String), nullable=False)
    estimated_calories = Column(Integer)
