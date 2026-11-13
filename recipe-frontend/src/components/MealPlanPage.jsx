import { useState } from "react";

const FALLBACK_IMAGE =
  "https://images.unsplash.com/photo-1504674900247-0877df9cc836?auto=format&fit=crop&w=900&q=80";

const dayList = (days) => (days.length === 1 ? `day ${days[0]}` : `days ${days.join(", ")}`);

function DayCard({ entry, onSelect }) {
  const { recipe } = entry;
  return (
    <article
      className="recipe-card"
      onClick={() => onSelect(recipe)}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect(recipe);
        }
      }}
    >
      <img src={recipe.image_url || FALLBACK_IMAGE} alt={recipe.name} className="recipe-card-image" />
      <div className="recipe-card-body">
        <div className="recipe-card-badges">
          <span className="plan-day-badge">Day {entry.day}</span>
          {recipe.cuisine && <span className="recipe-card-cuisine">{recipe.cuisine}</span>}
          {entry.new && <span className="recipe-card-diet">New recipe</span>}
        </div>
        <h3>{recipe.name}</h3>
        <p>
          {entry.uses_pantry.length > 0
            ? `Uses your ${entry.uses_pantry.join(", ")}`
            : "Uses none of your ingredients"}
        </p>
        <div className="recipe-card-meta">
          <span>{recipe.time || "Quick meal"}</span>
          <span>{recipe.servings ? `${recipe.servings} servings` : "Family size"}</span>
        </div>
      </div>
    </article>
  );
}

function PlanShoppingList({ items, staples, days }) {
  const [bought, setBought] = useState(() => new Set());
  const [copyMessage, setCopyMessage] = useState("");

  const toggle = (name) => {
    setCopyMessage("");
    setBought((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const copyList = async () => {
    const lines = items
      .filter((item) => !bought.has(item.name))
      .map((item) => `- ${item.name}${item.quantities.length ? ` (${item.quantities.join(" + ")})` : ""}`);
    try {
      await navigator.clipboard.writeText([`Shopping list: ${days}-day meal plan`, ...lines].join("\n"));
      setCopyMessage("Copied!");
    } catch {
      setCopyMessage("Couldn't copy. Select the list and copy it manually.");
    }
  };

  return (
    <section className="plan-panel">
      <h2>One shopping list</h2>
      {items.length === 0 ? (
        <p>Nothing to buy: you have everything these dinners need.</p>
      ) : (
        <ul className="shopping-items">
          {items.map((item) => (
            <li key={item.name} className={bought.has(item.name) ? "is-have" : ""}>
              <label>
                <input type="checkbox" checked={bought.has(item.name)} onChange={() => toggle(item.name)} />
                <span>
                  {item.name}
                  {item.quantities.length > 0 && ` (${item.quantities.join(" + ")})`}
                  <span className={`plan-item-days${item.days.length > 1 ? " is-shared" : ""}`}>
                    {" "}· {dayList(item.days)}
                  </span>
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}
      {staples.length > 0 && <p className="shopping-hint">Pantry staples: {staples.join(", ")}</p>}
      {items.length > 0 && (
        <button type="button" className="shopping-button" onClick={copyList}>
          Copy list
        </button>
      )}
      {copyMessage && <p className="shopping-hint">{copyMessage}</p>}
    </section>
  );
}

function MealPlanPage({ plan, onSelectRecipe, onBackToIngredients }) {
  const days = plan?.request.days;
  return (
    <main className="recipes-list-page">
      <div className="recipes-list-header">
        <button type="button" className="secondary-button" onClick={onBackToIngredients}>
          Back to Ingredients
        </button>
        <h1 className="browse-title">{days ? `Your ${days}-day dinner plan` : "Dinner plan"}</h1>
      </div>

      {!plan && (
        <section className="empty-state saved-empty">
          <p>Pick your ingredients, then choose “Plan dinners”.</p>
        </section>
      )}

      {plan?.status === "loading" && (
        <section className="empty-state saved-empty" aria-live="polite">
          <p>
            Planning dinners with {plan.request.ingredients.join(", ")}… The planner shortlists
            recipes, drafts a plan, checks it for shared ingredients and writes any new dishes.
            This takes a few minutes; you can browse in the meantime.
          </p>
        </section>
      )}

      {plan?.status === "error" && (
        <section className="empty-state saved-empty">
          <p className="error-text">{plan.error}</p>
        </section>
      )}

      {plan?.status === "done" && (
        <>
          <section className="recipe-cards-grid">
            {plan.data.days.map((entry) => (
              <DayCard key={entry.day} entry={entry} onSelect={onSelectRecipe} />
            ))}
          </section>

          <div className="plan-columns">
            <PlanShoppingList items={plan.data.shopping_list} staples={plan.data.staples} days={days} />

            <section className="plan-panel">
              <h2>Your ingredients</h2>
              <ul className="plan-pantry">
                {plan.data.pantry_used.map((use) => (
                  <li key={use.ingredient}>
                    {use.ingredient} <span className="plan-item-days">· {dayList(use.days)}</span>
                  </li>
                ))}
              </ul>
              {plan.data.pantry_unused.length > 0 && (
                <p className="shopping-hint">Not used: {plan.data.pantry_unused.join(", ")}</p>
              )}

              <details className="plan-steps">
                <summary>How this plan was made</summary>
                <ol>
                  {plan.data.steps.map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ol>
              </details>
            </section>
          </div>
        </>
      )}
    </main>
  );
}

export default MealPlanPage;
