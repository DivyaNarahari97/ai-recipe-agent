"""'Use it up first': rank stored recipes by how much of the soon-to-expire pantry they use.

Pure code over the stored recipes, no model call, so it's instant and repeatable.
"""
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

from app.ingredients import ingredient_tokens
from app.shopping import build_shopping_list

# Days left → how urgently to use it. Further out (or no date) still counts as owned.
URGENCY_BY_DAYS = ((1, 3), (3, 2), (7, 1))  # today/tomorrow: 3, within 3 days: 2, within a week: 1

# "chicken stock" contains "chicken" but doesn't use up the chicken in your fridge.
_NOT_THE_FOOD = ingredient_tokens("stock broth bouillon cube powder seasoning extract")


@dataclass(frozen=True)
class PantryItem:
    name: str
    days_left: Optional[int]  # None: no expiry date

    @property
    def urgency(self) -> int:
        if self.days_left is None:
            return 0
        return next((score for limit, score in URGENCY_BY_DAYS if self.days_left <= limit), 0)


def pantry_items(items: list, today: date) -> tuple[list[PantryItem], list[str]]:
    """Usable items with days left, plus the names of expired ones (never suggested to cook)."""
    usable, expired = [], []
    seen = set()
    for item in items:
        name = " ".join(str(item.name).split()).lower()
        if not name or not ingredient_tokens(name) or name in seen:
            continue
        seen.add(name)
        days = (item.expires - today).days if item.expires else None
        if days is not None and days < 0:
            expired.append(name)
        else:
            usable.append(PantryItem(name, days))
    return usable, expired


_LEFTOVER = ingredient_tokens("leftover cooked")


def _uses(item: PantryItem, ingredient_names: list[str]) -> bool:
    wanted = ingredient_tokens(item.name)
    for name in ingredient_names:
        tokens = ingredient_tokens(name)
        # "leftover roast chicken" needs cooked chicken, not the raw chicken in your fridge.
        if tokens & _LEFTOVER and not wanted & _LEFTOVER:
            continue
        if wanted and wanted <= tokens and not tokens & _NOT_THE_FOOD:
            return True
    return False


def rank_recipes(recipes: list, pantry: list[PantryItem], filters, limit: int) -> list[dict]:
    """Recipes using at least one pantry item, most urgent use first.

    Order: total urgency of the items used, then how many expiring items, then how many
    pantry items in all, then fewest things to buy.
    """
    ranked = []
    for recipe in recipes:
        if not filters.matches(recipe):
            continue
        ingredients = [i for i in recipe.ingredients or [] if isinstance(i, dict)]
        names = [str(i.get("name", "")) for i in ingredients]
        used = [item for item in pantry if _uses(item, names)]
        if not used:
            continue
        to_buy = [str(i.get("name")) for i in build_shopping_list(ingredients, [u.name for u in used])["need"]]
        expiring = sorted((u for u in used if u.urgency), key=lambda u: u.days_left)
        key = (
            -sum(u.urgency for u in used),
            -len(expiring),
            -len(used),
            len(to_buy),
            str(recipe.name).lower(),
        )
        ranked.append((key, {
            "recipe": recipe,
            "uses_expiring": [{"name": u.name, "days_left": u.days_left} for u in expiring],
            "uses": [u.name for u in used],
            "to_buy": to_buy,
        }))

    ranked.sort(key=lambda pair: pair[0])
    results, names_seen = [], set()
    for _, result in ranked:
        # The collection has near-duplicate names ("Stir Fry" / "Stir-Fry"); show one.
        key = " ".join(re.findall(r"[a-z]+", str(result["recipe"].name).lower()))
        if key in names_seen:
            continue
        names_seen.add(key)
        results.append(result)
        if len(results) >= limit:
            break
    return results
