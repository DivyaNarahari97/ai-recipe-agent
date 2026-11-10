import unittest
from types import SimpleNamespace

from app.ingredients import near_copy_of


def source(name, *ingredients):
    return SimpleNamespace(name=name, ingredients=[{"name": i} for i in ingredients])


class NearCopyTests(unittest.TestCase):
    SOURCES = [source("Corn Kichadi", "corn", "rice", "turmeric", "ghee"), source("Dal", "lentils")]

    def test_same_name_is_a_copy(self):
        self.assertEqual(near_copy_of(" corn  KICHADI", [{"name": "kale"}], self.SOURCES), "Corn Kichadi")

    def test_mostly_same_ingredients_is_a_copy(self):
        ingredients = [{"name": n} for n in ("frozen corn", "basmati rice", "turmeric powder", "ghee")]
        # {corn, frozen, rice, basmati, turmeric, powder, ghee} vs 4 source words: 4/7 < 0.7
        self.assertIsNone(near_copy_of("New", ingredients, self.SOURCES))
        close = [{"name": n} for n in ("corn", "rice", "turmeric", "ghee", "salt")]
        self.assertEqual(near_copy_of("New", close, self.SOURCES), "Corn Kichadi")  # 4/5

    def test_borrowing_some_ingredients_is_fine(self):
        ingredients = [{"name": n} for n in ("corn", "rice", "chili", "lime", "cilantro")]
        self.assertIsNone(near_copy_of("Corn Rice Bowl", ingredients, self.SOURCES))


if __name__ == "__main__":
    unittest.main()
