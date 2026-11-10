/* Intent router tests.
 *   node test/router.test.mjs
 *
 * Why this file exists: "premium kitna hoga" once returned "24 months".
 * `kitna` was listed as a waiting-period keyword, it tied with `premium`
 * at one hit each, and array order broke the tie the wrong way — a
 * question that must be refused came back with a confident number.
 *
 * app.js is a browser script with no module system, so the router is
 * lifted out of the real source by text markers rather than imported.
 * That keeps the test honest (it runs the shipped code, not a copy) but
 * it is brittle: if the markers move, cutMarkers throws instead of
 * silently testing nothing.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const APP = path.join(here, "..", "web", "app.js");
const src = fs.readFileSync(APP, "utf8");

function cutMarkers(start, end) {
  const a = src.indexOf(start);
  const b = src.indexOf(end);
  if (a === -1) throw new Error(`app.js: start marker not found: ${start}`);
  if (b === -1) throw new Error(`app.js: end marker not found: ${end}`);
  if (b <= a) throw new Error(`app.js: markers out of order: ${start} .. ${end}`);
  return src.slice(a, b);
}

const classify = new Function(
  cutMarkers("const STOPWORDS", "const el = {") +
    cutMarkers("const tokens =", "function fmtDate") +
    cutMarkers("function classify(q)", "/* Feature 3/5") +
    "; return classify;"
)();

/* [question, expected intent id or null] */
const CASES = [
  // out of scope — must never return a number
  ["premium kitna hoga", "premium"],
  ["Premium kitna hoga?", "premium"],
  ["what is the price", "premium"],
  ["iska cost kya hai", "premium"],

  // fast path, from the structured fact table
  ["diabetes ka waiting period kitna hai", "ped-wait"],
  ["waiting period kitna hai", "ped-wait"],
  ["sugar ki waiting", "ped-wait"],
  ["room rent kitna milega", "room-rent"],
  ["icu charges", "room-rent"],
  ["max entry age", "entry-age"],
  ["umar ki limit", "entry-age"],
  ["copay kitna hai", "copay"],

  // cited path, must reach a clause lookup
  ["is robotic surgery covered", "robotic-surgery"],
  ["robotic surgery ka limit", "robotic-surgery"],
  ["cataract limit", "cataract"],
  ["motiyabind cover hai", "cataract"],
  ["ayush cover hai kya", "ayush"],
  ["ayurveda treatment", "ayush"],

  // nothing to go on
  ["who won the cricket match", null],
  ["hello", null],
  ["", null],
];

let failed = 0;
for (const [q, want] of CASES) {
  const got = classify(q)?.id ?? null;
  const ok = got === want;
  if (!ok) failed++;
  console.log(
    `${ok ? "ok  " : "FAIL"}  ${JSON.stringify(q).padEnd(40)} want=${want}  got=${got}`
  );
}

console.log(
  failed
    ? `\n${failed} of ${CASES.length} failing`
    : `\nall ${CASES.length} passing`
);
process.exit(failed ? 1 : 0);
