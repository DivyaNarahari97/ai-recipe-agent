import assert from "node:assert/strict";
import test from "node:test";
import {
  TRAITS,
  addAvoid,
  buildProfile,
  foodName,
  isSpicy,
  profileRequest,
  profileSummary,
  rateRecipe,
  ratingFor,
  removeTrait,
} from "./taste.js";

const recipe = (id, cuisine, ...ingredients) => ({
  id,
  name: `Recipe ${id}`,
  cuisine,
  ingredients: ingredients.map((name) => ({ quantity: "1", name })),
});
const NO_EDITS = { dismissed: [], avoids: [] };
const likeTexts = (profile) => profile.likes.map((l) => l.text);

test("foodName keeps the food and drops prep and garnish words", () => {
  assert.equal(foodName("Fresh cilantro, chopped (for garnish)"), "cilantro");
  assert.equal(foodName("2 large Portobello Mushrooms"), "portobello mushrooms");
  assert.equal(foodName("bay leaves"), "bay leaves");
  assert.equal(foodName("bunch cilantro"), "cilantro");
  assert.equal(foodName("cup mint leaves"), "mint leaves");
  assert.equal(foodName("handful of fresh basil"), "basil");
});

test("isSpicy spots chili ingredients", () => {
  assert.equal(isSpicy(recipe(1, null, "rice", "red pepper flakes")), true);
  assert.equal(isSpicy(recipe(1, null, "jalapeños, sliced")), true);
  assert.equal(isSpicy(recipe(1, null, "bell pepper", "rice")), false);
});

test("one explicit reason makes a trait; liked dishes alone need two", () => {
  let ratings = rateRecipe({}, recipe(1, "Thai", "chili", "rice"), "up", ["spice"]);
  assert.deepEqual(likeTexts(buildProfile(ratings)), [TRAITS.spicy]);

  ratings = rateRecipe({}, recipe(1, "Thai", "chili", "rice"), "up");
  assert.deepEqual(likeTexts(buildProfile(ratings)), []);
  ratings = rateRecipe(ratings, recipe(2, "Thai", "sriracha", "noodles"), "up");
  assert.deepEqual(likeTexts(buildProfile(ratings)), [TRAITS.spicy, "Thai food"]);
});

test("too spicy outweighs liked spicy dishes and turns into mild", () => {
  let ratings = rateRecipe({}, recipe(1, null, "chili"), "up");
  ratings = rateRecipe(ratings, recipe(2, null, "cayenne"), "down", ["too_spicy"]);
  assert.deepEqual(likeTexts(buildProfile(ratings)), []);
  ratings = rateRecipe(ratings, recipe(3, null, "chipotle"), "down", ["too_spicy"]);
  assert.deepEqual(likeTexts(buildProfile(ratings)), [TRAITS.mild]);
});

test("a disliked dish cancels a liked one of the same cuisine", () => {
  let ratings = rateRecipe({}, recipe(1, "Indian", "dal"), "up");
  ratings = rateRecipe(ratings, recipe(2, "Indian", "paneer"), "up");
  ratings = rateRecipe(ratings, recipe(3, "Indian", "okra"), "down");
  assert.deepEqual(likeTexts(buildProfile(ratings)), []);
});

test("avoids come only from foods picked on a thumbs down", () => {
  let ratings = rateRecipe({}, recipe(1, null, "rice", "fresh cilantro, chopped"), "down", ["ingredient"], [
    "fresh cilantro, chopped",
  ]);
  ratings = rateRecipe(ratings, recipe(2, null, "mushrooms", "rice"), "down", ["bland"]);
  const profile = buildProfile(ratings);
  assert.deepEqual(profile.avoids, [{ text: "cilantro", why: "from 1 rating" }]);
  assert.deepEqual(likeTexts(profile), [TRAITS.bold]);
  assert.deepEqual(profileRequest(profile), { likes: [TRAITS.bold], avoids: ["cilantro"] });
  assert.equal(profileSummary(profile), "likes bold flavors · avoids cilantro");
});

test("changing or clearing a rating replaces it", () => {
  const r = recipe(1, null, "chili");
  let ratings = rateRecipe({}, r, "up", ["spice"]);
  ratings = rateRecipe(ratings, r, "down", ["too_spicy", "spice"]);
  assert.deepEqual(ratingFor(ratings, r).reasons, ["too_spicy"]);
  assert.equal(ratingFor(rateRecipe(ratings, r, null), r), null);
});

test("removed traits stay removed and added avoids show up", () => {
  const ratings = rateRecipe({}, recipe(1, null, "chili", "cilantro"), "down", ["too_spicy", "ingredient"], ["cilantro"]);
  let edits = removeTrait(NO_EDITS, { text: "cilantro" });
  edits = addAvoid(edits, "Olives, sliced");
  const profile = buildProfile(ratings, edits);
  assert.deepEqual(profile.avoids, [{ text: "olives", why: "added by you", manual: true }]);

  // Adding a removed food back undoes the removal.
  assert.deepEqual(
    buildProfile(ratings, addAvoid(edits, "cilantro")).avoids.map((a) => a.text),
    ["cilantro", "olives"]
  );
  assert.deepEqual(buildProfile(ratings, removeTrait(edits, profile.avoids[0])).avoids, []);
});
