import { useState } from "react";
import { REASONS, foodName, profileSummary } from "../taste";

// 👍 / 👎 with optional reasons; what it adds up to is shown right away.
function RecipeRating({ recipe, rating, profile, onRate, onOpenTaste }) {
  // Reasons open after a new thumb and close on "Done". Tapping the chosen thumb again clears the rating.
  const [open, setOpen] = useState(false);
  const current = rating?.rating || null;
  const reasons = rating?.reasons || [];
  const avoid = rating?.avoid || [];

  const foods = [...new Set((recipe.ingredients || []).map((i) => foodName(i.name)).filter(Boolean))];

  const choose = (thumb) => {
    if (current === thumb) {
      onRate(null);
      setOpen(false);
      return;
    }
    onRate(thumb, [], []);
    setOpen(true);
  };

  const toggleReason = (id) => {
    const next = reasons.includes(id) ? reasons.filter((r) => r !== id) : [...reasons, id];
    onRate(current, next, next.includes("ingredient") ? avoid : []);
  };

  const toggleFood = (food) => {
    const next = avoid.includes(food) ? avoid.filter((f) => f !== food) : [...avoid, food];
    onRate(current, reasons, next);
  };

  const summary = profileSummary(profile);

  return (
    <section className="rating" aria-label="Rate this recipe">
      <div className="rating-row">
        <span className="rating-question">{current ? "Thanks! Your rating:" : "How was it?"}</span>
        <button
          type="button"
          className={`rating-thumb${current === "up" ? " is-active" : ""}`}
          aria-pressed={current === "up"}
          aria-label="Thumbs up"
          onClick={() => choose("up")}
        >
          👍
        </button>
        <button
          type="button"
          className={`rating-thumb${current === "down" ? " is-active" : ""}`}
          aria-pressed={current === "down"}
          aria-label="Thumbs down"
          onClick={() => choose("down")}
        >
          👎
        </button>
        {current && !open && (
          <button type="button" className="link-button" onClick={() => setOpen(true)}>
            {reasons.length ? "Change reasons" : "Add a reason"}
          </button>
        )}
      </div>

      {current && open && (
        <div className="rating-reasons">
          <p className="rating-hint">{current === "up" ? "What did you like? (optional)" : "What was wrong? (optional)"}</p>
          <div className="rating-chips">
            {REASONS[current].map((reason) => (
              <button
                key={reason.id}
                type="button"
                className={`refine-chip${reasons.includes(reason.id) ? " is-active" : ""}`}
                aria-pressed={reasons.includes(reason.id)}
                onClick={() => toggleReason(reason.id)}
              >
                {reason.label}
              </button>
            ))}
          </div>
          {current === "down" && reasons.includes("ingredient") && (
            <>
              <p className="rating-hint">Which one? Future recipes will leave it out.</p>
              <div className="rating-chips">
                {foods.map((food) => (
                  <button
                    key={food}
                    type="button"
                    className={`refine-chip${avoid.includes(food) ? " is-active" : ""}`}
                    aria-pressed={avoid.includes(food)}
                    onClick={() => toggleFood(food)}
                  >
                    {food}
                  </button>
                ))}
              </div>
            </>
          )}
          <button type="button" className="link-button" onClick={() => setOpen(false)}>
            Done
          </button>
        </div>
      )}

      {current && (
        <p className="rating-profile">
          {summary ? `Your taste profile: ${summary}. ` : "Rate a few more recipes to build your taste profile. "}
          <button type="button" className="link-button" onClick={onOpenTaste}>
            {summary ? "Edit" : "See profile"}
          </button>
        </p>
      )}
    </section>
  );
}

export default RecipeRating;
