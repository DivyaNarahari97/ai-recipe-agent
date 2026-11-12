"""Scale ingredient quantities when a refinement changes the servings.

The model updates "servings" reliably but often leaves the quantities as they were
(or scales them by the wrong factor), so the arithmetic happens here.
"""
import re
from fractions import Fraction
from typing import Optional

_NUMBER = r"\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?"
_LEADING_AMOUNT = re.compile(rf"^\s*({_NUMBER})(?:\s*(-|–|to)\s*({_NUMBER}))?")
_NICE_DENOMINATORS = (2, 3, 4, 8)


def _parse_number(text: str) -> Fraction:
    parts = text.split()
    return sum((Fraction(p) for p in parts), Fraction(0))


def _format_number(value: Fraction) -> str:
    whole, rest = divmod(value, 1)
    if rest == 0:
        return str(int(whole))
    for denominator in _NICE_DENOMINATORS:
        numerator = round(rest * denominator)
        if abs(Fraction(numerator, denominator) - rest) < Fraction(1, 50) and 0 < numerator < denominator:
            fraction = f"{numerator}/{denominator}"
            return f"{int(whole)} {fraction}" if whole else fraction
    # No kitchen-friendly fraction is close: round to one decimal.
    return f"{float(value):.1f}".rstrip("0").rstrip(".")


def parse_servings(value) -> Optional[int]:
    """'4', '4 servings', 'Serves 6' → the number; ranges and unknowns → None."""
    numbers = re.findall(r"\d+", str(value or ""))
    return int(numbers[0]) if len(numbers) == 1 and int(numbers[0]) > 0 else None


def scale_quantity(quantity, factor: Fraction) -> Optional[str]:
    """'1 1/2 cups' × 2 → '3 cups'. Quantities without a leading number ('a pinch') → unchanged."""
    if quantity is None:
        return None
    text = str(quantity)
    match = _LEADING_AMOUNT.match(text)
    if not match:
        return text
    low, separator, high = match.groups()
    scaled = _format_number(_parse_number(low) * factor)
    if high:
        scaled += f"{' to ' if separator == 'to' else '-'}{_format_number(_parse_number(high) * factor)}"
    return scaled + text[match.end():]


def _key(value) -> str:
    return " ".join(str(value or "").lower().split())


def scale_for_new_servings(source, refined) -> int:
    """Scale the quantities the model copied over unchanged; returns how many were scaled.

    Quantities the model did change (it scaled them itself, or the refinement replaced
    the ingredient) are left alone, so nothing is scaled twice.
    """
    old, new = parse_servings(source.servings), parse_servings(refined.servings)
    if not old or not new or old == new:
        return 0
    factor = Fraction(new, old)
    original = {
        (_key(i.get("name")), _key(i.get("quantity")))
        for i in source.ingredients or []
        if isinstance(i, dict)
    }
    scaled = 0
    for ingredient in refined.ingredients:
        if ingredient.quantity and (_key(ingredient.name), _key(ingredient.quantity)) in original:
            ingredient.quantity = scale_quantity(ingredient.quantity, factor)
            scaled += 1
    return scaled
