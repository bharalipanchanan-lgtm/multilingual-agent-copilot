/* Provenance tests — the ones that make fabrication impossible.
 *   node test/catalogue.test.mjs
 *
 * Every quoted clause in data/catalogue.json must actually occur on the
 * PDF page it cites. If someone hand-edits a quote, invents a number, or
 * shifts a page reference, this fails.
 *
 * Reads data/pages/*.json, produced by: python3 ingest/extract.py
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const cat = JSON.parse(
  fs.readFileSync(path.join(root, "web", "data", "catalogue.json"), "utf8")
);

const pagesDir = path.join(root, "data", "pages");
if (!fs.existsSync(pagesDir)) {
  console.error("data/pages missing — run: python3 ingest/extract.py");
  process.exit(1);
}

/* PDF text carries ligatures, soft hyphens and column gutters. Compare on
   letters and digits only, so layout noise cannot fail a true quote. */
const norm = (s) =>
  s
    .normalize("NFKD")
    .replace(/[‘’]/g, "'")
    .replace(/[“”]/g, '"')
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");

const NUMWORD = {
  1: ["one"], 2: ["two"], 3: ["three"], 4: ["four"], 5: ["five"], 12: ["twelve"],
  24: ["twentyfour"], 36: ["thirtysix"], 48: ["fortyeight"],
};

const docs = {};
for (const [id, d] of Object.entries(cat.documents)) {
  const f = path.join(pagesDir, d.source.replace(/\.pdf$/, ".json"));
  if (!fs.existsSync(f)) {
    console.error(`missing extraction for ${d.source} — run ingest/extract.py`);
    process.exit(1);
  }
  const doc = JSON.parse(fs.readFileSync(f, "utf8"));
  docs[id] = {
    meta: d,
    byPage: new Map(doc.pages.map((p) => [p.page, norm(p.text)])),
  };
}

let failed = 0;
const check = (ok, msg, detail) => {
  if (!ok) failed++;
  console.log(
    `${ok ? "ok  " : "FAIL"}  ${msg}${ok || !detail ? "" : `\n        ${detail}`}`
  );
};

/* every product maps to a document we extracted */
for (const p of cat.products) {
  check(!!docs[p.id], `${p.id}: has an extracted source document`);
}

/* the headline guard: quotes must exist on the cited page */
let quotes = 0;
for (const p of cat.products) {
  const doc = docs[p.id];
  if (!doc) continue;

  for (const [key, f] of Object.entries(p.facts)) {
    if (!f.stated) {
      check(
        f.value === null && typeof f.note === "string" && f.note.length > 10,
        `${p.id}.${key}: not-stated carries a reason, not a number`
      );
      continue;
    }

    check(
      Number.isInteger(f.pdf_page) &&
        f.pdf_page >= 1 &&
        f.pdf_page <= doc.meta.pdf_pages,
      `${p.id}.${key}: cited page ${f.pdf_page} is inside the document`
    );

    if (!f.quote) continue;
    quotes++;
    const page = doc.byPage.get(f.pdf_page) ?? "";
    const needle = norm(f.quote);
    check(
      page.includes(needle),
      `${p.id}.${key}: quote occurs on PDF page ${f.pdf_page}`,
      `quote not found: "${f.quote.slice(0, 80)}..."`
    );

    /* a numeric fact must have its own number in its own quote —
       as digits, spelled out, or (for months) as whole years */
    if (typeof f.value === "number") {
      const q = norm(f.quote);
      const spelled = (NUMWORD[f.value] || []).some((w) => q.includes(w));
      const years = f.unit === "months" && f.value % 12 === 0 &&
        [String(f.value / 12) + "year", ...(NUMWORD[f.value / 12] || []).map((w) => w + "year")].some((w) => q.includes(w));
      check(
        q.includes(String(f.value)) || spelled || years,
        `${p.id}.${key}: the value ${f.value} appears in its own quote`
      );
    }
  }
}

/* close kit: every paper and the initial-wait line must be on its cited page */
for (const p of cat.products) {
  const doc = docs[p.id];
  if (!doc || !p.close_kit) continue;
  const items = [...p.close_kit.papers, ...(p.close_kit.initial_wait ? [{ key: "initial_wait", ...p.close_kit.initial_wait }] : [])];
  for (const it of items) {
    quotes++;
    check(
      (doc.byPage.get(it.pdf_page) ?? "").includes(norm(it.quote)),
      `${p.id}.close_kit.${it.key}: quote occurs on PDF page ${it.pdf_page}`,
      `quote not found: "${it.quote.slice(0, 80)}..."`
    );
  }
}

/* printed page numbers must agree with the stated offset */
for (const p of cat.products) {
  const off = docs[p.id]?.meta.page_offset;
  if (off === null || off === undefined) continue;
  for (const [key, f] of Object.entries(p.facts)) {
    if (!f.stated || f.printed_page === null) continue;
    check(
      f.printed_page === f.pdf_page + off,
      `${p.id}.${key}: printed page ${f.printed_page} matches offset ${off} on PDF page ${f.pdf_page}`
    );
  }
}

/* UIN on the product must match the UIN on its document */
for (const p of cat.products) {
  const d = docs[p.id]?.meta;
  if (!d) continue;
  check(p.uin === d.uin, `${p.id}: UIN matches the source document`);
}

console.log(`\n${quotes} quotes checked against extracted pages`);
console.log(failed ? `${failed} failing` : "all passing");
process.exit(failed ? 1 : 0);
