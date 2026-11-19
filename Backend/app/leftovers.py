"""Leftovers ("half a roast chicken and rice") → the list a new dish is built around, and checks on that dish.

Parsing and checking are code, not the model, so they're testable and the model can't
quietly drop a leftover or hand back the same meal reheated.
"""
import logging
import re
from dataclasses import dataclass

from app.ingredients import ingredient_tokens

logger = logging.getLogger(__name__)


def _tokens(text: str) -> set[str]:
    """ingredient_tokens, plural-safe: it maps "vegetables" to "vegetabl" but "vegetable" to itself."""
    return {token.rstrip("e") or token for token in ingredient_tokens(text)}

MAX_LEFTOVERS = 8
MAX_LEFTOVER_CHARS = 60
# Items to buy beyond the leftovers and pantry staples.
MAX_EXTRA_INGREDIENTS = 4

# Dishes whose names contain "and"; splitting them would invent two leftovers.
_COMPOUND_DISHES = (
    "mac and cheese", "macaroni and cheese", "fish and chips", "salt and pepper", "sweet and sour",
    "bangers and mash", "pork and beans", "chicken and dumplings", "franks and beans", "surf and turf",
)
_AND_PLACEHOLDER = "\x00"
_SEPARATORS = re.compile(r"\s*(?:,|;|\n|\+|&|\band\b|\bplus\b)\s*", re.I)
_LEAD_IN = re.compile(
    r"^(?:(?:i|we)(?:'ve| have)?(?: got| have)?|there(?:'s| is| are)|(?:i |we )?(?:got|have)|"
    r"using|use up|leftovers?:?|left-?over|some|a bit of|a little|the|my|our)\s+",
    re.I,
)
_TAIL = re.compile(
    r"\s+(?:left ?over|leftover|left|from (?:last night|yesterday|dinner|lunch)|in the fridge)\s*$", re.I
)

# Amount and cooked-state words: "half a roast chicken" is chicken, already cooked.
_DESCRIPTOR_WORDS = _tokens(
    "half quarter third whole bit bowl bowls plate container tub portion some couple few lot "
    "pot pan tray batch dish serving servings slice slices handful "
    "piece pieces extra cold day old plain a an and the leftover leftovers left over cooked "
    "roast roasted grilled baked fried steamed boiled mashed pulled braised smoked "
    "rotisserie poached sauteed stir"
)
# Words that don't make a dish new: "Chicken and Rice Bowl" is still the leftovers.
_DISH_FILLER = _tokens(
    "and with bowl plate platter dish style easy quick simple homemade leftover leftovers "
    "warm hot reheated delicious savory tasty"
)
# Assumed to be in the kitchen, so they don't count toward the items to buy.
_PANTRY_TOKENS = _tokens(
    "salt pepper black white kosher sea water ice oil olive vegetable canola sesame neutral "
    "butter ghee garlic clove cloves onion flour sugar brown honey soy sauce vinegar stock broth "
    "cumin paprika smoked chili chilli powder flake red cayenne turmeric curry garam masala "
    "cinnamon oregano dried basil thyme rosemary bay leaf italian seasoning spice mustard seed "
    "ketchup mayonnaise lemon juice baking soda cornstarch"
)

_SAFETY_NOTE = (
    "Leftovers: use cooked food within 3–4 days of cooking it. Reheat the leftovers until "
    "steaming hot all the way through (165°F / 74°C), and only reheat them once."
)


class NoLeftovers(ValueError):
    """Nothing usable in the text."""


@dataclass(frozen=True)
class Leftover:
    text: str  # as the user said it: "half a roast chicken"
    name: str  # the food itself, for matching: "chicken"


def _core_words(text: str) -> list[str]:
    """The food words of an item, in order: "half a roast chicken" → ["chicken"]."""
    words = re.findall(r"[a-z]+", text.lower())
    return [w for w in words if _tokens(w) and not _tokens(w) <= _DESCRIPTOR_WORDS]


def parse_leftovers(text: str) -> list[Leftover]:
    """Split "I have half a roast chicken and rice" into the leftovers it names."""
    lowered = re.sub(r"[ \t]+", " ", str(text or "")).lower()
    for dish in _COMPOUND_DISHES:
        lowered = lowered.replace(dish, dish.replace(" and ", f" {_AND_PLACEHOLDER} "))

    found: dict[str, Leftover] = {}
    for part in _SEPARATORS.split(lowered):
        item = " ".join(part.replace(_AND_PLACEHOLDER, "and").split()).strip(" .!?")
        previous = None
        while item != previous:
            previous = item
            item = _TAIL.sub("", _LEAD_IN.sub("", item)).strip(" .!?")
        core = _core_words(item)
        if not core or len(item) > MAX_LEFTOVER_CHARS:
            continue
        name = " ".join(core)
        found.setdefault(name, Leftover(text=item, name=name))

    if not found:
        raise NoLeftovers("Couldn't find any food in that. Try something like “half a roast chicken and rice”.")
    return list(found.values())[:MAX_LEFTOVERS]


