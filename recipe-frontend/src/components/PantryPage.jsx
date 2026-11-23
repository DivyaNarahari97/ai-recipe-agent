import { useEffect, useState } from "react";
import { API_BASE_URL } from "../config";
import { addDays, addToPantry, daysLeft, expiryStatus, sortPantry, todayISO } from "../pantry";
import PhotoIngredients from "./PhotoIngredients";

const PRESETS = [
  { label: "Today", days: 0 },
  { label: "+3 days", days: 3 },
  { label: "+1 week", days: 7 },
  { label: "+2 weeks", days: 14 },
  { label: "No date", days: null },
];

const whenText = (days) => (days === 0 ? "today" : days === 1 ? "tomorrow" : `in ${days} days`);

function ExpiryBadge({ days }) {
  const { label, tone } = expiryStatus(days);
  return <span className={`pantry-badge is-${tone}`}>{label}</span>;
}

function UseItUpResults({ items, filters, profile, onSelectRecipe, onRecipeCreated }) {
  const today = todayISO();
  const request = JSON.stringify({
    items: items.map(({ name, expires }) => ({ name, expires })),
    today,
    filters,
  });
  // Which request the loaded results belong to; while it differs, we're loading.
  const [loaded, setLoaded] = useState({ key: null, data: null, error: "" });
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  useEffect(() => {
    let current = true;
    fetch(`${API_BASE_URL}/pantry/use-it-up`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: request,
    })
      .then((res) => {
        if (!res.ok) throw new Error(`Use it up request failed: ${res.status}`);
        return res.json();
      })
      .then((data) => current && setLoaded({ key: request, data, error: "" }))
      .catch((err) => {
        console.error(err);
        if (current) setLoaded({ key: request, data: null, error: "Couldn't load suggestions. Is the backend running?" });
      });
    return () => {
      current = false;
    };
  }, [request]);

  if (loaded.key !== request && !loaded.data) return <p className="pantry-status">Finding recipes…</p>;
  if (loaded.error) return <p className="error-text">{loaded.error}</p>;
  const { results, expiring, expired } = loaded.data;

  // Offer a new recipe when no stored one uses the item that expires first.
  const mostUrgent = expiring[0];
  const urgentCovered = mostUrgent && results.some((r) => r.uses_expiring.some((u) => u.name === mostUrgent.name));
  const generateWith = expiring.slice(0, 3).map((e) => e.name);

  const createRecipe = async () => {
    setCreating(true);
    setCreateError("");
    try {
      const res = await fetch(`${API_BASE_URL}/ai/generate-recipe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ingredients: generateWith, filters, profile }),
      });
      if (!res.ok) {
        // 422: every try used a food from the taste profile's avoid list.
        const detail = res.status === 422 ? (await res.json().catch(() => ({}))).detail : "";
        throw new Error(
          (typeof detail === "string" && detail) || "Couldn't create a recipe right now. Check that Ollama is running."
        );
      }
      onRecipeCreated(await res.json());
    } catch (err) {
      console.error(err);
      setCreateError(err.message);
      setCreating(false);
    }
  };

  return (
    <div className={`use-it-up-results${loaded.key !== request ? " is-refreshing" : ""}`} aria-busy={loaded.key !== request}>
      <p className="pantry-status">
        {expiring.length > 0
          ? `Expiring this week: ${expiring.map((e) => `${e.name} (${whenText(e.days_left)})`).join(", ")}.`
          : "Nothing expires this week, so these use the most of what you have."}
        {expired.length > 0 && ` Past their date and left out: ${expired.join(", ")}.`}
      </p>

      {mostUrgent && !urgentCovered && (
        <div className="use-it-up-create">
          <p className="pantry-status">
            None of our recipes use your {mostUrgent.name}.
          </p>
          <button type="button" className="secondary-button" onClick={createRecipe} disabled={creating}>
            {creating ? "Creating… (about 30 seconds)" : `Create a recipe with ${generateWith.join(", ")}`}
          </button>
          {createError && <p className="error-text">{createError}</p>}
        </div>
      )}

      {results.length === 0 ? (
        <p className="pantry-status">No stored recipes use what's in your pantry yet.</p>
      ) : (
        <ol className="use-it-up-list">
          {results.map((result) => (
            <li key={result.recipe.id}>
              <button
                type="button"
                className="use-it-up-card"
                onClick={() => onSelectRecipe({ ...result.recipe, use_it_up: result })}
              >
                <span className="use-it-up-name">{result.recipe.name}</span>
                {result.uses_expiring.length > 0 && (
                  <span className="use-it-up-expiring">
                    Uses up{" "}
                    {result.uses_expiring.map((u) => `${u.name} (${whenText(u.days_left)})`).join(", ")}
                  </span>
                )}
                <span className="use-it-up-meta">
                  {result.uses.length} from your pantry ·{" "}
                  {result.to_buy.length === 0 ? "nothing to buy" : `${result.to_buy.length} to buy`}
                  {result.recipe.time && ` · ${result.recipe.time}`}
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function PantryPage({
  items,
  onChange,
  filters,
  profile,
  useItUp,
  onUseItUpChange,
  onSelectRecipe,
  onRecipeCreated,
  onBackToIngredients,
}) {
  const today = todayISO();
  const [names, setNames] = useState("");
  const [expires, setExpires] = useState(addDays(today, 7));
  const [photoAdded, setPhotoAdded] = useState("");

  const add = (list) => onChange(addToPantry(items, list, expires, today));
  const submit = (event) => {
    event.preventDefault();
    const list = names.split(/[,\n]/).map((n) => n.trim()).filter(Boolean);
    if (list.length === 0) return;
    add(list);
    setNames("");
  };
  const update = (id, changes) => onChange(items.map((item) => (item.id === id ? { ...item, ...changes } : item)));
  const remove = (id) => onChange(items.filter((item) => item.id !== id));

  const sorted = sortPantry(items, today);
  const usable = items.filter((item) => (daysLeft(item.expires, today) ?? 0) >= 0);

  return (
    <main className="recipes-list-page pantry-page">
      <div className="recipes-list-header">
        <button type="button" className="secondary-button" onClick={onBackToIngredients}>
          Back to Ingredients
        </button>
        <h1 className="browse-title">Your pantry</h1>
        <p className="browse-status">Saved in this browser. Add dates to get “use it up first” suggestions.</p>
      </div>

      <section className="pantry-panel">
        <form className="pantry-add" onSubmit={submit}>
          <label htmlFor="pantry-names">Add items</label>
          <div className="pantry-add-row">
            <input
              id="pantry-names"
              type="text"
              className="ingredient-input"
              placeholder="spinach, milk, chicken thighs"
              value={names}
              onChange={(e) => setNames(e.target.value)}
            />
            <button type="submit" className="secondary-button" disabled={!names.trim()}>
              Add
            </button>
          </div>
          <div className="pantry-expiry-row">
            <label htmlFor="pantry-expires">Expires</label>
            <input
              id="pantry-expires"
              type="date"
              value={expires || ""}
              min={addDays(today, -30)}
              onChange={(e) => setExpires(e.target.value || null)}
            />
            <div className="pantry-presets" role="group" aria-label="Expiry presets">
              {PRESETS.map((preset) => {
                const value = preset.days == null ? null : addDays(today, preset.days);
                return (
                  <button
                    key={preset.label}
                    type="button"
                    className={`pantry-preset${expires === value ? " is-active" : ""}`}
                    aria-pressed={expires === value}
                    onClick={() => setExpires(value)}
                  >
                    {preset.label}
                  </button>
                );
              })}
            </div>
          </div>
        </form>
        <PhotoIngredients
          onFound={(found) => {
            add(found);
            setPhotoAdded(`Added ${found.length} from the photo. Check them and their dates below.`);
          }}
        />
        {photoAdded && (
          <p className="pantry-status" role="status">
            {photoAdded}
          </p>
        )}
      </section>

      {sorted.length === 0 ? (
        <section className="empty-state saved-empty">
          <p>Your pantry is empty. Add what you have above.</p>
        </section>
      ) : (
        <section className="pantry-panel">
          <h2 className="pantry-heading">
            {items.length} item{items.length === 1 ? "" : "s"}
          </h2>
          <ul className="pantry-list">
            {sorted.map((item) => {
              const days = daysLeft(item.expires, today);
              return (
                <li key={item.id} className={`pantry-item is-${expiryStatus(days).tone}`}>
                  <span className="pantry-name">{item.name}</span>
                  <ExpiryBadge days={days} />
                  <input
                    type="date"
                    aria-label={`Expiry date for ${item.name}`}
                    value={item.expires || ""}
                    onChange={(e) => update(item.id, { expires: e.target.value || null })}
                  />
                  <button
                    type="button"
                    className="pantry-remove"
                    aria-label={`Remove ${item.name}`}
                    onClick={() => remove(item.id)}
                  >
                    {days != null && days < 0 ? "Throw out" : "Used it"}
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <section className="pantry-panel">
        <div className="use-it-up-header">
          <h2 className="pantry-heading">Use it up first</h2>
          <button
            type="button"
            className={`use-it-up-toggle${useItUp ? " is-active" : ""}`}
            aria-pressed={useItUp}
            disabled={usable.length === 0}
            onClick={() => onUseItUpChange(!useItUp)}
          >
            {useItUp ? "On" : "Off"}
          </button>
        </div>
        {usable.length === 0 ? (
          <p className="pantry-status">Add items you have (not expired) to get suggestions.</p>
        ) : useItUp ? (
          <UseItUpResults
            items={items}
            filters={filters}
            profile={profile}
            onSelectRecipe={onSelectRecipe}
            onRecipeCreated={onRecipeCreated}
          />
        ) : (
          <p className="pantry-status">Turn on to see recipes that use what expires soonest.</p>
        )}
      </section>
    </main>
  );
}

export default PantryPage;
