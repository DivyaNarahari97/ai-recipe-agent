import { useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "../config";

const SUGGESTIONS = ["Make it for 6 people", "Spicier", "No oven", "Make it vegetarian", "Quicker"];

// Edit the recipe on screen ("spicier", "no oven"); each change builds on the last one.
function RefinePanel({ recipe, onRefined, onUndo }) {
  const [instruction, setInstruction] = useState("");
  const [pending, setPending] = useState("");
  const [error, setError] = useState("");
  // The recipe on screen; null once the panel is gone. A refine takes about a minute,
  // so drop its result if the user has moved on to another recipe or page by then.
  const shownId = useRef(recipe.id);

  useEffect(() => {
    shownId.current = recipe.id;
    return () => {
      shownId.current = null;
    };
  }, [recipe.id]);

  const refine = async (text) => {
    const change = text.trim();
    if (!change || pending) return;
    const sourceId = recipe.id;
    setPending(change);
    setError("");
    try {
      const res = await fetch(`${API_BASE_URL}/recipes/${recipe.id}/refine`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ instruction: change }),
      });
      if (!res.ok) {
        throw new Error(
          res.status === 422
            ? "The recipe came back unchanged. Try wording the change differently."
            : "Couldn't change the recipe right now. Check that Ollama is running."
        );
      }
      const data = await res.json();
      if (shownId.current !== sourceId) return;
      setInstruction("");
      onRefined(data.recipe, change);
    } catch (err) {
      console.error(err);
      setError(err.message);
    } finally {
      setPending("");
    }
  };

  return (
    <section className="refine-panel" aria-label="Change this recipe">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          refine(instruction);
        }}
      >
        <label htmlFor="refine-input">Change this recipe</label>
        <div className="craving-row">
          <input
            id="refine-input"
            type="text"
            className="ingredient-input"
            placeholder="make it for 6 people, no oven…"
            maxLength={300}
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            disabled={Boolean(pending)}
          />
          <button type="submit" className="secondary-button" disabled={!instruction.trim() || Boolean(pending)}>
            Apply
          </button>
        </div>
      </form>

      <div className="refine-suggestions">
        {SUGGESTIONS.map((text) => (
          <button
            key={text}
            type="button"
            className="refine-chip"
            onClick={() => refine(text)}
            disabled={Boolean(pending)}
          >
            {text}
          </button>
        ))}
      </div>

      <p className="refine-status" aria-live="polite">
        {pending && `Applying “${pending}”… this can take a minute.`}
        {!pending && error}
      </p>

      {recipe.refinements?.length > 0 && (
        <div className="refine-trail">
          <span>Changes: {recipe.refinements.join(" → ")}</span>
          {recipe.previous && (
            <button type="button" className="link-button" onClick={onUndo} disabled={Boolean(pending)}>
              Undo last change
            </button>
          )}
        </div>
      )}
    </section>
  );
}

export default RefinePanel;
