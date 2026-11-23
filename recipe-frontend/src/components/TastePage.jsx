import { useState } from "react";

// What the ratings add up to, and what is sent with every new recipe. Everything here is editable.
function TastePage({ profile, ratings, onRemoveTrait, onAddAvoid, onClearRatings, onBackToIngredients }) {
  const [food, setFood] = useState("");
  const rated = Object.values(ratings).sort((a, b) => String(b.at).localeCompare(String(a.at)));
  const ups = rated.filter((r) => r.rating === "up").length;

  const submit = (event) => {
    event.preventDefault();
    food
      .split(",")
      .map((f) => f.trim())
      .filter(Boolean)
      .forEach(onAddAvoid);
    setFood("");
  };

  const traitList = (traits, empty) =>
    traits.length ? (
      <ul className="taste-list">
        {traits.map((trait) => (
          <li key={trait.text} className="taste-item">
            <span>
              <strong>{trait.text}</strong> <span className="taste-why">{trait.why}</span>
            </span>
            <button
              type="button"
              className="tile-remove-btn taste-remove"
              aria-label={`Remove ${trait.text}`}
              onClick={() => onRemoveTrait(trait)}
            >
              x
            </button>
          </li>
        ))}
      </ul>
    ) : (
      <p className="pantry-status">{empty}</p>
    );

  return (
    <main className="recipes-list-page taste-page">
      <div className="recipes-list-header">
        <button type="button" className="secondary-button" onClick={onBackToIngredients}>
          Back to Ingredients
        </button>
        <h1 className="browse-title">Your taste profile</h1>
        <p className="browse-status">
          Built from your 👍 and 👎 and sent with every new recipe you create. Saved in this browser.
        </p>
      </div>

      <section className="taste-section">
        <h2 className="recipe-section-title">You like</h2>
        <p className="taste-note">New recipes lean this way when it suits the dish.</p>
        {traitList(
          profile.likes,
          "Nothing yet. Rate recipes with 👍 (tap a reason like “Loved the spice” to count it straight away)."
        )}
      </section>

      <section className="taste-section">
        <h2 className="recipe-section-title">You avoid</h2>
        <p className="taste-note">
          New recipes leave these out, and are checked and remade if one slips in. Ask for one by name and
          you'll still get it.
        </p>
        {traitList(profile.avoids, "Nothing yet. On a 👎, tap “Didn't like an ingredient” and pick it.")}
        <form className="craving-row taste-add" onSubmit={submit}>
          <input
            type="text"
            className="ingredient-input"
            placeholder="Add a food to avoid, e.g. olives"
            aria-label="Food to avoid"
            value={food}
            onChange={(e) => setFood(e.target.value)}
          />
          <button type="submit" className="secondary-button" disabled={!food.trim()}>
            Add
          </button>
        </form>
      </section>

      <section className="taste-section">
        <h2 className="recipe-section-title">Your ratings</h2>
        {rated.length ? (
          <>
            <p className="taste-note">
              {rated.length} rated: {ups} 👍, {rated.length - ups} 👎
            </p>
            <ul className="taste-ratings">
              {rated.slice(0, 20).map((r) => (
                <li key={`${r.recipe.id ?? r.recipe.name}`}>
                  {r.rating === "up" ? "👍" : "👎"} {r.recipe.name}
                  {r.avoid?.length > 0 && <span className="taste-why"> · avoid {r.avoid.join(", ")}</span>}
                </li>
              ))}
            </ul>
            <button type="button" className="secondary-button" onClick={onClearRatings}>
              Clear ratings and profile
            </button>
          </>
        ) : (
          <p className="pantry-status">No ratings yet. Open any recipe and tap 👍 or 👎.</p>
        )}
      </section>
    </main>
  );
}

export default TastePage;
