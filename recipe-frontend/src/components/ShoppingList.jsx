import { useState } from "react";
import { API_BASE_URL } from "../config";

const label = (item) => [item.quantity, item.name].filter(Boolean).join(" ");

function ShoppingList({ recipe, pantry }) {
  const [status, setStatus] = useState("idle"); // idle | loading | done | error
  const [items, setItems] = useState([]);
  const [copyMessage, setCopyMessage] = useState("");

  const buildList = async () => {
    setStatus("loading");
    try {
      const res = await fetch(`${API_BASE_URL}/recipes/${recipe.id}/shopping-list`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ have: pantry }),
      });
      if (!res.ok) {
        throw new Error(`Shopping list request failed: ${res.status}`);
      }
      const data = await res.json();
      setItems([
        ...data.need.map((item) => ({ ...item, have: false, staple: false })),
        ...data.have.map((item) => ({ ...item, have: true, staple: false })),
        ...data.staples.map((item) => ({ ...item, have: true, staple: true })),
      ]);
      setStatus("done");
    } catch (err) {
      console.error(err);
      setStatus("error");
    }
  };

  const toggle = (index) => {
    setCopyMessage("");
    setItems((prev) => prev.map((item, i) => (i === index ? { ...item, have: !item.have } : item)));
  };

  const toBuy = items.filter((item) => !item.have);

  const copyList = async () => {
    const text = [`Shopping list: ${recipe.name}`, ...toBuy.map((item) => `- ${label(item)}`)].join("\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopyMessage("Copied!");
    } catch {
      setCopyMessage("Couldn't copy. Select the list and copy it manually.");
    }
  };

  if (status !== "done") {
    return (
      <div className="shopping-list">
        <button
          type="button"
          className="shopping-button"
          onClick={buildList}
          disabled={status === "loading"}
        >
          {status === "loading" ? "Building list…" : "Make a shopping list"}
        </button>
        <p className="shopping-hint">
          {pantry.length > 0
            ? `Leaves out the ${pantry.length} ingredient${pantry.length === 1 ? "" : "s"} you picked.`
            : "Tick off what you already have."}
        </p>
        {status === "error" && <p className="shopping-hint">Couldn't build the list. Try again.</p>}
      </div>
    );
  }

  const renderItems = (have) =>
    items.map((item, index) =>
      item.have === have ? (
        <li key={`${item.name}-${index}`}>
          <label>
            <input type="checkbox" checked={item.have} onChange={() => toggle(index)} />
            {label(item)}
            {item.staple && <span className="shopping-staple"> (pantry staple)</span>}
          </label>
        </li>
      ) : null
    );

  return (
    <div className="shopping-list">
      <h3 className="shopping-heading">To buy ({toBuy.length})</h3>
      {toBuy.length > 0 ? (
        <ul className="shopping-items">{renderItems(false)}</ul>
      ) : (
        <p className="shopping-hint">You have everything for this recipe.</p>
      )}

      {items.length > toBuy.length && (
        <>
          <h3 className="shopping-heading">Already have</h3>
          <ul className="shopping-items is-have">{renderItems(true)}</ul>
        </>
      )}

      {toBuy.length > 0 && (
        <button type="button" className="shopping-button" onClick={copyList}>
          Copy list
        </button>
      )}
      {copyMessage && (
        <p className="shopping-hint" aria-live="polite">
          {copyMessage}
        </p>
      )}
    </div>
  );
}

export default ShoppingList;
