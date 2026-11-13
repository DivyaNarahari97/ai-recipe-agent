import { useEffect, useState } from "react";
import DietaryFilters from "./components/DietaryFilters";
import MealPlanPage from "./components/MealPlanPage";
import RefinePanel from "./components/RefinePanel";
import RecipeDetail from "./components/RecipeDetail";
import { API_BASE_URL } from "./config";
import { DIET_LABELS, NO_FILTERS } from "./dietary";
import {
  addToHistory,
  clearHistory,
  isFavorite,
  loadFavorites,
  loadHistory,
  toggleFavorite,
} from "./savedRecipes";
import "./App.css";

function IngredientImage({ name }) {
  const [imageUrl, setImageUrl] = useState(null);

  useEffect(() => {
    let mounted = true;

    const fetchImage = async () => {
      try {
        const res = await fetch(
          `${API_BASE_URL}/ingredient-image?name=${encodeURIComponent(name)}`
        );
        const data = await res.json();
        if (mounted) {
          setImageUrl(data.image_url || null);
        }
      } catch (err) {
        console.error("Image fetch error:", err);
        if (mounted) {
          setImageUrl(null);
        }
      }
    };

    fetchImage();

    return () => {
      mounted = false;
    };
  }, [name]);

  return (
    <img
      src={imageUrl || "https://via.placeholder.com/80?text=Food"}
      alt={name}
      className="ingredient-image"
    />
  );
}

function IngredientPage({
  ingredientsInput,
  onIngredientInputChange,
  onIngredientInputKeyDown,
  onIngredientInputBlur,
  allIngredients,
  selectedIngredients,
  loading,
  toggleIngredient,
  onRemoveIngredient,
  onGetRecipe,
  onBrowse,
  onOpenSaved,
  onSearchCraving,
  onPlanMeals,
  onOpenPlan,
  hasPlan,
  filters,
  onFiltersChange,
  errorMessage,
}) {
  const [craving, setCraving] = useState("");
  const [planDays, setPlanDays] = useState(3);

  return (
    <main className="ingredient-page">
      <section className="landing-wrap">
        <div className="landing-hero">
          <div className="landing-main">
            <section className="ingredient-card">
              <h2>Choose your vegetables</h2>
              <p>Enter ingredients and generate a recipe.</p>

              <input
                type="text"
                placeholder="What's cooking todayyyy"
                value={ingredientsInput}
                onChange={(e) => onIngredientInputChange(e.target.value)}
                onKeyDown={onIngredientInputKeyDown}
                onBlur={onIngredientInputBlur}
                className="ingredient-input"
              />

              {allIngredients.length > 0 && (
                <div className="tiles-wrap">
                  {allIngredients.map((item) => {
                    const isSelected = selectedIngredients.includes(item);

                    return (
                      <div
                        key={item}
                        onClick={() => toggleIngredient(item)}
                        className={`ingredient-tile${isSelected ? " is-selected" : ""}`}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            toggleIngredient(item);
                          }
                        }}
                      >
                        <button
                          type="button"
                          className="tile-remove-btn"
                          aria-label={`Remove ${item}`}
                          onClick={(event) => {
                            event.stopPropagation();
                            onRemoveIngredient(item);
                          }}
                        >
                          x
                        </button>
                        <IngredientImage name={item} />
                        <span>{item}</span>
                      </div>
                    );
                  })}
                </div>
              )}

              <DietaryFilters filters={filters} onChange={onFiltersChange} />

              <button
                onClick={onGetRecipe}
                className="primary-button"
                type="button"
                disabled={selectedIngredients.length === 0 || loading}
              >
                {loading ? "Cooking..." : "Get Recipe"}
              </button>

              {errorMessage && <p className="error-text">{errorMessage}</p>}

              <div className="craving-form">
                <label htmlFor="plan-days">Or plan dinners that share ingredients</label>
                <div className="craving-row">
                  <select
                    id="plan-days"
                    className="ingredient-input plan-days-select"
                    value={planDays}
                    onChange={(e) => setPlanDays(Number(e.target.value))}
                  >
                    {[2, 3, 4, 5].map((n) => (
                      <option key={n} value={n}>
                        {n} days
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={selectedIngredients.length === 0}
                    onClick={() => onPlanMeals(planDays)}
                  >
                    Plan dinners
                  </button>
                </div>
              </div>

              <form
                className="craving-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (craving.trim()) onSearchCraving(craving.trim());
                }}
              >
                <label htmlFor="craving-input">Or describe what you're craving</label>
                <div className="craving-row">
                  <input
                    id="craving-input"
                    type="search"
                    className="ingredient-input"
                    placeholder="something light and spicy for a cold night"
                    value={craving}
                    onChange={(e) => setCraving(e.target.value)}
                  />
                  <button type="submit" className="secondary-button" disabled={!craving.trim()}>
                    Search
                  </button>
                </div>
              </form>

              <div className="landing-links">
                <button type="button" className="link-button" onClick={onBrowse}>
                  Browse all recipes by cuisine
                </button>
                <button type="button" className="link-button" onClick={onOpenSaved}>
                  Favorites &amp; history
                </button>
                {hasPlan && (
                  <button type="button" className="link-button" onClick={onOpenPlan}>
                    Your dinner plan
                  </button>
                )}
              </div>
            </section>

            <div className="landing-image-wrap">
              <img
                src="https://images.unsplash.com/photo-1546793665-c74683f339c1?auto=format&fit=crop&w=900&q=80"
                alt="Vegetable salad"
                className="landing-salad-image"
              />
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}

