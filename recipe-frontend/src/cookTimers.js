// Finds cooking times in a recipe step ("simmer for 10-15 minutes") so cook mode can offer a timer.

const WORDS = {
  a: 1, an: 1, another: 1, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8,
  nine: 9, ten: 10, twelve: 12, fifteen: 15, twenty: 20, thirty: 30, forty: 40, "forty-five": 45,
  "half a": 0.5, "half an": 0.5,
};
const NUMBER = String.raw`(\d+\s+\d\/\d|\d\/\d|\d+(?:\.\d+)?|half an?|forty-five|${Object.keys(WORDS)
  .filter((w) => !w.startsWith("half") && w !== "forty-five")
  .join("|")})`;
const UNIT = String.raw`(hours?|hrs?|minutes?|mins?|seconds?|secs?)`;
const DURATION = new RegExp(
  String.raw`\b${NUMBER}(?:\s*(?:-|–|to)\s*${NUMBER})?[\s-]*${UNIT}\b`,
  "gi"
);
const PER_SIDE = /^\s*(?:per|on each|each) side/i;

const UNIT_SECONDS = { h: 3600, m: 60, s: 1 };
const MIN_SECONDS = 5;
const MAX_SECONDS = 24 * 3600;

function toNumber(text) {
  const value = text.toLowerCase().trim();
  if (value in WORDS) return WORDS[value];
  const mixed = value.match(/^(\d+)\s+(\d)\/(\d)$/);
  if (mixed) return Number(mixed[1]) + Number(mixed[2]) / Number(mixed[3]);
  const fraction = value.match(/^(\d)\/(\d)$/);
  if (fraction) return Number(fraction[1]) / Number(fraction[2]);
  return Number(value);
}

export function formatDuration(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.round(seconds % 60);
  return [h && `${h} hr`, m && `${m} min`, s && `${s} sec`].filter(Boolean).join(" ") || "0 sec";
}

// "10–15 min" rather than "10 min–15 min" when both ends use one unit.
function rangeLabel(low, high) {
  const a = formatDuration(low).split(" ");
  const b = formatDuration(high);
  return a.length === 2 && b.split(" ").length === 2 && b.endsWith(` ${a[1]}`)
    ? `${a[0]}–${b}`
    : `${a.join(" ")}–${b}`;
}

export function formatClock(seconds) {
  const total = Math.max(0, Math.ceil(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = String(total % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

/**
 * Durations in a step, in order: { start, end, seconds, label }.
 * A range ("10-15 minutes") times the shorter end, the usual "start checking" point.
 * "1 hour 30 minutes" is one duration; "per side" is kept in the label.
 */
export function findDurations(text) {
  const found = [];
  for (const match of text.matchAll(DURATION)) {
    const [whole, low, high, unit] = match;
    const scale = UNIT_SECONDS[unit[0].toLowerCase()];
    const lowSeconds = toNumber(low) * scale;
    const highSeconds = high ? toNumber(high) * scale : null;
    if (!Number.isFinite(lowSeconds) || (high && !Number.isFinite(highSeconds))) continue;

    const previous = found[found.length - 1];
    const between = previous ? text.slice(previous.end, match.index) : "";
    if (previous && !previous.range && previous.scale === 3600 && scale === 60 && !high
        && /^\s*(?:and\s*)?$/.test(between)) {
      previous.seconds += lowSeconds;
      previous.end = match.index + whole.length;
      previous.label = formatDuration(previous.seconds);
      continue;
    }

    found.push({
      start: match.index,
      end: match.index + whole.length,
      seconds: lowSeconds,
      scale,
      range: Boolean(high),
      label: high ? rangeLabel(lowSeconds, highSeconds) : formatDuration(lowSeconds),
    });
  }

  return found
    .filter((d) => d.seconds >= MIN_SECONDS && d.seconds <= MAX_SECONDS)
    .map(({ start, end, seconds, label }) => {
      const perSide = PER_SIDE.test(text.slice(end));
      return { start, end, seconds, label: perSide ? `${label} per side` : label };
    });
}
