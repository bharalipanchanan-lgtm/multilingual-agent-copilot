/* No quote shown to an agent may be OCR noise.
 *   node test/quotes-readable.test.mjs
 *
 * Some PDFs carry an invisible OCR layer; pdftotext merges it into the real
 * text and a quote comes out as "r claim form, duIly completed Ou11"
 * (TATA AIG MediCare Plus, page 21). That still "occurs on the page", so the
 * provenance test passes it. This test checks the quote reads like words.
 * Same rule as garbled() in ingest/extract.py.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const cat = JSON.parse(fs.readFileSync(path.join(root, "web", "data", "catalogue.json"), "utf8"));

const JUNK = /^(?:[^aA&/*•\-–—\d\W]|[Il|]{2,}|\S*[a-z]I\S*|\S*[a-zA-Z]\d\S*|\S*\d(?!st|nd|rd|th)[a-zA-Z]\S*)$/;
const NOT_JUNK = /^(?:[ivxIVX]+|[A-Z]\d{1,3}|UIN\S*|[A-Z]{2,}\d\S*)$/;
function junkShare(q) {
  const toks = q.split(/\s+/)
    .filter((t) => !/^[A-Za-z0-9]{1,3}[.)]$/.test(t))   /* list markers "F." "ii)" "1)" */
    .map((t) => t.replace(/^[.,;:()'"]+|[.,;:()'"]+$/g, "")).filter(Boolean);
  if (toks.length < 5) return 0;
  return toks.filter((t) => JUNK.test(t) && !NOT_JUNK.test(t)).length / toks.length;
}

let fails = 0, n = 0;
for (const p of cat.products) {
  const quotes = [
    ...Object.entries(p.facts || {}).map(([k, f]) => [`facts.${k}`, f?.quote]),
    ...(p.close_kit?.papers || []).map((x) => [`close_kit.${x.key}`, x.quote]),
    ["close_kit.initial_wait", p.close_kit?.initial_wait?.quote],
  ];
  for (const [where, q] of quotes) {
    if (!q) continue;
    n++;
    const s = junkShare(q);
    if (s > 0.2) { fails++; console.log(`FAIL  ${p.id}.${where}: reads as OCR noise (${Math.round(s * 100)}%): "${q.slice(0, 90)}"`); }
  }
}
/* the case that started this */
const tata = cat.products.find((p) => p.id === "tata-aig-medicare-plus");
const cf = tata?.close_kit?.papers?.find((x) => x.key === "claim_form");
if (!cf || /Ou11|duIly/.test(cf.quote)) { fails++; console.log("FAIL  tata-aig-medicare-plus claim form quote is missing or still garbled"); }
/* tick-mark table cells never reach a quote */
for (const p of cat.products) for (const x of p.close_kit?.papers || []) {
  if (/[√×✓✗]/.test(x.quote || "")) { fails++; console.log(`FAIL  ${p.id}.close_kit.${x.key}: tick marks in quote`); }
}
console.log(`\n${n} quotes checked for readability\n${fails ? `${fails} failing` : "all passing"}`);
process.exit(fails ? 1 : 0);
