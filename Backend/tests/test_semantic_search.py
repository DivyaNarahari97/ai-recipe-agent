import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Must be set before app.main loads app.db, so tests can never reach a real database.
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost/unused"

import requests
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app import embeddings, main, semantic_search
from app.ai import RecipeGenerationError, generate_from_craving
from app.dietary import DietaryFilters
from app.embeddings import EMBED_DIM, EmbeddingError, descriptors, embed, recipe_document
from app.schemas import CravingRecipeRequest, GeneratedRecipe, SearchRequest
from tests.test_ai_path import VALID, scripted


def recipe(recipe_id, name, ingredients=("rice",), time="30 minutes", calories="400 kcal", **extra):
    return SimpleNamespace(
        id=recipe_id, name=name, ingredients=[{"name": n} for n in ingredients],
        instructions=[{"section": "Cook", "steps": ["Boil.", "Serve."]}],
        time=time, calories=calories, cuisine=extra.get("cuisine"), notes=extra.get("notes"),
    )


class DocumentTests(unittest.TestCase):
    def test_document_has_the_searchable_fields(self):
        doc = recipe_document(recipe(1, "Dal", ("lentils", "green chillies"), "15 min", "250 kcal",
                                     cuisine="Indian", notes="Serve hot."))
        for part in ("Dal.", "Cuisine: Indian.", "vegan", "Style: light, quick, spicy.",
                     "Ingredients: lentils, green chillies.", "Notes: Serve hot.", "Steps: Boil. Serve."):
            self.assertIn(part, doc)

    def test_style_words_can_be_left_out(self):
        self.assertNotIn("Style:", recipe_document(recipe(1, "Dal", ("chili",)), include_descriptors=False))

    def test_descriptors(self):
        self.assertEqual(descriptors(recipe(1, "x", calories="700 kcal", time="1 hour")), ["hearty"])
        self.assertEqual(descriptors(recipe(1, "x", calories=None, time=None)), [])

    def test_hash_changes_with_text(self):
        self.assertNotEqual(embeddings.content_hash("a"), embeddings.content_hash("b"))


class EmbedTests(unittest.TestCase):
    def response(self, vectors):
        resp = MagicMock()
        resp.json.return_value = {"embeddings": vectors}
        return resp

    def test_returns_vectors(self):
        with patch.object(embeddings.requests, "post", return_value=self.response([[0.1] * EMBED_DIM])):
            self.assertEqual(len(embed(["x"])[0]), EMBED_DIM)

    def test_wrong_shape_or_outage_raises(self):
        for side_effect in (
            [self.response([[0.1] * 3])],
            [self.response([])],
            requests.ConnectionError(),
        ):
            with self.subTest(side_effect=side_effect), patch.object(
                embeddings.requests, "post", side_effect=side_effect
            ), self.assertRaises(EmbeddingError):
                embed(["x"])


class FusionTests(unittest.TestCase):
    def test_rewards_ids_found_by_both_rankers(self):
        fused = semantic_search.reciprocal_rank_fusion([1, 2, 3], [3, 4])
        self.assertEqual([i for i, _ in fused], [3, 1, 2, 4])
        self.assertAlmostEqual(dict(fused)[3], 1 / 63 + 1 / 61)

    def test_one_empty_ranking_keeps_the_other_order(self):
        self.assertEqual([i for i, _ in semantic_search.reciprocal_rank_fusion([5, 6], [])], [5, 6])


