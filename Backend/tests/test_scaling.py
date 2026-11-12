import unittest
from fractions import Fraction
from types import SimpleNamespace

from app.scaling import parse_servings, scale_for_new_servings, scale_quantity


class ScaleQuantityTests(unittest.TestCase):
    def test_kitchen_amounts(self):
        cases = [
            ("2 cups grated carrots", 2, "4 cups grated carrots"),
            ("1 1/2 cups flour", 2, "3 cups flour"),
            ("1/2 teaspoon salt", Fraction(3, 2), "3/4 teaspoon salt"),
            ("1 teaspoon cumin", Fraction(3, 2), "1 1/2 teaspoon cumin"),
            ("2/3 cup sugar", Fraction(1, 2), "1/3 cup sugar"),
            ("1.5 kg rice", 2, "3 kg rice"),
            ("2-3 cloves", 2, "4-6 cloves"),
            ("1 to 2 chillies", 3, "3 to 6 chillies"),
            ("7 g yeast", Fraction(1, 3), "2 1/3 g yeast"),
            ("7 g yeast", Fraction(2, 5), "2.8 g yeast"),  # no close kitchen fraction
            ("4", Fraction(3, 2), "6"),
        ]
        for quantity, factor, expected in cases:
            with self.subTest(quantity=quantity):
                self.assertEqual(scale_quantity(quantity, Fraction(factor)), expected)

    def test_amounts_without_a_number_are_left_alone(self):
        for quantity in ("a pinch", "to taste", ""):
            self.assertEqual(scale_quantity(quantity, Fraction(2)), quantity)
        self.assertIsNone(scale_quantity(None, Fraction(2)))


class ServingsTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_servings("4"), 4)
        self.assertEqual(parse_servings("Serves 6"), 6)
        for unknown in (None, "", "2-4", "a few", "0"):
            self.assertIsNone(parse_servings(unknown))

    def test_scales_only_quantities_copied_from_the_source(self):
        source = SimpleNamespace(servings="3", ingredients=[
            {"quantity": "1 cup", "name": "rice"},
            {"quantity": "2 tbsp", "name": "oil"},
            {"quantity": "1 tsp", "name": "salt"},
        ])
        refined = SimpleNamespace(servings="6", ingredients=[
            SimpleNamespace(quantity="1 cup", name="Rice"),     # copied: scale
            SimpleNamespace(quantity="4 tbsp", name="oil"),     # model scaled it: leave
            SimpleNamespace(quantity="1 tsp", name="chili"),    # new ingredient: leave
            SimpleNamespace(quantity=None, name="salt"),
        ])
        self.assertEqual(scale_for_new_servings(source, refined), 1)
        self.assertEqual([i.quantity for i in refined.ingredients], ["2 cup", "4 tbsp", "1 tsp", None])

    def test_no_scaling_without_a_clear_servings_change(self):
        for old, new in (("4", "4"), ("2-4", "6"), (None, "6"), ("4", None)):
            source = SimpleNamespace(servings=old, ingredients=[{"quantity": "1 cup", "name": "rice"}])
            refined = SimpleNamespace(servings=new, ingredients=[SimpleNamespace(quantity="1 cup", name="rice")])
            with self.subTest(old=old, new=new):
                self.assertEqual(scale_for_new_servings(source, refined), 0)
                self.assertEqual(refined.ingredients[0].quantity, "1 cup")


if __name__ == "__main__":
    unittest.main()
