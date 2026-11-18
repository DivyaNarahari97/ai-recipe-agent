// Scales ingredient quantities ("1 1/2 cups", "1-2 tsp", "2 eggs") to a new serving count
// and converts them between measuring systems. Number rules match Backend/app/scaling.py.

export const UNIT_SYSTEMS = [
  { id: "original", label: "As written" },
  { id: "metric", label: "Metric" },
  { id: "us", label: "US" },
];

const UNICODE_FRACTIONS = { "½": "1/2", "⅓": "1/3", "⅔": "2/3", "¼": "1/4", "¾": "3/4", "⅛": "1/8" };
const NUMBER = String.raw`\d+\s+\d+\/\d+|\d+\/\d+|\d+(?:\.\d+)?`;
const AMOUNT = new RegExp(String.raw`^\s*(${NUMBER})(?:\s*(-|–|to)\s*(${NUMBER}))?`, "i");

// size: millilitres (volume) or grams (weight) in one unit.
const UNITS = {
  tsp: { kind: "volume", size: 4.92892, aliases: ["teaspoons", "teaspoon", "tsps", "tsp"] },
  tbsp: { kind: "volume", size: 14.7868, aliases: ["tablespoons", "tablespoon", "tbsps", "tbsp", "tbs", "tbl"] },
  "fl oz": { kind: "volume", size: 29.5735, aliases: ["fluid ounces", "fluid ounce", "fl. oz", "fl oz"] },
  cup: { kind: "volume", size: 236.588, aliases: ["cups", "cup"], plural: "cups" },
  pint: { kind: "volume", size: 473.176, aliases: ["pints", "pint", "pt"], plural: "pints" },
  quart: { kind: "volume", size: 946.353, aliases: ["quarts", "quart", "qt"], plural: "quarts" },
  ml: { kind: "volume", size: 1, aliases: ["millilitres", "millilitre", "milliliters", "milliliter", "ml"] },
  l: { kind: "volume", size: 1000, aliases: ["litres", "litre", "liters", "liter", "l"], label: "L" },
  g: { kind: "weight", size: 1, aliases: ["grams", "gram", "gr", "g"] },
  kg: { kind: "weight", size: 1000, aliases: ["kilograms", "kilogram", "kgs", "kg"] },
  oz: { kind: "weight", size: 28.3495, aliases: ["ounces", "ounce", "oz"] },
  lb: { kind: "weight", size: 453.592, aliases: ["pounds", "pound", "lbs", "lb"] },
};
const ALIAS_TO_UNIT = Object.fromEntries(
  Object.entries(UNITS).flatMap(([id, unit]) => unit.aliases.map((alias) => [alias, id]))
);
const UNIT_PATTERN = new RegExp(
  String.raw`^\s*(${Object.keys(ALIAS_TO_UNIT)
    .sort((a, b) => b.length - a.length)
    .map((alias) => alias.replace(/[.\s]/g, (c) => (c === "." ? "\\." : "\\s*")))
    .join("|")})\.?(?=[\s,;()]|$)`,
  "i"
);

// Words after a bare count that should agree with it: "1 clove" / "3 cloves".
const COUNT_NOUNS = {
  clove: "cloves", sprig: "sprigs", bunch: "bunches", bundle: "bundles", can: "cans",
  slice: "slices", piece: "pieces", ear: "ears", stalk: "stalks", egg: "eggs",
  inch: "inches", head: "heads", pinch: "pinches", scallion: "scallions",
};
const COUNT_SINGULAR = Object.fromEntries(Object.entries(COUNT_NOUNS).map(([one, many]) => [many, one]));

