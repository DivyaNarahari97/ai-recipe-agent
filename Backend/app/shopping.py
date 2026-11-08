"""Split a recipe's ingredients into what to buy and what the user already has."""
from app.ingredients import ingredient_tokens

# Assumed to be in every kitchen, so they're listed separately rather than as "to buy".
_STAPLE_TOKENS = ingredient_tokens(
    "salt pepper black white sea kosher water hot cold warm ice and"
)


def build_shopping_list(ingredients: list[dict], have: list[str]) -> dict:
    have_tokens = [tokens for tokens in (ingredient_tokens(h) for h in have) if tokens]
    result = {"need": [], "have": [], "staples": []}

    for item in ingredients or []:
        tokens = ingredient_tokens(str(item.get("name", "")))
        if tokens and any(owned <= tokens for owned in have_tokens):
            # "chicken" covers "chicken breasts".
            result["have"].append(item)
        elif tokens <= _STAPLE_TOKENS:
            # Also catches junk names with no real words, like "to taste".
            result["staples"].append(item)
        else:
            result["need"].append(item)
    return result
