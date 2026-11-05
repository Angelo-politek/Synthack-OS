// Audio CPU meter (src/cpu.ts) on the real budget.json (tools/build/budget.py): red over budget for any combination,
// with the measured profiles of budget.py ("every mod" is over: the site must warn, not block).

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { audioLoad, overBudget, type Budget } from "../src/cpu.ts";

const budget = JSON.parse(readFileSync(new URL("../src/budget.json", import.meta.url), "utf-8")) as Budget;
const every = Object.keys(budget.mods).filter((n) => n !== "mod-zero");

test("no mod: the stock load, not over", () => {
  const l = audioLoad(budget, []);
  assert.equal(l.cycles, 0);
  assert.equal(Math.round(l.percent), 89);
  assert.equal(l.over, false);
});

test("every mod together is over the budget and names the heaviest mods", () => {
  const l = audioLoad(budget, every);
  assert.ok(l.over, `${l.cycles} cycles`);
  assert.ok(l.percent > 95);
  assert.equal(l.heaviest[0], "fx3");
  const text = overBudget(l, (n) => n.toUpperCase());
  assert.match(text, /over budget/);
  assert.match(text, /FX3/);
});

test("a credit (negative cycles) lowers the load", () => {
  const fx3 = audioLoad(budget, ["fx3"]), both = audioLoad(budget, ["fx3", "fastmix"]);
  assert.ok(both.cycles < fx3.cycles);
  assert.ok(!both.heaviest.includes("fastmix"));
});

test("over exactly when the sum passes the limit, for any subset", () => {
  const names = every.filter((n) => budget.mods[n].cpu !== 0);
  for (let mask = 0; mask < 1 << names.length; mask++) {
    const pick = names.filter((_, i) => mask >> i & 1);
    const sum = pick.reduce((s, n) => s + budget.mods[n].cpu, 0);
    assert.equal(audioLoad(budget, pick).over, sum > budget.limits.cpu, pick.join("+"));
  }
});
