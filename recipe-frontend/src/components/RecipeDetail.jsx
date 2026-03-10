function RecipeDetail({ recipe }) {
  if (!recipe) return null;

  const meta = [
    recipe.servings
      ? { icon: "🍴", label: `${recipe.servings} servings` }
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
          <ul className="recipe-ingredient-list">
            {recipe.ingredients?.map((item, i) => (
              <li key={`${item.name}-${i}`}>
                {item.quantity} {item.name}
              </li>
            ))}
          </ul>
        </section>

        <section className="recipe-directions-col">
          <h2 className="recipe-section-title">DIRECTIONS</h2>
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