_COOKED_MARKERS = _tokens("leftover cooked")
# "chicken stock" contains "chicken" but isn't the leftover chicken.
_NOT_THE_FOOD = _tokens("stock broth bouillon cube powder seasoning extract")


def _leftover_index(ingredients: list[dict], leftovers: list[Leftover]) -> list[Leftover | None]:
    """For each ingredient, the leftover it is (or None). Each leftover is its single best match."""
    tokens = [_tokens(str(item.get("name", ""))) for item in ingredients]
    matches: list[Leftover | None] = [None] * len(ingredients)
    for leftover in leftovers:
        wanted = _tokens(leftover.name)
        said = _tokens(leftover.text) | _COOKED_MARKERS
        candidates = [
            i for i, t in enumerate(tokens)
            if matches[i] is None and wanted <= t and not t & _NOT_THE_FOOD
        ]
        if candidates:
            best = max(candidates, key=lambda i: (len(tokens[i] & said), -i))
            matches[best] = leftover
    return matches


# Preparation, not food: "medium onion, finely diced" is still a pantry onion.
_PREP_WORDS = _tokens("finely thinly roughly coarsely grated crushed peeled diced sliced cut into pieces")


def extra_ingredients(ingredients: list[dict], leftovers: list[Leftover]) -> list[str]:
    """Ingredients that are neither a leftover nor a pantry staple, named without prep notes."""
    extras = []
    for item, leftover in zip(ingredients, _leftover_index(ingredients, leftovers)):
        name = str(item.get("name", "")).split(",")[0].strip()
        tokens = _tokens(name) - _PREP_WORDS
        if leftover is None and tokens and not tokens <= _PANTRY_TOKENS:
            extras.append(name)
    return extras


def leftover_problems(name: str, ingredients: list[dict], leftovers: list[Leftover]) -> list[str]:
    """Why a generated dish doesn't do the job; empty when it does."""
    problems = []
    used = {l for l in _leftover_index(ingredients, leftovers) if l is not None}
    missing = [l.text for l in leftovers if l not in used]
    if missing:
        problems.append("it must use every leftover as an ingredient, but it leaves out: " + ", ".join(missing))

    # Only the words they said: "Chicken Fried Rice" from roast chicken and rice is a new dish.
    leftover_words: set[str] = set()
    for leftover in leftovers:
        leftover_words |= _tokens(leftover.text)
    if not _tokens(name) - leftover_words - _DISH_FILLER:
        problems.append(f"“{name}” is the same leftovers reheated; make a different dish out of them")

    extras = extra_ingredients(ingredients, leftovers)
    if len(extras) > MAX_EXTRA_INGREDIENTS:
        problems.append(
            f"it needs {len(extras)} ingredients they'd have to buy ({', '.join(extras)}); "
            f"use at most {MAX_EXTRA_INGREDIENTS} besides the leftovers and pantry staples"
        )
    return problems


class DishRejected(Exception):
    """Every attempt broke a check; `problems` are the last attempt's reasons."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


# One retry with the reasons when the dish drops a leftover, just reheats them, or needs too much shopping.
LEFTOVER_ATTEMPTS = 2


def make_leftover_dish(leftovers: list[Leftover], filters, generate) -> tuple:
    """Generate, check, and retry once with the reasons. Returns (recipe, attempts used).

    `generate` is app.ai.generate_from_leftovers (passed in so callers and tests can swap it).
    """
    rejected: list[str] = []
    for attempt in range(1, LEFTOVER_ATTEMPTS + 1):
        recipe = generate(
            [l.text for l in leftovers], filters=filters, rejected=rejected or None, max_extra=MAX_EXTRA_INGREDIENTS
        )
        ingredients = [i.model_dump() for i in recipe.ingredients]
        rejected = leftover_problems(recipe.name, ingredients, leftovers)
        rejected += filters.violations(ingredients, recipe.time, recipe.calories)
        if not rejected:
            return recipe, attempt
        logger.info("Leftover recipe rejected", extra={"attempt": attempt, "problems": rejected})
    raise DishRejected(rejected)


def mark_leftovers(ingredients: list, leftovers: list[Leftover]) -> None:
    """Label leftover ingredients so the list says they're already cooked: "leftover rice"."""
    for item, leftover in zip(ingredients, _leftover_index([i.model_dump() for i in ingredients], leftovers)):
        if leftover is not None and not re.search(r"\b(leftover|cooked)\b", item.name, re.I):
            item.name = f"leftover {item.name}"


def add_safety_note(notes: str | None) -> str:
    return f"{notes.rstrip()}\n\n{_SAFETY_NOTE}" if notes and notes.strip() else _SAFETY_NOTE
