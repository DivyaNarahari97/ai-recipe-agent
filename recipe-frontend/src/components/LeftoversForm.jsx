import { useState } from "react";
import { API_BASE_URL } from "../config";

const EXAMPLES = ["half a roast chicken and rice", "leftover pasta and steamed broccoli", "dal and 3 rotis"];

// "I have half a roast chicken and rice" → a new dish built around them.
function LeftoversForm({ filters, onRecipeCreated }) {
  const [text, setText] = useState("");
  const [status, setStatus] = useState("idle"); // idle | loading | error
  const [error, setError] = useState("");

  const submit = async (event) => {
    event.preventDefault();
    if (!text.trim() || status === "loading") return;
    setStatus("loading");
    setError("");
    try {
      const res = await fetch(`${API_BASE_URL}/leftovers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ leftovers: text.trim(), filters }),
      });
      if (!res.ok) {
        // 400 and 422 explain themselves (no food found, diet clash, couldn't make a dish).
        const detail = res.status === 400 || res.status === 422 ? (await res.json().catch(() => ({}))).detail : "";
        throw new Error(
          (typeof detail === "string" && detail) || "Couldn't create a recipe right now. Check that Ollama is running."
        );
      }
      const data = await res.json();
      setStatus("idle");
      onRecipeCreated({ ...data.recipe, leftovers: data.leftovers, to_buy: data.to_buy });
    } catch (err) {
      console.error(err);
      setError(err.message);
      setStatus("error");
    }
  };

  return (
    <form className="craving-form leftovers-form" onSubmit={submit}>
      <label htmlFor="leftovers-input">Got leftovers? Turn them into something new</label>
      <div className="craving-row">
        <input
          id="leftovers-input"
          type="text"
          className="ingredient-input"
          placeholder="half a roast chicken and rice"
          value={text}
          maxLength={500}
          disabled={status === "loading"}
          onChange={(e) => setText(e.target.value)}
        />
        <button type="submit" className="secondary-button" disabled={!text.trim() || status === "loading"}>
          {status === "loading" ? "Cooking up…" : "Transform"}
        </button>
      </div>
      {status === "loading" ? (
        <p className="leftovers-hint" role="status">
          Building a new dish around your leftovers. This takes about a minute.
        </p>
      ) : (
        <div className="leftovers-examples">
          {EXAMPLES.map((example) => (
            <button key={example} type="button" className="leftovers-example" onClick={() => setText(example)}>
              {example}
            </button>
          ))}
        </div>
      )}
      {status === "error" && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}

export default LeftoversForm;
