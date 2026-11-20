// The pantry: what you own and when it expires. Kept in this browser (no accounts yet),
// like favorites. Dates are local calendar days ("2026-11-19"), not timestamps.

const PANTRY_KEY = "recipe-assistant:pantry";
const DAY_MS = 24 * 60 * 60 * 1000;
export const SOON_DAYS = 3;

export function todayISO(now = new Date()) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

const toUTC = (iso) => {
  const [y, m, d] = iso.split("-").map(Number);
  return Date.UTC(y, m - 1, d);
};

export function addDays(iso, days) {
  return new Date(toUTC(iso) + days * DAY_MS).toISOString().slice(0, 10);
}

/** Whole days from `today` until `expires`; negative once it's past; null without a date. */
export function daysLeft(expires, today) {
  if (!expires) return null;
  return Math.round((toUTC(expires) - toUTC(today)) / DAY_MS);
}

/** How to show an expiry: a label and a tone (expired | urgent | soon | week | fresh | none). */
export function expiryStatus(days) {
  if (days == null) return { label: "No date", tone: "none" };
  if (days < 0) return { label: days === -1 ? "Expired yesterday" : `Expired ${-days} days ago`, tone: "expired" };
  if (days === 0) return { label: "Expires today", tone: "urgent" };
  if (days === 1) return { label: "Tomorrow", tone: "urgent" };
  if (days <= SOON_DAYS) return { label: `In ${days} days`, tone: "soon" };
  if (days <= 7) return { label: `In ${days} days`, tone: "week" };
  return { label: `In ${days} days`, tone: "fresh" };
}

/** Expired first (they need a decision), then soonest, then undated A–Z. */
export function sortPantry(items, today) {
  const rank = (item) => {
    const days = daysLeft(item.expires, today);
    return days == null ? Infinity : days;
  };
  return [...items].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
}

const cleanName = (name) => String(name).trim().replace(/\s+/g, " ").toLowerCase();

const newId = () =>
  globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;

/**
 * Add names ("spinach, milk") with one expiry date. An item you already have keeps the
 * earlier date, since the older one goes off first.
 */
export function addToPantry(items, names, expires, today) {
  const next = [...items];
  for (const raw of names) {
    const name = cleanName(raw);
    if (!name) continue;
    const index = next.findIndex((item) => item.name === name);
    if (index === -1) {
      next.push({ id: newId(), name, expires: expires || null, added: today });
    } else if (expires && (!next[index].expires || expires < next[index].expires)) {
      next[index] = { ...next[index], expires };
    }
  }
  return next;
}

export function countExpiring(items, today, within = SOON_DAYS) {
  return items.filter((item) => {
    const days = daysLeft(item.expires, today);
    return days != null && days >= 0 && days <= within;
  }).length;
}

export function loadPantry() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(PANTRY_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((item) => item && typeof item.name === "string") : [];
  } catch {
    return [];
  }
}

export function savePantry(items) {
  try {
    window.localStorage.setItem(PANTRY_KEY, JSON.stringify(items));
  } catch {
    // Storage blocked (private mode, quota): the pantry still works for this visit.
  }
}
