"""Re-embed every recipe whose text or embedding model changed.

Search already embeds new recipes on demand; run this after changing
recipe_document() or EMBED_MODEL:  python -m app.index_recipes
"""
import logging

from app.db import SessionLocal
from app.semantic_search import index_missing, reindex_stale


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        added = index_missing(db)
        refreshed = reindex_stale(db)
        print(f"Embedded {added} new and {refreshed} changed recipes.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
