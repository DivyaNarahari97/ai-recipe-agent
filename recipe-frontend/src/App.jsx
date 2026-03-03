import { useState, useEffect } from "react";
import RecipeDetail from "./components/RecipeDetail";

function IngredientImage({ name }) {
  const [imageUrl, setImageUrl] = useState(null);

  useEffect(() => {
    const fetchImage = async () => {
      try {
        const res = await fetch(
          `http://localhost:8000/ingredient-image?name=${name}`
        );
        const data = await res.json();
        setImageUrl(data.image_url);
      } catch (err) {
        console.error("Image fetch error:", err);
        setImageUrl(null);
      }
    };

    fetchImage();
  }, [name]);

  return (
    <img
      src={imageUrl || "https://via.placeholder.com/80"}
      alt={name}
      style={{
        width: "80px",
        height: "80px",
        objectFit: "cover",
        borderRadius: "12px",
        marginBottom: "8px"
      }}
    />
  );
}

function App() {
  const [ingredientsInput, setIngredientsInput] = useState("");
  const [allIngredients, setAllIngredients] = useState([]);
  const [selectedIngredients, setSelectedIngredients] = useState([]);
  const [selectedRecipe, setSelectedRecipe] = useState(null);
  const [loading, setLoading] = useState(false);

  const createTiles = () => {
    const parsed = ingredientsInput
      .split(",")
      .map(i => i.trim().toLowerCase())
      .filter(i => i !== "");

    setAllIngredients(parsed);
    setSelectedIngredients([]);
    setSelectedRecipe(null);
  };

  const toggleIngredient = (ingredient) => {
    if (selectedIngredients.includes(ingredient)) {
      setSelectedIngredients(
        selectedIngredients.filter(i => i !== ingredient)
      );
    } else {
      setSelectedIngredients([...selectedIngredients, ingredient]);
    }
  };

  const handleSearch = async () => {
    if (selectedIngredients.length === 0) return;

    try {
      setLoading(true);

      const response = await fetch("http://localhost:8000/assistant", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          ingredients: selectedIngredients
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
          width: "380px",
          padding: "40px",
          borderRight: "1px solid #ddd",
          backgroundColor: "#f4f4f4",
          height: "100vh",
          position: "sticky",
          top: 0,
          overflowY: "auto"
        }}
      >
        <h2>🔍 What do we have today?</h2>

        <input
          type="text"
          placeholder="Enter ingredients separated by commas"
          value={ingredientsInput}
          onChange={(e) => {
            setIngredientsInput(e.target.value);
            setSelectedRecipe(null);
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
          onClick={createTiles}
          style={{
            marginTop: "15px",
            width: "100%",
            padding: "12px",
            backgroundColor: "#4CAF50",
            color: "white",
            border: "none",
            borderRadius: "6px",
            cursor: "pointer"
          }}
        >
          Create Tiles
        </button>

        {allIngredients.length > 0 && (
          <>
            <h3 style={{ marginTop: "30px" }}>
              Select Ingredients
            </h3>

            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: "15px",
                marginTop: "20px"
              }}
            >
              {allIngredients.map((item, index) => {
                const isSelected = selectedIngredients.includes(item);

                return (
                  <div
                    key={index}
                    onClick={() => toggleIngredient(item)}
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      padding: "12px",
                      borderRadius: "15px",
                      cursor: "pointer",
                      backgroundColor: isSelected
                        ? "#4CAF50"
                        : "#f0f0f0",
                      color: isSelected ? "white" : "#333",
                      width: "110px",
                      transition: "0.3s"
                    }}
                  >
                    <IngredientImage name={item} />

                    <span
                      style={{
                        fontSize: "14px",
                        textAlign: "center"
                      }}
                    >
                      {item}
                    </span>
                  </div>
                );
              })}
            </div>
          </>
        )}

        {selectedIngredients.length > 0 && (
          <button
            onClick={handleSearch}
            style={{
              marginTop: "30px",
              width: "100%",
              padding: "14px",
              backgroundColor: "#2e7d32",
              color: "white",
              border: "none",
              borderRadius: "6px",
              cursor: "pointer"
            }}
          >
            {loading ? "Cooking..." : "Generate Recipe"}
          </button>
        )}
      </div>

      {/* RIGHT PANEL */}
      <div
        style={{
          flex: 1,
          padding: "60px",
          backgroundColor: "#ffffff",
          minHeight: "100vh"
        }}
      >
        {loading ? (
          <h3 style={{ color: "#777" }}>
            AI is preparing your recipe...
          </h3>
        ) : selectedRecipe ? (
          <RecipeDetail recipe={selectedRecipe} />
        ) : (
          <h3 style={{ color: "gray" }}>
            Enter ingredients and create tiles to begin
          </h3>
        )}
      </div>

    </div>
  );
}

export default App;
