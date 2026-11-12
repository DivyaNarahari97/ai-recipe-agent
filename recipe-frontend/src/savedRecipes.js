// Favorites and history live in this browser only (no accounts yet).
// Recipes are stored as snapshots; saved recipes are never edited, so they don't go stale.
const FAVORITES_KEY = "recipe-assistant:favorites";
const HISTORY_KEY = "recipe-assistant:history";
const HISTORY_LIMIT = 20;

function read(key) {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(key) ?? "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function write(key, list) {
  try {
    window.localStorage.setItem(key, JSON.stringify(list));
  } catch {
    // Storage blocked (private mode, quota): the lists still work for this visit.
  }
}

export const loadFavorites = () => read(FAVORITES_KEY);
export const loadHistory = () => read(HISTORY_KEY);

// A refined recipe links to the version before it (for undo); don't store that whole chain.
// eslint-disable-next-line no-unused-vars
const snapshot = ({ previous, ...recipe }) => recipe;

export const isFavorite = (favorites, recipe) =>
  Boolean(recipe) && favorites.some((r) => r.id === recipe.id);

export function toggleFavorite(favorites, recipe) {
  const next = isFavorite(favorites, recipe)
    ? favorites.filter((r) => r.id !== recipe.id)
    : [snapshot(recipe), ...favorites];
  write(FAVORITES_KEY, next);
  return next;
}

export function addToHistory(history, recipe) {
  const next = [snapshot(recipe), ...history.filter((r) => r.id !== recipe.id)].slice(0, HISTORY_LIMIT);
  write(HISTORY_KEY, next);
  return next;
}

export function clearHistory() {
  write(HISTORY_KEY, []);
  return [];
}
