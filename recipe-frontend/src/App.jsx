import { useEffect, useState } from "react";
import RecipeDetail from "./components/RecipeDetail";
import "./App.css";

const API_BASE_URL = "http://localhost:8000";

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
  errorMessage,
}) {
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

              <button
                onClick={onGetRecipe}
                className="primary-button"
                type="button"
                disabled={selectedIngredients.length === 0 || loading}
              >
                {loading ? "Cooking..." : "Get Recipe"}
              </button>

              {errorMessage && <p className="error-text">{errorMessage}</p>}
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

function RecipePage({ recipe, onBack }) {
  return (
    <main className="recipe-page">
      <div className="recipe-page-header">
        <button type="button" className="secondary-button" onClick={onBack}>
          Back to Recipes
        </button>
      </div>

      {recipe ? (
        <RecipeDetail recipe={recipe} />
      ) : (
        <section className="empty-state">
          <h2>No recipe loaded</h2>
          <p>Go back, select ingredients, and click Get Recipe.</p>
        </section>
      )}
    </main>
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
      ) : (
        <section className="empty-state">
          <h2>No recipes found</h2>
          <p>Go back and try different vegetables.</p>
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
    if (path !== "/" && path !== "/recipes" && path !== "/recipe") {
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
        setErrorMessage("No recipe found for these ingredients.");
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
    if (recipeResults.length > 0) {
      navigate("/recipes");
      return;
    }
    navigate("/");
  };

  const handleSelectRecipe = (recipe) => {
    setSelectedRecipe(recipe);
    navigate("/recipe");
  };

  const handleBackToIngredients = () => {
    navigate("/");
  };

  return path === "/recipe" ? (
    <RecipePage recipe={selectedRecipe} onBack={handleBack} />
  ) : path === "/recipes" ? (
    <RecipesPage
      recipes={recipeResults}
      onSelectRecipe={handleSelectRecipe}
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
      errorMessage={errorMessage}
    />
  );
}

export default App;
