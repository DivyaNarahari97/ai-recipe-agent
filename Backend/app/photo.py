"""Fridge/pantry photo -> ingredient names: image checks and cleanup of what the vision model lists."""
import base64
import binascii
import re

from app.ingredients import ingredient_tokens

MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_DETECTED = 25
MAX_NAME_WORDS = 4

# Things a vision model names in a fridge photo that aren't ingredients you can cook with.
_NOT_INGREDIENTS = {
    "fridge", "refrigerator", "freezer", "shelf", "shelves", "drawer", "door", "pantry",
    "container", "containers", "jar", "jars", "bottle", "bottles", "box", "boxes", "bag", "bags",
    "can", "cans", "carton", "plate", "bowl", "tray", "lid", "packaging", "package", "label",
    "food", "foods", "groceries", "items", "vegetables", "vegetable", "fruits", "fruit", "produce",
    "condiments", "sauces", "drinks", "beverages", "leftovers", "snacks", "ingredients",
}
_LEADING = re.compile(
    r"^(?:(?:a few|a|an|some|several|\d+(?:\.\d+)?)\s+)?"
    r"(?:(?:jar|bottle|box|bag|carton|can|container|pack|packet|bunch|tub|head|loaf|block|piece"
    r"|bowl|plate|tray|slice)s?\s+of\s+)?"
)


class InvalidImage(ValueError):
    """The upload isn't a usable photo."""


def decode_image(data: str) -> str:
    """Check a base64 photo (plain or data URL) and return it as plain base64 for the model."""
    if data.startswith("data:"):
        data = data.partition(",")[2]
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidImage("Not a valid image upload") from exc
    if not raw:
        raise InvalidImage("Not a valid image upload")
    if len(raw) > MAX_PHOTO_BYTES:
        raise InvalidImage("Photo is too large (5 MB max)")
    if not raw.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")):
        raise InvalidImage("Use a JPEG or PNG photo")
    return base64.b64encode(raw).decode("ascii")


def name_key(name: str) -> frozenset:
    """Words of a name, plural-insensitive: "apple"/"apples" and "grape"/"grapes" match."""
    # ingredient_tokens turns "apples" into "appl" but leaves "apple", so drop the trailing e too.
    return frozenset(token.rstrip("e") for token in ingredient_tokens(name))


def clean_detected(names: list[str]) -> list[str]:
    """Lowercase plain names, without containers, generic categories or duplicates ("egg"/"eggs")."""
    cleaned: list[str] = []
    seen: set[frozenset] = set()
    for name in names:
        name = " ".join(str(name).lower().replace("_", " ").split()).strip(" .,;:!-*\"'")
        name = _LEADING.sub("", name).strip()
        if not re.search(r"[a-z]", name) or len(name.split()) > MAX_NAME_WORDS:
            continue
        if name in _NOT_INGREDIENTS:
            continue
        key = name_key(name)
        if not key or key in seen:
            continue
        seen.add(key)
        cleaned.append(name)
    return cleaned[:MAX_DETECTED]
