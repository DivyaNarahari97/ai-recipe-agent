import { useState } from "react";
import { API_BASE_URL } from "../config";
import { DIET_LABELS } from "../dietary";
import { recipeScale } from "../quantities";
import ServingsScaler from "./ServingsScaler";
import ShoppingList from "./ShoppingList";

function IngredientItem({ item, quantity }) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState("idle"); // idle | loading | done | error
  const [substitutes, setSubstitutes] = useState([]);

  const toggleSwaps = async () => {
    const nextOpen = !open;
    setOpen(nextOpen);
    if (!nextOpen || status === "done" || status === "loading") {
      return;
    }

    setStatus("loading");
    try {
      const res = await fetch(
        `${API_BASE_URL}/substitutions?ingredient=${encodeURIComponent(item.name)}`
      );
      if (!res.ok) {
        throw new Error(`Substitutions request failed: ${res.status}`);
      }
      const data = await res.json();
      setSubstitutes(data.substitutes || []);
      setStatus("done");
    } catch (err) {
      console.error(err);
      setStatus("error");
    }
  };

  return (
    <li>
      <div className="recipe-ingredient-row">
        <span>
          {quantity && <strong className="recipe-quantity">{quantity}</strong>} {item.name}
        </span>
        <button
          type="button"
          className="swap-button"
          onClick={toggleSwaps}
          aria-expanded={open}
        >
          {open ? "Hide" : "Missing this?"}
        </button>
      </div>
      {open && (
        <p className="swap-text" aria-live="polite">
          {status === "loading" && "Finding swaps…"}
          {status === "done" && `Use instead: ${substitutes.join(", ")}`}
          {status === "error" && "Couldn't find swaps right now. Try again."}
        </p>
      )}
    </li>
  );
}

function RecipeDetail({ recipe, pantry = [], scale, onServingsChange, onSystemChange }) {
  if (!recipe) return null;
  const shown = scale || recipeScale(recipe, null);
  const resized = shown.factor !== 1;
  const converted = shown.system !== "original";

  const meta = [
    recipe.cuisine && recipe.cuisine !== "Other"
      ? { icon: "🌍", label: recipe.cuisine }
      : null,
    recipe.servings
      ? { icon: "🍴", label: `${resized ? shown.servings : recipe.servings} servings` }
      : null,
    recipe.time ? { icon: "◷", label: recipe.time } : null,
    recipe.calories ? { icon: "•", label: recipe.calories } : null,
  ].filter(Boolean);

  const allSteps =
    recipe.instructions?.flatMap((section) =>
      section.steps?.map((step) => ({
        section: section.section,
        step,
      })) || []
    ) || [];

  return (
    <article className="recipe-layout">
      <header className="recipe-hero-head">
        <div>
          <h1 className="recipe-title">{recipe.name}</h1>
          <p className="recipe-subtitle">
            {recipe.description || "FAST AND DELICIOUS RECIPE FOR THE WHOLE FAMILY"}
          </p>
          {recipe.inspired_by?.length > 0 && (
            <p className="recipe-inspired-by">
              Inspired by: {recipe.inspired_by.map((source) => source.name).join(", ")}
            </p>
          )}
          {recipe.dietary_tags?.length > 0 && (
            <ul className="recipe-diet-tags" aria-label="Dietary">
              {recipe.dietary_tags.map((tag) => (
                <li key={tag}>{DIET_LABELS[tag] || tag}</li>
              ))}
            </ul>
          )}
        </div>

        {meta.length > 0 && (
          <ul className="recipe-meta-list">
            {meta.map((item) => (
              <li key={item.label} className="recipe-meta-item">
                <span className="recipe-meta-icon">{item.icon}</span>
                {item.label}
              </li>
            ))}
          </ul>
        )}
      </header>

      {recipe.image_url && (
        <img src={recipe.image_url} alt={recipe.name} className="recipe-hero-image" />
      )}

      <section className="recipe-content-block">
        <section className="recipe-ingredients-col">
          <h2 className="recipe-section-title">INGREDIENTS</h2>
          {onServingsChange && (
            <ServingsScaler
              scale={shown}
              originalServings={recipe.servings}
              onServingsChange={onServingsChange}
              onSystemChange={onSystemChange}
            />
          )}
          <ul className="recipe-ingredient-list">
            {recipe.ingredients?.map((item, i) => (
              <IngredientItem key={`${item.name}-${i}`} item={item} quantity={shown.quantity(item)} />
            ))}
          </ul>
          {recipe.id && <ShoppingList recipe={recipe} pantry={pantry} quantity={shown.quantity} />}
        </section>

        <section className="recipe-directions-col">
          <h2 className="recipe-section-title">DIRECTIONS</h2>
          {(resized || converted) && (
            <p className="scaler-note">
              The directions still use the original {resized ? `amounts for ${recipe.servings} servings` : "units"}.
            </p>
          )}
          <ol className="recipe-step-list">
            {allSteps.map((entry, i) => (
              <li key={`${entry.section || "step"}-${i}`}>
                {entry.step}
              </li>
            ))}
          </ol>

          {recipe.notes && <p className="recipe-notes">Note: {recipe.notes}</p>}
        </section>
      </section>
    </article>
  );
}

export default RecipeDetail;
