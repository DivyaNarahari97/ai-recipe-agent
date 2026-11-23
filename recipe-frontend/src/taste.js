// Thumbs up/down on recipes → a taste profile ("likes spicy food", "avoids cilantro")
// that is sent with every generation request. Stored in this browser, like favorites.
const RATINGS_KEY = "recipe-assistant:ratings";
const EDITS_KEY = "recipe-assistant:taste-edits";

export const REASONS = {
  up: [
    { id: "spice", label: "Loved the spice" },
    { id: "bold", label: "Big flavor" },
    { id: "quick", label: "Quick to make" },
  ],
  down: [
    { id: "too_spicy", label: "Too spicy" },
    { id: "bland", label: "Too bland" },
    { id: "slow", label: "Took too long" },
    { id: "ingredient", label: "Didn't like an ingredient" },
  ],
};

// What the model is told, and the short form the app shows ("likes spicy · avoids cilantro").
export const TRAITS = {
  spicy: "spicy food",
  mild: "mild food with little or no chili heat",
  bold: "bold, well-seasoned flavors",
  quick: "quick recipes, about 30 minutes or less",
};
const SHORT = {
  [TRAITS.spicy]: "spicy",
  [TRAITS.mild]: "mild",
  [TRAITS.bold]: "bold flavors",
  [TRAITS.quick]: "quick recipes",
};

// Same limits as the backend (app/taste.py).
const MAX_LIKES = 12;
const MAX_AVOIDS = 20;

const HOT = /\b(chil(?:i|e|li)e?s?|jalape(?:n|ñ)os?|cayenne|sriracha|gochujang|gochugaru|harissa|habaneros?|serranos?|chipotles?|red pepper flakes|hot sauce|sambal|curry paste|bird'?s eye|scotch bonnet|piri.?piri|peri.?peri)\b/i;

export const isSpicy = (recipe) => (recipe?.ingredients || []).some((item) => HOT.test(String(item?.name || "")));

// "Fresh cilantro, chopped (for garnish)" → "cilantro": the food, for "avoids …".
export function foodName(name) {
  return String(name || "")
    .toLowerCase()
    .split(",")[0]
    .replace(/\(.*?\)/g, " ")
    .replace(/\b(fresh|freshly|chopped|minced|diced|sliced|finely|roughly|thinly|large|small|medium|optional|whole|for garnish|to garnish|to taste|to serve|for serving)\b/g, " ")
    .replace(/[^a-z' -]/g, " ")
    .split(/\s+/)
    .filter(Boolean)
    .join(" ")
    .replace(UNITS, "")
    .trim();
}

// Some stored names start with the amount: "bunch cilantro", "cup mint leaves", "handful of basil".
const UNITS = /^(?:(?:cups?|tbsps?|tsps?|tablespoons?|teaspoons?|bunch(?:es)?|handfuls?|pinch(?:es)?|sprigs?|dash(?:es)?|g|kg|ml|l|oz|ounces?|lbs?|pounds?|cans?|packages?|packets?|jars?|stalks?|heads?|of)\s+)+/;

function read(key, fallback) {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(key) ?? "null");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : fallback;
  } catch {
    return fallback;
  }
}

function write(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage blocked (private mode, quota): the profile still works for this visit.
  }
}

const NO_EDITS = { dismissed: [], avoids: [] };

export const loadRatings = () => read(RATINGS_KEY, {});
export const loadTasteEdits = () => ({ ...NO_EDITS, ...read(EDITS_KEY, NO_EDITS) });
export const saveRatings = (ratings) => write(RATINGS_KEY, ratings);
export const saveTasteEdits = (edits) => write(EDITS_KEY, edits);

// A rating keeps what the profile needs from the recipe, so it survives the recipe being refined away.
export function rateRecipe(ratings, recipe, rating, reasons = [], avoid = []) {
  const key = String(recipe.id ?? recipe.name);
  const next = { ...ratings };
  if (!rating) {
    delete next[key];
    return next;
  }
  next[key] = {
    rating,
    reasons: reasons.filter((r) => REASONS[rating].some((option) => option.id === r)),
    avoid: rating === "down" ? avoid.map(foodName).filter(Boolean) : [],
    recipe: { id: recipe.id ?? null, name: recipe.name, cuisine: recipe.cuisine || null, spicy: isSpicy(recipe) },
    at: new Date().toISOString(),
  };
  return next;
}