function RecipePage({ recipe, onBack, pantry, favorite, onToggleFavorite, onRefined, onUndoRefine }) {
  return (
    <main className="recipe-page">
      <div className="recipe-page-header">
        <button type="button" className="secondary-button" onClick={onBack}>
          Back to Recipes
        </button>
        {recipe && (
          <button
            type="button"
            className={`favorite-button${favorite ? " is-active" : ""}`}
            aria-pressed={favorite}
            onClick={onToggleFavorite}
          >
            {favorite ? "♥ Saved" : "♡ Save recipe"}
          </button>
        )}
      </div>

      {recipe?.id && <RefinePanel recipe={recipe} onRefined={onRefined} onUndo={onUndoRefine} />}

      {recipe ? (
        <RecipeDetail recipe={recipe} pantry={pantry} />
      ) : (
        <section className="empty-state">
          <h2>No recipe loaded</h2>
          <p>Go back, select ingredients, and click Get Recipe.</p>
        </section>
      )}
    </main>
  );
}

function RecipeCardGrid({ recipes, onSelectRecipe }) {
  return (
    <section className="recipe-cards-grid">
      {recipes.map((recipe) => (
        <article
          key={recipe.id || recipe.name}
          className="recipe-card"
          onClick={() => onSelectRecipe(recipe)}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              onSelectRecipe(recipe);
            }
          }}
        >
          <img
            src={
              recipe.image_url ||
              "https://images.unsplash.com/photo-1504674900247-0877df9cc836?auto=format&fit=crop&w=900&q=80"
            }
            alt={recipe.name}
            className="recipe-card-image"
          />
          <div className="recipe-card-body">
            <div className="recipe-card-badges">
              {recipe.cuisine && <span className="recipe-card-cuisine">{recipe.cuisine}</span>}
              {recipe.dietary_tags?.map((tag) => (
                <span key={tag} className="recipe-card-diet">
                  {DIET_LABELS[tag] || tag}
                </span>
              ))}
            </div>
            <h3>{recipe.name}</h3>
            <p>{recipe.notes || "Tap to open full recipe details."}</p>
            <div className="recipe-card-meta">
              <span>{recipe.time || "Quick meal"}</span>
              <span>{recipe.servings ? `${recipe.servings} servings` : "Family size"}</span>
            </div>
          </div>
        </article>
      ))}
    </section>
  );
}

