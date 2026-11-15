"""How well does the vision model read a fridge/pantry photo?

17 Unsplash photos (fridges, pantry shelves, counters, grocery bags, one nearly empty fridge),
hand-labeled in photo_cases.json:
- must: clearly visible ingredients ("a|b" = either name counts)
- ok:   reasonable answers that aren't counted against the model ("herbs" for parsley,
        "juice" in a fridge full of bottles)

Metrics, over everything the model listed after cleanup:
- recall:    share of must items found
- precision: share of listed items that are must or ok
- invented:  listed items matching nothing in the photo
- removed by cleanup: raw items app.photo.clean_detected rejects (containers, "vegetables", sentences)

A name matches a label when one's words contain the other's ("red onion" matches "onion").
Photos are downloaded once into evals/photo_cache/ (gitignored); nothing is stored in the DB.
Usage (Ollama running with llava, from Backend/):  python -m evals.photo_eval
"""
import base64
import json
import statistics
import time
from pathlib import Path

import requests

from app.ai import VISION_MODEL_NAME, RecipeGenerationError, _call_vision_model, extract_ingredients_from_photo
from app.photo import clean_detected, name_key
from app.schemas import DetectedIngredients

EVAL_DIR = Path(__file__).parent
CACHE_DIR = EVAL_DIR / "photo_cache"


def photo_b64(case: dict) -> str:
    path = CACHE_DIR / f"{case['id']}.jpg"
    if not path.exists():
        CACHE_DIR.mkdir(exist_ok=True)
        response = requests.get(case["url"], timeout=60)
        response.raise_for_status()
        path.write_bytes(response.content)
    return base64.b64encode(path.read_bytes()).decode()


def matches(name: str, label: str) -> bool:
    a, b = name_key(name), name_key(label)
    return bool(a and b) and (a <= b or b <= a)


def score(found: list[str], case: dict) -> dict:
    must = [alts.split("|") for alts in case["must"]]
    hit = [any(matches(f, alt) for f in found for alt in alts) for alts in must]
    labels = [alt for alts in must for alt in alts] + case["ok"]
    invented = [f for f in found if not any(matches(f, label) for label in labels)]
    return {
        "must_found": sum(hit),
        "must_total": len(must),
        "missed": [alts[0] for alts, h in zip(must, hit) if not h],
        "listed": len(found),
        "invented": invented,
    }


def main() -> None:
    cases = json.loads((EVAL_DIR / "photo_cases.json").read_text())
    rows = []
    for case in cases:
        image = photo_b64(case)
        raw_outputs = []

        def recording_model(prompt, img):
            output = _call_vision_model(prompt, img)
            raw_outputs.append(output)
            return output

        started = time.perf_counter()
        try:
            found = extract_ingredients_from_photo(image, call_model=recording_model)
            row = {"id": case["id"], "kind": case["kind"], "success": True, "found": found, **score(found, case)}
            raw = DetectedIngredients.model_validate_json(raw_outputs[-1]).ingredients
            row["raw"] = raw
            row["removed_by_cleanup"] = [r for r in raw if not clean_detected([r])]
        except RecipeGenerationError as exc:
            row = {"id": case["id"], "kind": case["kind"], "success": False, "error": str(exc)}
        row["latency_seconds"] = round(time.perf_counter() - started, 1)
        rows.append(row)
        if row["success"]:
            print(f"{case['id']:<12} {case['kind']:<20} found {row['must_found']}/{row['must_total']}  "
                  f"invented {row['invented']}  missed {row['missed']}  {row['latency_seconds']}s", flush=True)
        else:
            print(f"{case['id']:<12} FAILED {row['error']}", flush=True)

    ok = [r for r in rows if r["success"]]
    labeled = [r for r in ok if r["must_total"]]
    listed = sum(r["listed"] for r in ok)
    summary = {
        "photos": len(rows),
        "produced_list": len(ok) / len(rows),
        "recall": sum(r["must_found"] for r in labeled) / sum(r["must_total"] for r in labeled),
        "precision": 1 - sum(len(r["invented"]) for r in ok) / listed if listed else None,
        "items_listed_per_photo": listed / len(ok) if ok else None,
        "invented_per_photo": sum(len(r["invented"]) for r in ok) / len(ok) if ok else None,
        "removed_by_cleanup": sum(len(r["removed_by_cleanup"]) for r in ok),
        "latency_p50_seconds": statistics.median(r["latency_seconds"] for r in rows),
    }
    by_kind = {}
    for r in labeled:
        k = by_kind.setdefault(r["kind"], {"found": 0, "total": 0})
        k["found"] += r["must_found"]
        k["total"] += r["must_total"]
    summary["recall_by_kind"] = {k: round(v["found"] / v["total"], 2) for k, v in by_kind.items()}

    (EVAL_DIR / "photo_results.json").write_text(json.dumps(
        {"model": VISION_MODEL_NAME, "summary": summary, "cases": rows}, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