class RankingTests(unittest.TestCase):
    def test_keeps_best_copy_of_duplicates_and_applies_filters(self):
        rows = [
            (recipe(1, "Corn Pakoda"), 0.9),
            (recipe(2, "corn  pakoda"), 0.8),
            (recipe(3, "Chicken Curry", ("chicken",)), 0.7),
            (recipe(4, "Dal"), 0.6),
            (recipe(5, "Salad"), 0.5),
        ]
        hits = semantic_search._best_distinct(rows, DietaryFilters(vegetarian=True), limit=2)
        self.assertEqual([(r.id, s) for r, s in hits], [(1, 0.9), (4, 0.6)])

    def test_search_fuses_both_rankers(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [
            recipe(1, "Pakoda"), recipe(2, "Dal"), recipe(3, "Soup")
        ]
        with patch.object(semantic_search, "index_missing") as index, patch.object(
            semantic_search, "_vector_ranking", return_value=[1, 2, 3]
        ), patch.object(semantic_search, "_keyword_ranking", return_value=[3, 2]):
            hits = semantic_search.search(db, "cozy soup", limit=2)
        index.assert_called_once_with(db)
        # 2 and 3 are found by both rankers, so they beat 1, the vector-only top hit.
        self.assertEqual([r.name for r, _ in hits], ["Soup", "Dal"])

    def test_vector_ranking_uses_query_prefix(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [(7,)]
        with patch.object(semantic_search, "embed", return_value=[[0.0] * EMBED_DIM]) as embed_mock:
            self.assertEqual(semantic_search._vector_ranking(db, "cozy soup"), [7])
        self.assertEqual(embed_mock.call_args.args[0], ["search_query: cozy soup"])

    def test_keyword_query_ors_the_words(self):
        db = MagicMock()
        db.execute.return_value.all.return_value = [(4,), (9,)]
        self.assertEqual(semantic_search._keyword_ranking(db, "light spicy"), [4, 9])
        sql = str(db.execute.call_args.args[0])
        self.assertIn("replace(CAST(plainto_tsquery('english', :query) AS text), '&', '|')", sql)
        self.assertIn("ts_rank_cd(search_vector, q, 1)", sql)


class IndexTests(unittest.TestCase):
    def test_documents_are_upserted_in_batches_with_keyword_index(self):
        db = MagicMock()
        recipes = [recipe(i, f"R{i}") for i in range(semantic_search._BATCH_SIZE + 1)]
        with patch.object(semantic_search, "embed", side_effect=lambda t: [[0.0] * EMBED_DIM] * len(t)) as e:
            self.assertEqual(semantic_search._embed_and_store(db, recipes), len(recipes))
        self.assertEqual([len(c.args[0]) for c in e.call_args_list], [semantic_search._BATCH_SIZE, 1])
        self.assertTrue(e.call_args_list[0].args[0][0].startswith("search_document: R0."))
        self.assertEqual(db.execute.call_count, len(recipes))
        self.assertEqual(db.commit.call_count, 2)
        sql = str(db.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
        self.assertIn("to_tsvector", sql)
        self.assertIn("ON CONFLICT (recipe_id) DO UPDATE", sql)


class CravingGenerationTests(unittest.TestCase):
    def test_prompt_includes_craving_and_sources(self):
        model = scripted(json.dumps(VALID))
        sources = [recipe(1, "Dal", ("lentils", "cumin"), cuisine="Indian")]
        generate_from_craving("something cozy", sources, call_model=model, filters=DietaryFilters(vegan=True))
        prompt = model.call_args.args[0]
        self.assertIn('craving: "something cozy"', prompt)
        self.assertIn("- Dal (cuisine Indian; time 30 minutes; calories 400 kcal). Ingredients: lentils, cumin.", prompt)
        self.assertIn("do not copy", prompt)
        self.assertIn('"ingredients": [', prompt)
        self.assertIn("Vegan", prompt)

    def test_without_sources_there_is_no_inspiration_section(self):
        model = scripted(json.dumps(VALID))
        generate_from_craving("something cozy", [], call_model=model)
        self.assertNotIn("inspiration", model.call_args.args[0])


class EndpointTests(unittest.TestCase):
    def test_embedding_outage_returns_502(self):
        with patch.object(main, "semantic_search", side_effect=EmbeddingError("down")):
            with self.assertRaises(HTTPException) as caught:
                main.search_by_craving(SearchRequest(query="soup"), MagicMock())
        self.assertEqual(caught.exception.status_code, 502)

    def test_query_must_not_be_empty(self):
        with self.assertRaises(ValueError):
            SearchRequest(query="")


class CravingEndpointTests(unittest.TestCase):
    def run_endpoint(self, generated, filters=DietaryFilters()):
        sources = [recipe(1, "Dal"), recipe(2, "Soup")]
        with patch.object(main, "semantic_search", return_value=[(s, 0.5) for s in sources]) as search, \
                patch.object(main, "generate_from_craving", side_effect=generated) as generate, \
                patch.object(main, "_store_generated_recipe", return_value="stored") as store:
            result = main.generate_for_craving(CravingRecipeRequest(query="cozy", filters=filters), MagicMock())
        return result, search, generate, store

    def test_generates_from_retrieved_sources_and_stores(self):
        recipe_out = GeneratedRecipe.model_validate_json(json.dumps(VALID))
        result, search, generate, store = self.run_endpoint([recipe_out])
        self.assertEqual(search.call_args.args[2], main.CRAVING_SOURCE_COUNT)
        self.assertEqual([s.name for s in generate.call_args.args[1]], ["Dal", "Soup"])
        store.assert_called_once()
        self.assertEqual(result["recipe"], "stored")
        self.assertEqual(result["inspired_by"], [{"id": 1, "name": "Dal"}, {"id": 2, "name": "Soup"}])

    def test_retries_when_filters_are_ignored(self):
        meaty = GeneratedRecipe.model_validate_json(json.dumps(VALID))  # chicken
        veggie = GeneratedRecipe.model_validate_json(json.dumps(
            {**VALID, "ingredients": [{"name": "tofu"}, {"name": "rice"}]}
        ))
        _, _, generate, store = self.run_endpoint([meaty, veggie], DietaryFilters(vegetarian=True))
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(store.call_args.args[0].ingredients[0].name, "tofu")

    def test_gives_up_with_422_and_stores_nothing(self):
        meaty = GeneratedRecipe.model_validate_json(json.dumps(VALID))
        with self.assertRaises(HTTPException) as caught:
            self.run_endpoint([meaty] * main.CRAVING_ATTEMPTS, DietaryFilters(vegetarian=True))
        self.assertEqual(caught.exception.status_code, 422)

    def test_retries_when_a_source_is_copied(self):
        copy = GeneratedRecipe.model_validate_json(json.dumps(
            {**VALID, "name": "Dal Again", "ingredients": [{"name": "rice"}]}
        ))
        original = GeneratedRecipe.model_validate_json(json.dumps(VALID))
        _, _, generate, store = self.run_endpoint([copy, original])
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(store.call_args.args[0].name, "Chicken Rice")

    def test_generation_failure_returns_502(self):
        with self.assertRaises(HTTPException) as caught:
            self.run_endpoint(RecipeGenerationError("x"))
        self.assertEqual(caught.exception.status_code, 502)


if __name__ == "__main__":
    unittest.main()
