function RecipeDetail({ recipe }) {
  if (!recipe) return null;

  return (
    <div
      style={{
        maxWidth: "1000px",
        margin: "0 auto",
        paddingBottom: "60px"
      }}
    >

      {/* 🖼️ Image Section */}
      {recipe.image_url && (
        <img
          src={recipe.image_url}
          alt={recipe.name}
          style={{
            width: "100%",
            maxHeight: "450px",
            objectFit: "cover",
            borderRadius: "24px",
            marginBottom: "40px"
          }}
        />
      )}

      {/* Title */}
      <h1
        style={{
          fontSize: "42px",
          fontWeight: "700",
          marginBottom: "10px"
        }}
      >
        {recipe.name}
      </h1>

      {/* Meta Info */}
      <p
        style={{
          color: "#777",
          marginBottom: "40px",
          fontSize: "16px"
        }}
      >
        {recipe.servings && `${recipe.servings} servings`}
        {recipe.time && ` • ${recipe.time}`}
        {recipe.calories && ` • ${recipe.calories}`}
      </p>

      {/* Main Content Layout */}
      <div
        style={{
          display: "flex",
          gap: "60px",
          alignItems: "flex-start"
        }}
      >

        {/* Ingredients Section */}
        <div style={{ width: "40%" }}>
          <h2 style={{ marginBottom: "20px" }}>Ingredients</h2>

          {recipe.ingredients?.map((item, i) => (
            <div
              key={i}
              style={{
                marginBottom: "12px",
                lineHeight: "1.6"
              }}
            >
              ▢ {item.quantity} {item.name}
            </div>
          ))}
        </div>

        {/* Instructions Section */}
        <div style={{ width: "60%" }}>
          <h2 style={{ marginBottom: "20px" }}>Instructions</h2>

          {recipe.instructions?.map((section, i) => (
            <div key={i} style={{ marginBottom: "35px" }}>
              <h3 style={{ marginBottom: "10px" }}>
                {section.section}
              </h3>

              {section.steps?.map((step, j) => (
                <p
                  key={j}
                  style={{
                    marginBottom: "12px",
                    lineHeight: "1.8"
                  }}
                >
                  {step}
                </p>
              ))}
            </div>
          ))}

          {recipe.notes && (
            <div style={{ marginTop: "30px" }}>
              <h3>Notes</h3>
              <p style={{ lineHeight: "1.7" }}>{recipe.notes}</p>
            </div>
          )}
        </div>

      </div>

    </div>
  );
}

export default RecipeDetail;
