import logging

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import declarative_base

from app.embeddings import EMBED_DIM

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

class RecipeEmbedding(Base):
    """One vector per recipe for semantic search (needs the pgvector extension)."""

    __tablename__ = "recipe_embeddings"

    recipe_id = Column(Integer, ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True)
    model = Column(String, nullable=False)
    # Hash of model + embedded text, so a changed recipe or model can be re-embedded.
    content_hash = Column(String, nullable=False)
    embedding = Column(Vector(EMBED_DIM), nullable=False)
    # Same text as the embedding, for the keyword half of hybrid search.
    search_vector = Column(TSVECTOR)

    __table_args__ = (
        Index(
            "idx_recipe_embeddings_hnsw",
            embedding,
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("idx_recipe_embeddings_search_vector", search_vector, postgresql_using="gin"),
    )


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
