import { useState } from "react";
import RecipeDetail from "./components/RecipeDetail";

function App() {
  const [ingredients, setIngredients] = useState("");
  const [selectedRecipe, setSelectedRecipe] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSearch = async () => {
    const ingredientsArray = ingredients
      .split(",")
      .map(i => i.trim())
      .filter(i => i !== "");

    if (ingredientsArray.length === 0) {
      setSelectedRecipe(null);
      return;
    }

    try {
      setLoading(true);

      const response = await fetch("http://localhost:8000/assistant", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          ingredients: ingredientsArray
        })
      });

      const data = await response.json();

      if (data.results && data.results.length > 0) {
        setSelectedRecipe(data.results[0]);
      } else {
        setSelectedRecipe(null);
      }

    } catch (error) {
      console.error(error);
      setSelectedRecipe(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>

      {/* LEFT PANEL */}
  <div
    style={{
      width: "380px",        // fixed width
      padding: "40px",
      borderRight: "1px solid #ddd",
      backgroundColor: "#f4f4f4",
      height: "100vh",
      position: "sticky",
      top: 0
    }}
  >
        <h2>🔍 what do we have today?</h2>

        <input
          type="text"
          placeholder="what's up today"
          value={ingredients}
          onChange={(e) => {
            setIngredients(e.target.value);
            setSelectedRecipe(null); // clear when typing
          }}
          style={{
            width: "100%",
            padding: "12px",
            marginTop: "20px",
            borderRadius: "6px",
            border: "1px solid #ccc"
          }}
        />

        <button
          onClick={handleSearch}
          style={{
            marginTop: "20px",
            width: "100%",
            padding: "14px",
            backgroundColor: "#4CAF50",
            color: "white",
            border: "none",
            borderRadius: "6px",
            cursor: "pointer"
          }}
        >
          {loading ? "Loading..." : "Find Recipe"}
        </button>
      </div>

      {/* RIGHT PANEL */}
  <div
    style={{
      flex: 1,               // takes remaining space
      padding: "60px",
      backgroundColor: "#ffffff",
      minHeight: "100vh"
    }}
  >
        {selectedRecipe ? (
          <RecipeDetail recipe={selectedRecipe} />
        ) : (
          <h3 style={{ color: "gray" }}>
            Enter ingredients to see recipe
          </h3>
        )}
      </div>

    </div>
  );
}

export default App;