export const ratingFor = (ratings, recipe) => (recipe ? ratings[String(recipe.id ?? recipe.name)] || null : null);

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

/**
 * The profile the ratings add up to. One explicit reason is enough for a trait; without
 * reasons it takes two liked recipes of the same kind (two spicy dishes, two Thai dishes).
 * Avoids only ever come from foods the cook picked, never from guesses.
 */
export function buildProfile(ratings, edits = NO_EDITS) {
  const all = Object.values(ratings || {});
  const has = (r, reason) => r.reasons?.includes(reason);
  const count = (test) => all.filter(test).length;

  const likes = [];
  const add = (text, score, sources) => {
    if (score >= 2) likes.push({ text, short: SHORT[text] || text, why: `from ${plural(sources, "rating")}` });
  };

  const lovedSpice = count((r) => r.rating === "up" && has(r, "spice"));
  const likedSpicy = count((r) => r.rating === "up" && r.recipe?.spicy && !has(r, "spice"));
  const tooSpicy = count((r) => r.rating === "down" && has(r, "too_spicy"));
  const spice = 2 * lovedSpice + likedSpicy - 2 * tooSpicy;
  if (spice >= 2) add(TRAITS.spicy, spice, lovedSpice + likedSpicy);
  else if (spice <= -2) add(TRAITS.mild, -spice, tooSpicy);

  const bold = count((r) => (r.rating === "up" && has(r, "bold")) || (r.rating === "down" && has(r, "bland")));
  add(TRAITS.bold, 2 * bold, bold);
  const quick = count((r) => (r.rating === "up" && has(r, "quick")) || (r.rating === "down" && has(r, "slow")));
  add(TRAITS.quick, 2 * quick, quick);

  const cuisines = {};
  for (const r of all) {
    const cuisine = r.recipe?.cuisine;
    if (!cuisine || cuisine === "Other") continue;
    cuisines[cuisine] ??= { score: 0, ups: 0 };
    cuisines[cuisine].score += r.rating === "up" ? 1 : -1;
    if (r.rating === "up") cuisines[cuisine].ups += 1;
  }
  Object.entries(cuisines)
    .sort((a, b) => b[1].score - a[1].score || a[0].localeCompare(b[0]))
    .forEach(([cuisine, { score, ups }]) => add(`${cuisine} food`, score, ups));

  const avoidCounts = new Map();
  for (const r of all) {
    if (r.rating !== "down") continue;
    for (const food of r.avoid || []) avoidCounts.set(food, (avoidCounts.get(food) || 0) + 1);
  }
  const avoids = [...avoidCounts].map(([text, n]) => ({ text, why: `from ${plural(n, "rating")}` }));
  for (const text of edits.avoids || []) {
    if (!avoids.some((a) => a.text === text)) avoids.push({ text, why: "added by you", manual: true });
  }

  const dismissed = new Set(edits.dismissed || []);
  return {
    likes: likes.filter((l) => !dismissed.has(l.text)).slice(0, MAX_LIKES),
    avoids: avoids.filter((a) => a.manual || !dismissed.has(a.text)).slice(0, MAX_AVOIDS),
    rated: all.length,
  };
}

// What the backend gets (app/taste.py TasteProfile).
export const profileRequest = (profile) => ({
  likes: profile.likes.map((l) => l.text),
  avoids: profile.avoids.map((a) => a.text),
});

export function removeTrait(edits, trait) {
  return {
    dismissed: trait.manual ? edits.dismissed : [...new Set([...edits.dismissed, trait.text])],
    avoids: edits.avoids.filter((a) => a !== trait.text),
  };
}

export function addAvoid(edits, name) {
  const food = foodName(name);
  if (!food) return edits;
  return {
    dismissed: edits.dismissed.filter((d) => d !== food),
    avoids: [...new Set([...edits.avoids, food])],
  };
}

export function profileSummary(profile) {
  const parts = [];
  if (profile.likes.length) parts.push(`likes ${profile.likes.map((l) => l.short).join(", ")}`);
  if (profile.avoids.length) parts.push(`avoids ${profile.avoids.map((a) => a.text).join(", ")}`);
  return parts.join(" · ");
}
