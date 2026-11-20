import { test } from "node:test";
import assert from "node:assert/strict";
import { addDays, addToPantry, countExpiring, daysLeft, expiryStatus, sortPantry, todayISO } from "./pantry.js";

const TODAY = "2026-11-19";

test("todayISO uses the local calendar date", () => {
  assert.equal(todayISO(new Date(2026, 0, 5, 23, 30)), "2026-01-05");
});

test("addDays crosses months, years and DST changes", () => {
  assert.equal(addDays("2026-11-28", 3), "2026-12-01");
  assert.equal(addDays("2026-12-31", 1), "2027-01-01");
  assert.equal(addDays("2026-03-07", 2), "2026-03-09"); // US DST starts Mar 8
});

test("daysLeft counts calendar days", () => {
  assert.equal(daysLeft("2026-11-19", TODAY), 0);
  assert.equal(daysLeft("2026-11-20", TODAY), 1);
  assert.equal(daysLeft("2026-11-17", TODAY), -2);
  assert.equal(daysLeft(null, TODAY), null);
});

test("expiryStatus labels and tones", () => {
  assert.deepEqual(
    [-3, -1, 0, 1, 3, 5, 12, null].map((d) => expiryStatus(d).label),
    ["Expired 3 days ago", "Expired yesterday", "Expires today", "Tomorrow", "In 3 days", "In 5 days", "In 12 days", "No date"]
  );
  assert.deepEqual(
    [-1, 0, 1, 2, 3, 4, 7, 8, null].map((d) => expiryStatus(d).tone),
    ["expired", "urgent", "urgent", "soon", "soon", "week", "week", "fresh", "none"]
  );
});

test("sortPantry: expired, then soonest, then undated A–Z", () => {
  const items = [
    { name: "rice", expires: null },
    { name: "milk", expires: "2026-11-21" },
    { name: "beans", expires: null },
    { name: "yogurt", expires: "2026-11-18" },
    { name: "spinach", expires: "2026-11-20" },
  ];
  assert.deepEqual(sortPantry(items, TODAY).map((i) => i.name), ["yogurt", "spinach", "milk", "beans", "rice"]);
});

test("addToPantry cleans names and keeps the earlier date for an item you have", () => {
  let items = addToPantry([], [" Baby  Spinach ", "milk", ""], "2026-11-22", TODAY);
  assert.deepEqual(items.map((i) => [i.name, i.expires, i.added]), [
    ["baby spinach", "2026-11-22", TODAY],
    ["milk", "2026-11-22", TODAY],
  ]);
  items = addToPantry(items, ["milk"], "2026-11-20", TODAY); // older carton goes first
  items = addToPantry(items, ["baby spinach"], "2026-11-30", TODAY); // later date ignored
  items = addToPantry(items, ["rice"], null, TODAY);
  assert.deepEqual(items.map((i) => [i.name, i.expires]), [
    ["baby spinach", "2026-11-22"],
    ["milk", "2026-11-20"],
    ["rice", null],
  ]);
  assert.equal(new Set(items.map((i) => i.id)).size, 3);
});

test("countExpiring counts today through 3 days, not expired or undated", () => {
  const items = [
    { name: "a", expires: "2026-11-18" },
    { name: "b", expires: "2026-11-19" },
    { name: "c", expires: "2026-11-22" },
    { name: "d", expires: "2026-11-23" },
    { name: "e", expires: null },
  ];
  assert.equal(countExpiring(items, TODAY), 2);
});