function RecipesPage({ recipes, onSelectRecipe, onBackToIngredients }) {
  return (
    <main className="recipes-list-page">
      <div className="recipes-list-header">
        <button type="button" className="secondary-button" onClick={onBackToIngredients}>
          Back to Ingredients
        </button>
      </div>

      {recipes.length > 0 ? (
        <RecipeCardGrid recipes={recipes} onSelectRecipe={onSelectRecipe} />
      ) : (
        <section className="empty-state">
          <h2>No recipes found</h2>
          <p>Go back and try different vegetables.</p>
        </section>
      )}
    </main>
  );
}

function BrowsePage({ cuisine, onCuisineChange, onSelectRecipe, onBackToIngredients }) {
  const [cuisines, setCuisines] = useState([]);
  // Which cuisine the loaded results belong to; while it differs from `cuisine`, we're loading.
  const [loaded, setLoaded] = useState({ cuisine: null, recipes: [], error: false });

  useEffect(() => {
    fetch(`${API_BASE_URL}/cuisines`)
      .then((res) => (res.ok ? res.json() : []))
      .then(setCuisines)
      .catch((err) => console.error("Cuisine fetch error:", err));
  }, []);

  useEffect(() => {
    let current = true;
    const query = cuisine ? `?cuisine=${encodeURIComponent(cuisine)}` : "";

    fetch(`${API_BASE_URL}/recipes${query}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Recipes request failed: ${res.status}`);
        return res.json();
      })
      .then((data) => {
        if (current) setLoaded({ cuisine, recipes: data, error: false });
      })
      .catch((err) => {
        console.error(err);
        if (current) setLoaded({ cuisine, recipes: [], error: true });
      });

    // Ignore a slower response for a chip the user has already clicked away from.
    return () => {
      current = false;
    };
  }, [cuisine]);

  const isLoading = loaded.cuisine !== cuisine;

  const chips = [{ cuisine: "", label: "All" }].concat(
    cuisines.map((c) => ({ cuisine: c.cuisine, label: `${c.cuisine} (${c.count})` }))
  );

  return (
    <main className="recipes-list-page">
      <div className="recipes-list-header">
        <button type="button" className="secondary-button" onClick={onBackToIngredients}>
          Back to Ingredients
        </button>
        <h1 className="browse-title">Browse by cuisine</h1>
      </div>

      <div className="cuisine-filter" role="group" aria-label="Filter by cuisine">
        {chips.map((chip) => (
          <button
            key={chip.label}
            type="button"
            className={`cuisine-chip${chip.cuisine === cuisine ? " is-active" : ""}`}
            aria-pressed={chip.cuisine === cuisine}
            onClick={() => onCuisineChange(chip.cuisine)}
          >
            {chip.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <p className="browse-status">Loading recipes…</p>
      ) : loaded.error ? (
        <section className="empty-state">
          <h2>Couldn't load recipes</h2>
          <p>Check that the backend is running, then try again.</p>
        </section>
      ) : loaded.recipes.length === 0 ? (
        <section className="empty-state">
          <h2>No saved recipes{cuisine ? ` for ${cuisine}` : ""} yet</h2>
          <p>Generate a recipe from your ingredients and it will show up here.</p>
        </section>
      ) : (
        <RecipeCardGrid recipes={loaded.recipes} onSelectRecipe={onSelectRecipe} />
      )}
    </main>
  );
}

function SearchPage({ query, filters, onSelectRecipe, onRecipeCreated, onBackToIngredients }) {
  // Which request the loaded results belong to; while it differs, we're loading.
  const requestKey = JSON.stringify({ query, filters });
  const [loaded, setLoaded] = useState({ key: null, hits: [], error: "" });
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  const createRecipe = async () => {
    setCreating(true);
    setCreateError("");
    try {
      const res = await fetch(`${API_BASE_URL}/search/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, filters }),
      });
      if (!res.ok) {
        throw new Error(
          res.status === 422
            ? "Couldn't create a new recipe that fits. Try rewording the craving or loosening your preferences."
            : "Couldn't create a recipe right now. Check that Ollama is running."
        );
      }
      const data = await res.json();
      onRecipeCreated({ ...data.recipe, inspired_by: data.inspired_by });
    } catch (err) {
      console.error(err);
      setCreateError(err.message);
      setCreating(false);
    }
  };

  useEffect(() => {
    if (!query) return undefined;
    let current = true;

    fetch(`${API_BASE_URL}/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, filters, limit: 9 }),
    })
      .then(async (res) => {
        if (!res.ok) {
          throw new Error(
            res.status === 502
              ? "Craving search needs Ollama running with the nomic-embed-text model."
              : "Search failed. Please try again."
          );
        }
        return res.json();
      })
      .then((data) => {
        if (current) setLoaded({ key: requestKey, hits: data.results, error: "" });
      })
      .catch((err) => {
        console.error(err);
        if (current) setLoaded({ key: requestKey, hits: [], error: err.message });
      });

    return () => {
      current = false;
    };
  }, [query, filters, requestKey]);

  const filtersOn = Object.values(filters).some(Boolean);

  return (
    <main className="recipes-list-page">
      <div className="recipes-list-header">
        <button type="button" className="secondary-button" onClick={onBackToIngredients}>
          Back to Ingredients
        </button>
        <h1 className="browse-title">{query ? `“${query}”` : "Search by craving"}</h1>
        {query && filtersOn && <p className="browse-status">With your dietary preferences applied.</p>}
        {query && loaded.key === requestKey && !loaded.error && (
          <div className="create-from-search">
            <button
              type="button"
              className="secondary-button"
              onClick={createRecipe}
              disabled={creating}
            >
              {creating ? "Creating your recipe… (about 30 seconds)" : "Create a new recipe from these"}
            </button>
            <p className="browse-status">A new recipe inspired by the top matches below.</p>
            {createError && <p className="error-text">{createError}</p>}
          </div>
        )}
      </div>

      {!query ? (
        <section className="empty-state saved-empty">
          <p>Describe what you're craving on the home page to search.</p>
        </section>
      ) : loaded.key !== requestKey ? (
        <p className="browse-status">Searching…</p>
      ) : loaded.error ? (
        <section className="empty-state saved-empty">
          <p>{loaded.error}</p>
        </section>
      ) : loaded.hits.length === 0 ? (
        <section className="empty-state saved-empty">
          <p>No recipes matched. Try describing it differently{filtersOn ? " or loosening your filters" : ""}.</p>
        </section>
      ) : (
        <RecipeCardGrid recipes={loaded.hits.map((hit) => hit.recipe)} onSelectRecipe={onSelectRecipe} />
      )}
    </main>
  );
}

