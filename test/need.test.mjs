/* Need parser + eligibility tests.
 *   node test/need.test.mjs
 *
 * Covers features 2 and 3: turning "mother 50, diabetes, room rent 10000"
 * into structured constraints, and picking a best and second choice with
 * a stated reason for every product that does not fit.
 *
 * As with router.test.mjs, the code under test is lifted out of the real
 * app.js by text markers, and cutMarkers throws if they move.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "..");
const src = fs.readFileSync(path.join(root, "web", "app.js"), "utf8");
const fixture = JSON.parse(
  fs.readFileSync(path.join(root, "web", "data", "catalogue.json"), "utf8")
);

function cutMarkers(start, end) {
  const a = src.indexOf(start);
  const b = src.indexOf(end);
  if (a === -1) throw new Error(`app.js: start marker not found: ${start}`);
  if (b === -1) throw new Error(`app.js: end marker not found: ${end}`);
  if (b <= a) throw new Error(`app.js: markers out of order: ${start} .. ${end}`);
  return src.slice(a, b);
}

const mod = new Function(
  "state",
  cutMarkers("const CONDITION_WORDS", "const el = {") +
    cutMarkers("const fullName =", "function fmtDate") +
    "; return { parseNeed, assess, recommend, whyBest };"
)({ products: fixture.products, myInsurers: new Set() });

const { parseNeed, assess, recommend } = mod;

let failed = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failed++;
  console.log(
    `${ok ? "ok  " : "FAIL"}  ${name}` +
      (ok ? "" : `\n        want ${JSON.stringify(want)}\n        got  ${JSON.stringify(got)}`)
  );
};

/* ── need parsing ──────────────────────────────────────── */

const n1 = parseNeed("mother 50, diabetes, room rent 10000");
check("age read from 'mother 50'", n1.age, 50);
check("diabetes detected", n1.conditions, ["diabetes"]);
check("room rent floor read", n1.roomRentMin, 10000);
check("no budget claimed when none given", n1.budgetMax, null);
check("flagged as a need query", n1.isNeedQuery, true);

const n2 = parseNeed("mother age 50 diabetes room rent 10k budget 25000");
check("10k expands to 10000", n2.roomRentMin, 10000);
check("budget read", n2.budgetMax, 25000);

const n3 = parseNeed("father 62, bp, budget 1.5 lakh");
check("age 62 read", n3.age, 62);
check("hypertension detected", n3.conditions, ["hypertension"]);
check("1.5 lakh expands", n3.budgetMax, 150000);

const n4 = parseNeed("optima restore");
check("a plain product name is not a need query", n4.isNeedQuery, false);

const n6 = parseNeed("star health 50");
check("bare number is not treated as an age", n6.age, null);

/* ── eligibility against the REAL catalogue ────────────── */

const byId = Object.fromEntries(fixture.products.map((p) => [p.id, p]));

/* premium is never in a policy wording: a budget must be reported as
   uncheckable, never silently ignored and never guessed */
const budget = assess(byId["care-supreme"], parseNeed("mother 50 budget 20000"));
check(
  "a budget is reported as uncheckable, not failed or passed",
  budget.cannotCheck.some((c) => /rate card/i.test(c)),
  true
);
check("a budget alone does not disqualify a product", budget.eligible, true);

/* entry age is not in these wordings either */
const age = assess(byId["hdfc-optima-secure"], parseNeed("father 70"));
check(
  "entry age is reported as uncheckable",
  age.cannotCheck.some((c) => /prospectus/i.test(c)),
  true
);

/* room rent: stated for Star, Policy-Schedule-dependent for HDFC */
const starRoom = assess(byId["star-family-health-optima"], parseNeed("mother 50 room rent 10000"));
check("Star room rent is stated and used", starRoom.wins.some((w) => /Room rent:/.test(w)), true);
const hdfcRoom = assess(byId["hdfc-optima-secure"], parseNeed("mother 50 room rent 10000"));
check(
  "HDFC room rent is deferred to the Policy Schedule",
  hdfcRoom.cannotCheck.some((c) => /Policy Schedule/i.test(c)),
  true
);

/* ranking uses the one value every wording states */
const need = parseNeed("mother 50, diabetes, room rent more than 10000");
const r = recommend(need);
check("a best fit is found", r.best !== null, true);
check("a second choice is found", r.second !== null, true);
check(
  "best has the shortest verified PED wait",
  r.best.product.facts.ped_wait_months.value <=
    r.second.product.facts.ped_wait_months.value,
  true
);
check(
  "Tata (24 months) outranks Care Supreme (48 months)",
  r.best.product.id,
  "tata-medicare-premier"
);

const nameOf = (a) => `${a.product.insurer} ${a.product.name}`;
console.log(`\nbest:     ${nameOf(r.best)} (PED ${r.best.product.facts.ped_wait_months.value}mo)`);
console.log(`second:   ${nameOf(r.second)} (PED ${r.second.product.facts.ped_wait_months.value}mo)`);

console.log(failed ? `\n${failed} failing` : "\nall passing");
process.exit(failed ? 1 : 0);
