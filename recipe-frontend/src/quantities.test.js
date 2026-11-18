import { test } from "node:test";
import assert from "node:assert/strict";
import { parseServings, scaleQuantity } from "./quantities.js";

const scale = (quantity, factor, system = "original", name = "") =>
  scaleQuantity(quantity, { factor, system, name });

test("parseServings takes the first number", () => {
  assert.equal(parseServings("4"), 4);
  assert.equal(parseServings("2-3"), 2);
  assert.equal(parseServings("Serves 6"), 6);
  assert.equal(parseServings(4), 4);
  assert.equal(parseServings(""), null);
  assert.equal(parseServings(null), null);
  assert.equal(parseServings("0"), null);
});

test("unchanged when nothing to do", () => {
  assert.equal(scale("16 oz", 1), "16 oz");
  assert.equal(scale("Salt to taste", 3), "Salt to taste");
  assert.equal(scale("pinch", 2, "metric"), "pinch");
  assert.equal(scale(null, 2), null);
});

test("scales amounts with kitchen fractions", () => {
  assert.equal(scale("1 1/2 cups", 2), "3 cups");
  assert.equal(scale("1/2 cup", 3), "1 1/2 cups");
  assert.equal(scale("½ cup", 2), "1 cup");
  assert.equal(scale("1 cup heavy cream (optional)", 0.5), "1/2 cup heavy cream (optional)");
  assert.equal(scale("1/4 tsp", 0.25), "1/8 tsp");
});

test("ranges scale both ends", () => {
  assert.equal(scale("1-2 tsp", 2), "2–4 tsp");
  assert.equal(scale("1-2 tsp", 3), "1–2 tbsp");
});

test("counts keep their noun in agreement", () => {
  assert.equal(scale("2 eggs", 0.5), "1 egg");
  assert.equal(scale("3 cloves garlic, minced", 1 / 3), "1 clove garlic, minced");
  assert.equal(scale("1 sprig", 2), "2 sprigs");
  assert.equal(scale("1 inch", 2), "2 inches");
  assert.equal(scale("1 large", 1.5), "1 1/2 large");
  assert.equal(scale("2 green onions, chopped", 3), "6 green onions, chopped");
  assert.equal(scale("4", 0.5), "2");
});

test("tidies units after scaling", () => {
  assert.equal(scale("1 tsp", 6), "2 tbsp");
  assert.equal(scale("2 tbsp", 2), "1/4 cup");
  assert.equal(scale("1 kg", 1.5), "1.5 kg");
  assert.equal(scale("100 g", 2), "200 g");
  assert.equal(scale("16 oz", 2), "2 lb");
  assert.equal(scale("1 cup", 0.25), "1/4 cup");
  assert.equal(scale("1 cup", 0.2), "3 tbsp");
  assert.equal(scale("2 tbsp", 3), "6 tbsp"); // not "3/8 cup"
  assert.equal(scale("4 tbsp", 3), "3/4 cup");
  assert.equal(scale("8 cups", 3), "6 quarts");
});

test("metric: weighs dry goods, measures liquids in ml, keeps small spoons", () => {
  assert.equal(scale("1 cup", 1, "metric", "all-purpose flour"), "125 g");
  assert.equal(scale("2 cups", 1, "metric", "basmati rice"), "370 g");
  assert.equal(scale("1 cup", 1, "metric", "milk"), "235 ml");
  assert.equal(scale("1 cup heavy cream (optional)", 1, "metric", "heavy cream"), "235 ml heavy cream (optional)");
  assert.equal(scale("1 cup", 1, "metric", "spinach"), "235 ml");
  assert.equal(scale("1 tbsp", 1, "metric", "butter"), "1 tbsp");
  assert.equal(scale("1 lb", 1, "metric", "chicken"), "450 g");
  assert.equal(scale("2 litres", 1, "metric", "water"), "2 L");
  assert.equal(scale("1/2 cup", 1, "metric", "sugar"), "100 g");
});

test("us: grams to cups when the ingredient is known, otherwise ounces", () => {
  assert.equal(scale("200 g", 1, "us", "sugar"), "1 cup");
  assert.equal(scale("125 g", 2, "us", "flour"), "2 cups");
  assert.equal(scale("100 g", 1, "us", "paneer"), "3 1/2 oz");
  assert.equal(scale("1 kg", 1, "us", "chicken thighs"), "2 1/4 lb");
  assert.equal(scale("500 ml", 1, "us", "water"), "2 cups");
  assert.equal(scale("1 kg", 3, "us", "carrots"), "6 1/2 lb");
  assert.equal(scale("8 oz", 3, "us", "mozzarella cheese"), "1 1/2 lb"); // stays a weight
  assert.equal(scale("2 litres", 3, "us", "whole milk"), "6 1/4 quarts");
  assert.equal(scale("15 ml", 1, "us", "oil"), "1 tbsp");
});

test("unit words inside other words are not units", () => {
  assert.equal(scale("1 large", 2, "metric"), "2 large");
  assert.equal(scale("2 green onions", 1, "us"), "2 green onions");
});
