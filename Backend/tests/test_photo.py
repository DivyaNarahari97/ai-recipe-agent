import base64
import json
import os
import unittest
from unittest.mock import patch

# Must be set before app.main loads app.db, so tests can never reach a real database.
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost/unused"

import requests
from fastapi import HTTPException

from app import main
from app.ai import RecipeGenerationError, extract_ingredients_from_photo
from app.photo import MAX_PHOTO_BYTES, InvalidImage, clean_detected, decode_image
from app.schemas import PhotoIngredientsRequest
from tests.test_ai_path import scripted

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


class DecodeImageTests(unittest.TestCase):
    def test_accepts_jpeg_png_and_data_urls(self):
        self.assertEqual(decode_image(b64(JPEG)), b64(JPEG))
        self.assertEqual(decode_image(b64(PNG)), b64(PNG))
        self.assertEqual(decode_image("data:image/jpeg;base64," + b64(JPEG)), b64(JPEG))

    def test_rejects_what_the_model_cant_read(self):
        for bad in ("not base64!!", "", b64(b"GIF89a" + b"\x00" * 10), b64(b"%PDF-1.4")):
            with self.subTest(bad=bad[:12]), self.assertRaises(InvalidImage):
                decode_image(bad)

    def test_rejects_photos_over_the_limit(self):
        with self.assertRaises(InvalidImage) as caught:
            decode_image(b64(JPEG + b"\x00" * MAX_PHOTO_BYTES))
        self.assertIn("too large", str(caught.exception))


class CleanDetectedTests(unittest.TestCase):
    def test_plain_lowercase_names(self):
        self.assertEqual(clean_detected(["  Eggs ", "Cheddar  Cheese.", "green_onions"]),
                         ["eggs", "cheddar cheese", "green onions"])

    def test_names_the_food_not_its_container_or_count(self):
        self.assertEqual(clean_detected(["a jar of pickles", "2 bottles of milk", "a few carrots", "bunch of cilantro"]),
                         ["pickles", "milk", "carrots", "cilantro"])

    def test_drops_containers_categories_and_sentences(self):
        self.assertEqual(clean_detected(["fridge", "Vegetables", "jar", "123", "",
                                         "something that looks like it might be cheese", "butter"]),
                         ["butter"])

    def test_drops_duplicates_that_differ_only_by_plural(self):
        self.assertEqual(clean_detected(["egg", "Eggs", "tomatoes", "tomato", "apples", "apple", "grape", "grapes"]),
                         ["egg", "tomatoes", "apples", "grape"])

    def test_caps_the_list(self):
        self.assertEqual(len(clean_detected([f"item {chr(97 + i)}{chr(97 + j)}" for i in range(6) for j in range(6)])), 25)


class ExtractTests(unittest.TestCase):
    def test_sends_the_photo_and_cleans_the_answer(self):
        model = scripted(json.dumps({"ingredients": ["Eggs", "jar", "a carton of milk"]}))
        self.assertEqual(extract_ingredients_from_photo("IMG", call_model=model), ["eggs", "milk"])
        prompt, image = model.call_args.args
        self.assertEqual(image, "IMG")
        self.assertIn('{"ingredients": [string]}', prompt)

    def test_an_empty_fridge_is_a_valid_answer(self):
        self.assertEqual(extract_ingredients_from_photo("IMG", call_model=scripted('{"ingredients": []}')), [])

    def test_retries_once_on_bad_json_then_gives_up(self):
        model = scripted("I see eggs", '{"ingredients": ["eggs"]}')
        self.assertEqual(extract_ingredients_from_photo("IMG", call_model=model), ["eggs"])
        self.assertEqual(model.call_count, 2)
        with self.assertRaises(RecipeGenerationError):
            extract_ingredients_from_photo("IMG", call_model=scripted("no", "still no"))

    def test_model_outage_is_not_retried(self):
        model = scripted(requests.ConnectionError())
        with self.assertRaises(RecipeGenerationError):
            extract_ingredients_from_photo("IMG", call_model=model)
        self.assertEqual(model.call_count, 1)


class EndpointTests(unittest.TestCase):
    def call(self, image, found=None):
        with patch.object(main, "extract_ingredients_from_photo", side_effect=found or [["eggs"]]) as extract:
            return main.ingredients_from_photo(PhotoIngredientsRequest(image=image)), extract

    def test_returns_what_the_model_found(self):
        result, extract = self.call("data:image/png;base64," + b64(PNG))
        self.assertEqual(result, {"ingredients": ["eggs"]})
        self.assertEqual(extract.call_args.args[0], b64(PNG))

    def test_bad_upload_is_400_without_calling_the_model(self):
        with self.assertRaises(HTTPException) as caught:
            self.call(b64(b"GIF89a"), found=AssertionError("model called"))
        self.assertEqual(caught.exception.status_code, 400)

    def test_model_failure_is_502(self):
        with self.assertRaises(HTTPException) as caught:
            self.call(b64(JPEG), found=RecipeGenerationError("down"))
        self.assertEqual(caught.exception.status_code, 502)


if __name__ == "__main__":
    unittest.main()
