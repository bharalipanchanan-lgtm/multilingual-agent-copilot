/* Chat agent answers — the claims the chat shows must agree with each other
 * and with the wording.
 *   node test/agent.test.mjs
 *
 * Loads web/agent-core.js (window.QPCore) against the real catalogue.
 */

import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const cat = JSON.parse(fs.readFileSync(path.join(root, "web", "data", "catalogue.json"), "utf8"));
const ctx = { window: {}, console };
vm.runInNewContext(fs.readFileSync(path.join(root, "web", "agent-core.js"), "utf8"), ctx);
const C = ctx.window.QPCore;
const byId = new Map(cat.products.map((p) => [p.id, p]));

let failed = 0;
const check = (ok, msg, detail) => {
  if (!ok) failed++;
  console.log(`${ok ? "ok  " : "FAIL"}  ${msg}${ok || !detail ? "" : `\n        ${detail}`}`);
};

/* one "shortest wait" claim per screen */
const mother = "meri ma 55 years ki hai. unhe diabetes hai. unke ghutne meh bohot jyada dard rehta hai. pre existing ka waiting 3 saal se jyada tha. pese bhi kam lage";
const need = C.parseNeed(mother);
const r = C.recommend(cat.products, need, new Set(), byId);
const lang = C.detectLang(mother);
const screen = [
  ...C.needAnswer(need, r, lang),
  ...[r.best, r.second, r.third].filter(Boolean).map((a, i) => C.whyLine(a, i + 1, r.best)),
].join("\n");
const shorterUnranked = cat.products.some((p) => {
  const a = C.assess(p, need, byId);
  return a.eligible && a.ageUnknown && r.best && a.pedMonths < r.best.pedMonths;
});
check(!!r.best, "mother case: a best plan is ranked");
if (shorterUnranked) {
  check(/entry age is confirmed from the wording/.test(C.whyLine(r.best, 1, r.best)),
    "mother case: best is labelled shortest only among age-confirmed plans", C.whyLine(r.best, 1, r.best));
  check(!/Shortest pre-existing wait of the plans that fit/.test(screen),
    "mother case: no unqualified 'shortest' claim while a shorter unranked plan is shown");
}
check(/compare nahi|not compared|तुलना नहीं/i.test(screen), "budget need: says money was not compared", screen);

/* cataract hard answer carries its rule number */
const optima = byId.get("hdfc-ergo-optima-secure-v08-2025-26-wording");
const cq = C.classify("cataract limit kya hai");
const h = C.hardFact(optima, cq.id);
check(cq.id === "cataract", "cataract question routes to the cataract fact");
check(!!h?.section && /Excl02/.test(h.section), "Optima Secure V08 cataract shows its section / rule number", h?.section);
check(!!h?.quote && !!h?.cite && !!h?.plain, "Optima Secure V08 cataract has exact line, page and simple words");

/* every stated hard fact names its clause */
for (const p of cat.products) {
  for (const k of ["cataract", "ayush", "robotic_surgery"]) {
    const f = p.facts?.[k];
    if (f?.stated && !f.section) check(false, `${p.id}.${k}: has a section / rule number`);
  }
}

/* close kit is built from each product's own wording */
const a = C.closeKit(byId.get("care-health-care-freedom"), need, "en");
const b = C.closeKit(byId.get("star-family-health-optima"), need, "en");
const sig = (k) => JSON.stringify([k.papers.map((x) => x.text), k.dont.map((x) => x.text)]);
check(sig(a) !== sig(b), "close kit differs between two products");
for (const [name, k] of [["care-health-care-freedom", a], ["star-family-health-optima", b]]) {
  check(k.papers.length > 0 && k.papers.every((x) => x.cite && x.quote), `${name}: every paper cites its wording page`);
  check(k.dont.filter((x) => !/premium/i.test(x.text)).every((x) => x.cite), `${name}: every do-not-promise line cites its wording page`);
}

console.log(failed ? `\n${failed} failing` : "\nall passing");
process.exit(failed ? 1 : 0);