// Grams per millilitre, so grams ↔ cups works for common ingredients. First match wins.
// Liquids stay in millilitres in metric; everything else is weighed.
const DENSITIES = [
  { pattern: /\b(water|milk|broth|stock|juice|vinegar|wine|cream|sauce)\b/, gPerMl: 1.0, liquid: true },
  { pattern: /\boil\b/, gPerMl: 0.92, liquid: true },
  { pattern: /\b(honey|syrup|molasses)\b/, gPerMl: 1.42, liquid: true },
  { pattern: /\bbrown sugar\b/, gPerMl: 0.93 },
  { pattern: /\b(powdered|icing|confectioners'?) sugar\b/, gPerMl: 0.51 },
  { pattern: /\bsugar\b/, gPerMl: 0.85 },
  { pattern: /\b(almond flour|almond meal)\b/, gPerMl: 0.41 },
  { pattern: /\brice flour\b/, gPerMl: 0.67 },
  { pattern: /\b(flour|maida|atta)\b/, gPerMl: 0.53 },
  { pattern: /\b(cornstarch|corn starch|cornflour)\b/, gPerMl: 0.54 },
  { pattern: /\b(butter|ghee)\b/, gPerMl: 0.96 },
  { pattern: /\bcocoa\b/, gPerMl: 0.36 },
  { pattern: /\boats?\b/, gPerMl: 0.38 },
  { pattern: /\b(rice|basmati)\b/, gPerMl: 0.78 },
  { pattern: /\b(lentils?|dal)\b/, gPerMl: 0.82 },
  { pattern: /\b(yogh?urt|curd)\b/, gPerMl: 1.03 },
  { pattern: /\b(cheese|parmesan|cheddar|mozzarella)\b/, gPerMl: 0.42 },
  { pattern: /\b(nuts|almonds|walnuts|cashews|peanuts|pecans)\b/, gPerMl: 0.6 },
];

const COOKING_DENOMINATORS = [2, 3, 4, 8];
const COUNT_DENOMINATORS = [2, 3, 4];
const CUP_DENOMINATORS = [2, 3, 4];
// What measuring sets hold: no "3 1/4 tbsp" or "6 5/8 lb".
const UNIT_DENOMINATORS = {
  tsp: [2, 4, 8], tbsp: [2], cup: CUP_DENOMINATORS, quart: [2, 4], oz: [2, 4], lb: [2, 4],
};

function parseNumber(text) {
  return text
    .trim()
    .split(/\s+/)
    .reduce((sum, part) => {
      const [top, bottom] = part.split("/");
      return sum + (bottom ? Number(top) / Number(bottom) : Number(top));
    }, 0);
}

// Nearest kitchen-friendly value: halves, thirds, quarters (and eighths for measures).
function snap(value, denominators) {
  if (value >= 20) return Math.round(value);
  if (value >= 10) return Math.round(value * 2) / 2;
  let best = Math.round(value);
  for (const d of denominators) {
    const candidate = Math.round(value * d) / d;
    if (Math.abs(candidate - value) < Math.abs(best - value) - 1e-9) best = candidate;
  }
  return best > 0 ? best : 1 / denominators[denominators.length - 1];
}

function formatFraction(value, denominators) {
  const snapped = snap(value, denominators);
  const whole = Math.floor(snapped + 1e-9);
  const rest = snapped - whole;
  if (rest < 1e-9) return String(whole);
  const d = denominators.find((den) => Math.abs(Math.round(rest * den) - rest * den) < 1e-6);
  const fraction = `${Math.round(rest * d)}/${d}`;
  return whole ? `${whole} ${fraction}` : fraction;
}

// Grams and millilitres: precise enough to measure, without false precision.
function formatMetric(value) {
  if (value < 20) return String(Math.max(1, Math.round(value)));
  if (value < 250) return String(Math.round(value / 5) * 5);
  return String(Math.round(value / 10) * 10);
}

function formatAmount(value, unitId) {
  if (unitId === "g" || unitId === "ml") return formatMetric(value);
  if (unitId === "kg" || unitId === "l") return String(Number(value.toFixed(2)));
  return formatFraction(value, UNIT_DENOMINATORS[unitId] || COOKING_DENOMINATORS);
}

function unitName(unitId, amount) {
  const { plural, label = unitId } = UNITS[unitId];
  return plural && amount > 1 ? plural : label;
}

function densityOf(name) {
  const text = String(name || "").toLowerCase();
  return DENSITIES.find((entry) => entry.pattern.test(text)) || null;
}

// Best unit for an amount in base units (ml or g).
// Under a cup, use cups only when a ¼ / ⅓ / ½ / ⅔ / ¾ cup measures it: 6 tbsp, not "3/8 cup".
function pickUsVolume(ml) {
  if (ml < UNITS.tbsp.size * 0.99) return "tsp";
  const cups = ml / UNITS.cup.size;
  if (cups >= 16) return "quart";
  if (cups >= 0.98) return "cup";
  const fitsCup = cups >= 0.24 && Math.abs(snap(cups, CUP_DENOMINATORS) - cups) <= 0.021;
  return fitsCup ? "cup" : "tbsp";
}
const pickMetricVolume = (ml) => (ml < 1000 ? "ml" : "l");
const pickUsWeight = (g) => (g < UNITS.lb.size * 0.99 ? "oz" : "lb");
const pickMetricWeight = (g) => (g < 1000 ? "g" : "kg");

/** The unit to show, and the base amount in that unit's kind (it may switch volume ↔ weight). */
function chooseTarget(unitId, base, system, density) {
  const { kind } = UNITS[unitId];
  const spoon = unitId === "tsp" || unitId === "tbsp";

  if (system === "metric") {
    if (kind === "weight") return { unitId: pickMetricWeight(base), base };
    // Spoons are metric too; small amounts stay as spoons.
    if (base < UNITS.cup.size / 4 - 1 && (spoon || unitId === "cup")) return { unitId: pickUsVolume(base), base };
    if (density && !density.liquid) {
      const grams = base * density.gPerMl;
      return { unitId: pickMetricWeight(grams), base: grams };
    }
    return { unitId: pickMetricVolume(base), base };
  }

  if (system === "us") {
    if (kind === "volume") return { unitId: pickUsVolume(base), base };
    // Grams of a known ingredient become cups; ounces and pounds are already US.
    if (density && (unitId === "g" || unitId === "kg")) {
      const ml = base / density.gPerMl;
      return { unitId: pickUsVolume(ml), base: ml };
    }
    return { unitId: pickUsWeight(base), base };
  }

  // As written: same system, but tidy up after scaling (6 tsp → 2 tbsp, 1200 g → 1.2 kg).
  if (spoon || unitId === "cup" || unitId === "quart") return { unitId: pickUsVolume(base), base };
  if (unitId === "ml" || unitId === "l") return { unitId: pickMetricVolume(base), base };
  if (unitId === "g" || unitId === "kg") return { unitId: pickMetricWeight(base), base };
  if (unitId === "oz" || unitId === "lb") return { unitId: pickUsWeight(base), base };
  return { unitId, base };
}

function parseQuantity(text) {
  const normalized = text.replace(/[½⅓⅔¼¾⅛]/g, (c) => ` ${UNICODE_FRACTIONS[c]}`);
  const amount = normalized.match(AMOUNT);
  if (!amount) return null;
  const [whole, low, separator, high] = amount;
  const afterAmount = normalized.slice(whole.length);
  const unit = afterAmount.match(UNIT_PATTERN);
  return {
    low: parseNumber(low),
    high: high ? parseNumber(high) : null,
    separator: separator === "to" ? " to " : "–",
    unitId: unit ? ALIAS_TO_UNIT[unit[1].toLowerCase().replace(/\s+/g, " ")] : null,
    rest: unit ? afterAmount.slice(unit[0].length) : afterAmount,
  };
}

// "1 clove" → "3 cloves", "2 eggs" → "1 egg".
function agreeNoun(rest, amount) {
  return rest.replace(/^(\s*)([a-z]+)\b/i, (match, space, word) => {
    const lower = word.toLowerCase();
    if (amount > 1 && COUNT_NOUNS[lower]) return space + COUNT_NOUNS[lower];
    if (amount <= 1 && COUNT_SINGULAR[lower]) return space + COUNT_SINGULAR[lower];
    return match;
  });
}

const UNIT_SYSTEM_KEY = "recipe-assistant:units";

export function loadUnitSystem() {
  try {
    const saved = window.localStorage.getItem(UNIT_SYSTEM_KEY);
    return UNIT_SYSTEMS.some((s) => s.id === saved) ? saved : "original";
  } catch {
    return "original";
  }
}

export function saveUnitSystem(system) {
  try {
    window.localStorage.setItem(UNIT_SYSTEM_KEY, system);
  } catch {
    // Private mode or blocked storage: the choice just isn't remembered.
  }
}

/**
 * How a recipe is being shown: its own servings (`base`), the chosen `servings`, and
 * `quantity(item)` for an ingredient's amount at that size in the chosen unit system.
 * Without a usable servings count, amounts are converted but not scaled.
 */
export function recipeScale(recipe, chosenServings, system = "original") {
  const base = parseServings(recipe?.servings);
  const servings = base && chosenServings > 0 ? chosenServings : base;
  const factor = base ? servings / base : 1;
  return {
    base,
    servings,
    factor,
    system,
    quantity: (item) => scaleQuantity(item?.quantity, { factor, system, name: item?.name }),
  };
}

/** "2-3", "4 servings", "Serves 6" → the (lowest) number; nothing usable → null. */
export function parseServings(value) {
  const match = String(value ?? "").match(/\d+/);
  const servings = match ? Number(match[0]) : 0;
  return servings > 0 ? servings : null;
}

/**
 * A quantity for `factor` times the servings, in `system` ("original" | "metric" | "us").
 * `name` is the ingredient, used for grams ↔ cups. Quantities without a leading
 * number ("salt to taste", "pinch") come back unchanged.
 */
export function scaleQuantity(quantity, { factor = 1, system = "original", name = "" } = {}) {
  if (quantity == null) return quantity;
  const text = String(quantity);
  if (factor === 1 && system === "original") return text;
  const parsed = parseQuantity(text);
  if (!parsed) return text;

  const low = parsed.low * factor;
  const high = parsed.high == null ? null : parsed.high * factor;

  if (!parsed.unitId) {
    const amount = formatFraction(low, COUNT_DENOMINATORS);
    const range = high == null ? "" : parsed.separator + formatFraction(high, COUNT_DENOMINATORS);
    return amount + range + agreeNoun(parsed.rest, high ?? low);
  }

  const size = UNITS[parsed.unitId].size;
  const density = densityOf(name) || densityOf(parsed.rest);
  const target = chooseTarget(parsed.unitId, low * size, system, density);
  const perBase = target.base / (low * size); // ml → g (or back) when the kind changed
  const toTarget = (amount) => (amount * size * perBase) / UNITS[target.unitId].size;

  const lowText = formatAmount(toTarget(low), target.unitId);
  const highText = high == null ? "" : parsed.separator + formatAmount(toTarget(high), target.unitId);
  return `${lowText}${highText} ${unitName(target.unitId, toTarget(high ?? low))}${parsed.rest}`;
}