function SavedPage({ favorites, history, onSelectRecipe, onClearHistory, onBackToIngredients }) {
  return (
    <main className="recipes-list-page">
      <div className="recipes-list-header">
        <button type="button" className="secondary-button" onClick={onBackToIngredients}>
          Back to Ingredients
        </button>
        <h1 className="browse-title">Favorites</h1>
      </div>
      {favorites.length > 0 ? (
        <RecipeCardGrid recipes={favorites} onSelectRecipe={onSelectRecipe} />
      ) : (
        <section className="empty-state saved-empty">
          <p>No favorites yet. Open a recipe and tap “Save recipe”.</p>
        </section>
      )}

      <div className="recipes-list-header saved-section-header">
        <h2 className="browse-title">Recently viewed</h2>
        {history.length > 0 && (
          <button type="button" className="secondary-button" onClick={onClearHistory}>
            Clear history
          </button>
        )}
      </div>
      {history.length > 0 ? (
        <RecipeCardGrid recipes={history} onSelectRecipe={onSelectRecipe} />
      ) : (
        <section className="empty-state saved-empty">
          <p>Recipes you open will show up here.</p>
        </section>
      )}
    </main>
  );
}

function App() {
  const [path, setPath] = useState(window.location.pathname);
  const [ingredientsInput, setIngredientsInput] = useState("");
  const [allIngredients, setAllIngredients] = useState([]);
  const [selectedIngredients, setSelectedIngredients] = useState([]);
  const [recipeResults, setRecipeResults] = useState([]);
  const [selectedRecipe, setSelectedRecipe] = useState(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [browseCuisine, setBrowseCuisine] = useState("");
  const [detailBackPath, setDetailBackPath] = useState("/");
  const [filters, setFilters] = useState(NO_FILTERS);
  const [favorites, setFavorites] = useState(loadFavorites);
  const [history, setHistory] = useState(loadHistory);
  const [cravingQuery, setCravingQuery] = useState("");
  // { key, request, status: "loading" | "done" | "error", data, error }; kept here so a
  // plan that takes minutes survives browsing away and back.
  const [mealPlan, setMealPlan] = useState(null);

  useEffect(() => {
    const handlePopState = () => {
      setPath(window.location.pathname);
    };

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const navigate = (nextPath, replace = false) => {
    if (replace) {
      window.history.replaceState({}, "", nextPath);
    } else {
      window.history.pushState({}, "", nextPath);
    }
    setPath(nextPath);
  };

  useEffect(() => {
    if (!["/", "/recipes", "/recipe", "/browse", "/saved", "/search", "/plan"].includes(path)) {
      navigate("/", true);
    }
  }, [path]);

  const parseIngredients = (rawInput) =>
    rawInput
      .split(",")
      .map((item) => item.trim().toLowerCase())
      .filter((item) => item !== "");

  const addIngredients = (rawInput) => {
    const parsed = Array.from(new Set(parseIngredients(rawInput)));
    if (parsed.length === 0) {
      return;
    }

    setAllIngredients((prev) => Array.from(new Set([...prev, ...parsed])));
    setSelectedIngredients((prev) => Array.from(new Set([...prev, ...parsed])));
    setRecipeResults([]);
    setSelectedRecipe(null);
    setErrorMessage("");
  };

  const toggleIngredient = (ingredient) => {
    setSelectedIngredients((prev) =>
      prev.includes(ingredient)
        ? prev.filter((i) => i !== ingredient)
        : [...prev, ingredient]
    );
  };

  const removeIngredient = (ingredient) => {
    setAllIngredients((prev) => prev.filter((item) => item !== ingredient));
    setSelectedIngredients((prev) => prev.filter((item) => item !== ingredient));
    setRecipeResults([]);
    setSelectedRecipe(null);
    setErrorMessage("");
  };

  const commitIngredientInput = () => {
    if (!ingredientsInput.trim()) {
      return;
    }
    addIngredients(ingredientsInput);
    setIngredientsInput("");
  };

  const handleIngredientInputKeyDown = (event) => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      commitIngredientInput();
    }
  };

  const handleIngredientInputBlur = () => {
    commitIngredientInput();
  };

  const handleGetRecipe = async () => {
    if (selectedIngredients.length === 0 || loading) {
      return;
    }

    setErrorMessage("");
    setLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/assistant`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          ingredients: selectedIngredients,
          filters,
        }),
      });

      const data = await response.json();

      if (data.results && data.results.length > 0) {
        setRecipeResults(data.results);
        setSelectedRecipe(null);
        navigate("/recipes");
      } else {
        setRecipeResults([]);
        setSelectedRecipe(null);
        setErrorMessage(
          Object.values(filters).some(Boolean)
            ? "No recipe found that meets your dietary preferences. Try loosening them."
            : "No recipe found for these ingredients."
        );
      }
    } catch (error) {
      console.error(error);
      setSelectedRecipe(null);
      setErrorMessage("Failed to fetch recipe. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleBack = () => {
    navigate(detailBackPath);
  };

  const handleSelectRecipe = (recipe, backPath) => {
    setSelectedRecipe(recipe);
    setDetailBackPath(backPath);
    setHistory((prev) => addToHistory(prev, recipe));
    navigate("/recipe");
  };

  const handleRefined = (refined, change) => {
    // Keep the version before the change so it can be undone; the trail lists every change so far.
    const next = {
      ...refined,
      refinements: [...(selectedRecipe?.refinements || []), change],
      previous: selectedRecipe,
    };
    setSelectedRecipe(next);
    setHistory((prev) => addToHistory(prev, next));
  };

  const handleUndoRefine = () => {
    if (selectedRecipe?.previous) setSelectedRecipe(selectedRecipe.previous);
  };

  const handlePlanMeals = async (days) => {
    const request = { ingredients: selectedIngredients, days, filters };
    const key = JSON.stringify(request);
    navigate("/plan");
    if (mealPlan?.key === key && mealPlan.status !== "error") return;

    setMealPlan({ key, request, status: "loading" });
    // A newer request may have replaced this one by the time it finishes.
    const settle = (update) => setMealPlan((prev) => (prev?.key === key ? { ...prev, ...update } : prev));
    try {
      const res = await fetch(`${API_BASE_URL}/meal-plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: key,
      });
      if (!res.ok) {
        throw new Error(
          res.status === 422
            ? "None of our recipes fit your dietary preferences. Try loosening them."
            : "Couldn't plan dinners right now. Check that Ollama is running and try again."
        );
      }
      settle({ status: "done", data: await res.json() });
    } catch (err) {
      console.error(err);
      settle({ status: "error", error: err.message });
    }
  };

  const handleBackToIngredients = () => {
    navigate("/");
  };

  return path === "/recipe" ? (
    <RecipePage
      recipe={selectedRecipe}
      onBack={handleBack}
      pantry={selectedIngredients}
      favorite={isFavorite(favorites, selectedRecipe)}
      onToggleFavorite={() => setFavorites((prev) => toggleFavorite(prev, selectedRecipe))}
      onRefined={handleRefined}
      onUndoRefine={handleUndoRefine}
    />
  ) : path === "/recipes" ? (
    <RecipesPage
      recipes={recipeResults}
      onSelectRecipe={(recipe) => handleSelectRecipe(recipe, "/recipes")}
      onBackToIngredients={handleBackToIngredients}
    />
  ) : path === "/browse" ? (
    <BrowsePage
      cuisine={browseCuisine}
      onCuisineChange={setBrowseCuisine}
      onSelectRecipe={(recipe) => handleSelectRecipe(recipe, "/browse")}
      onBackToIngredients={handleBackToIngredients}
    />
  ) : path === "/search" ? (
    <SearchPage
      query={cravingQuery}
      filters={filters}
      onSelectRecipe={(recipe) => handleSelectRecipe(recipe, "/search")}
      onRecipeCreated={(recipe) => handleSelectRecipe(recipe, "/search")}
      onBackToIngredients={handleBackToIngredients}
    />
  ) : path === "/plan" ? (
    <MealPlanPage
      plan={mealPlan}
      onSelectRecipe={(recipe) => handleSelectRecipe(recipe, "/plan")}
      onBackToIngredients={handleBackToIngredients}
    />
  ) : path === "/saved" ? (
    <SavedPage
      favorites={favorites}
      history={history}
      onSelectRecipe={(recipe) => handleSelectRecipe(recipe, "/saved")}
      onClearHistory={() => setHistory(clearHistory())}
      onBackToIngredients={handleBackToIngredients}
    />
  ) : (
    <IngredientPage
      ingredientsInput={ingredientsInput}
      onIngredientInputChange={(value) => {
        setIngredientsInput(value);
        setRecipeResults([]);
        setErrorMessage("");
      }}
      onIngredientInputKeyDown={handleIngredientInputKeyDown}
      onIngredientInputBlur={handleIngredientInputBlur}
      allIngredients={allIngredients}
      selectedIngredients={selectedIngredients}
      loading={loading}
      toggleIngredient={toggleIngredient}
      onRemoveIngredient={removeIngredient}
      onGetRecipe={handleGetRecipe}
      onBrowse={() => navigate("/browse")}
      onOpenSaved={() => navigate("/saved")}
      onPlanMeals={handlePlanMeals}
      onOpenPlan={() => navigate("/plan")}
      hasPlan={Boolean(mealPlan)}
      onSearchCraving={(query) => {
        setCravingQuery(query);
        navigate("/search");
      }}
      filters={filters}
      onFiltersChange={setFilters}
      errorMessage={errorMessage}
    />
  );
}

export default App;
