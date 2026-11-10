/** quickinsure-story-test.md — score the 5 features against agent-core + live /api/ask */
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
const optima = byId.get("hdfc-ergo-optima-secure-v08-2025-26-wording");

const feats = {
  1: { name: "Know exactly which product", checks: [] },
  2: { name: "Two ways to use it", checks: [] },
  3: { name: "Show the best 1 or 2", checks: [] },
  4: { name: "Simple vs hard answers", checks: [] },
  5: { name: "Close the sale + keep products up to date", checks: [] },
};
const add = (f, ok, msg, detail) => feats[f].checks.push({ ok: !!ok, msg, detail });

/* 1 — Optima */
{
  const m = C.matchProducts("Optima", cat.products, new Set());
  /* chat.js askWhich() shows at most 3 and says how many more match */
  const shown = m.slice(0, 3);
  const diffs = C.differences(shown);
  add(1, m.length >= 2, `Optima → ${m.length} matches, ${shown.length} shown (not one mixed answer)`);
  add(1, shown.length <= 3, "at most 3 options on screen");
  add(1, new Set(diffs.values()).size === shown.length, "each shown option has its own difference");
  add(1, [...diffs.values()].every((d) => String(d).length > 0), "each option has a difference line",
    shown.map((p) => `${C.fullName(p)} — ${diffs.get(p.id)}`).join("\n       "));
  add(1, m.every((p) => /optima/i.test(p.name + p.id)), "candidates are Optima-family only");
}

/* 2 — need / name / my insurers */
{
  const needQ = "My mother is 55 years old. She has diabetes. She has severe pain in her knees. waiting period more than 3 years. premium also low?";
  const need = C.parseNeed(needQ);
  add(2, C.isNeed(need, false), "need-first: mother case is a need", `age=${need.age} conditions=${(need.conditions||[]).join(",")}`);
  const nameM = C.matchProducts("Optima Secure V08", cat.products, new Set());
  add(2, nameM.length === 1 && /v08/i.test(nameM[0].id), "name-first: Optima Secure V08 → one product", nameM.map((p) => C.fullName(p)).join(", "));
  const mine = new Set(["ICICI Lombard"]);
  const sorted = [...cat.products].filter((p) => !C.isUpload(p))
    .sort((a, b) => (mine.has(b.insurer) ? 1 : 0) - (mine.has(a.insurer) ? 1 : 0) || (a.status === "withdrawn") - (b.status === "withdrawn"));
  add(2, mine.has(sorted[0].insurer), "My insurers ICICI Lombard sorts those first", sorted.slice(0, 3).map((p) => p.insurer).join(", "));
  add(2, !cat.products.some((p) => /max.?life/i.test(p.insurer + p.name)),
    "story Max Life / ICC check: Max Life removed (no health wording) — ICC/Elevate still present",
    cat.products.filter((p) => /icici|elevate/i.test(p.insurer + p.name)).map((p) => C.fullName(p)).join(", "));
}

/* 3 — ranking */
{
  const need = C.parseNeed(needQEnglish());
  const r = C.recommend(cat.products, need, new Set(), byId);
  const lines = C.needAnswer(need, r, "en").join("\n");
  const why = r.best ? C.whyLine(r.best, 1, r.best) : "";
  add(3, !!r.best && !!r.second, "best + second shown", `best=${label(r.best)} | second=${label(r.second)}`);
  add(3, /optima secure v08/i.test(label(r.best)), "best = Optima Secure V08", label(r.best));
  add(3, /healthprime|liberty/i.test(`${r.second?.product?.insurer || ""} ${label(r.second)}`),
    "second is Liberty HealthPrime Connect", `${r.second?.product?.insurer} ${label(r.second)}`);
  add(3, /11 November 2029/.test(lines), "diabetes cover date 11 November 2029");
  add(3, /36/.test(why) && /shortest wait/i.test(why) && /entry age is confirmed/i.test(why),
    "why-best: shortest confirmed wait — 36 months", why);
  add(3, !/\bthird\b|teesra|तीसरा/i.test(lines), "screen shows best + second only (no third)", lines);
  const needBudget = C.parseNeed(`${needQEnglish()} budget 20000`);
  const moneyLines = C.needAnswer(needBudget, C.recommend(cat.products, needBudget, new Set(), byId), "en").join("\n");
  add(3, /money was not compared|not compared/i.test(moneyLines),
    "money: with a ₹ budget, says not compared (no fake premium rank)",
    moneyLines.split("\n").filter((l) => /money|premium|compared/i.test(l)).join(" | "));
  add(3, (r.others || []).length > 0, "why-others present",
    (r.others || []).slice(0, 2).map((o) => `${label(o)}: ${o.reason || o.fails?.[0] || ""}`).join(" | "));
}

/* 4 — simple + hard */
{
  const wait = C.classify("What is the waiting time?");
  const room = C.classify("What is the room rent?");
  const age = C.classify("What is the age limit?");
  const prem = C.classify("How much will the premium be?");
  add(4, wait?.id === "ped-wait" && C.simpleAnswer(optima, "ped-wait")?.lead, "waiting time → fast PED answer", C.simpleAnswer(optima, "ped-wait")?.lead);
  add(4, room?.id === "room-rent" && /actual/i.test(C.simpleAnswer(optima, "room-rent")?.lead || ""), "room rent → at actuals", C.simpleAnswer(optima, "room-rent")?.lead);
  const ageA = C.simpleAnswer(optima, "entry-age");
  add(4, age?.id === "entry-age" && (ageA?.lead || ageA?.notWritten), "age limit → short answer or not-written", ageA?.lead || (ageA?.notWritten && "notWritten"));
  add(4, prem?.kind === "premium", "premium → premium path (not guessed)");
  const catH = C.hardFact(optima, "cataract");
  add(4, !!catH?.quote && /Excl02/i.test(catH.section || ""), "cataract: exact line + Code-Excl02", `${C.pageLabel(catH?.cite)} · ${catH?.section}`);
  add(4, /31/.test(C.pageLabel(catH?.cite) || ""), "cataract: PDF page 31", C.pageLabel(catH?.cite));
  add(4, /listed-illness|no separate money limit/i.test(catH?.plain || ""), "cataract: simple words", catH?.plain);
  add(4, C.hardFact(optima, "robotic-surgery")?.notWritten, "robotic: not written in V08");
  const ay = C.hardFact(optima, "ayush");
  add(4, !!ay?.quote || ay?.notWritten, "AYUSH: exact line or not-written", ay?.plain || (ay?.notWritten && "notWritten"));
}

/* 5 — close + stopped */
{
  const need = C.parseNeed("mother 55 diabetes knee pain");
  const kit = C.closeKit(optima, need, "en");
  const blob = JSON.stringify(kit);
  add(5, /11 November 2029/.test(blob), "close kit: diabetes / wait end 11 Nov 2029");
  add(5, /whatsapp/i.test(kit.labels?.wa || "") && /UIN|uin/.test(kit.whatsapp || ""), "WhatsApp message with UIN", (kit.whatsapp || "").slice(0, 220));
  add(5, (kit.papers || []).length > 0 && kit.papers.every((p) => p.cite), `papers from wording (${kit.papers.length}) with cites`);
  add(5, (kit.dont || []).some((d) => /premium/i.test(d.text)) && (kit.dont || []).some((d) => /pre-existing|diabetes|11 November 2029|PED/i.test(d.text)),
    "do-not-promise: PED/diabetes + premium");
  const nat = byId.get("national-mediclaim");
  const rep = byId.get(nat.replaced_by);
  add(5, nat.status === "withdrawn" && nat.withdrawn_on === "2024-04-01", "National Mediclaim STOPPED 1 Apr 2024");
  add(5, !rep, "National Mediclaim: no cross-company replacement", nat.stop_reason || "");
  const wrong = cat.products.filter((p) => p.replaced_by && byId.get(p.replaced_by)?.insurer !== p.insurer);
  add(5, wrong.length === 0, "every replacement is the same company's product",
    wrong.map((p) => `${p.id} → ${p.replaced_by}`).join(", "));
}

function needQEnglish() {
  return "My mother is 55 years old. She has diabetes. She has severe pain in her knees. We tried insurance before, but in all of them the waiting period for a pre-existing disease was more than 3 years. Is there a health insurance plan where I can put my mother, and the premium is also low?";
}
function label(a) {
  const p = a?.product || a;
  return p ? C.fullName(p) : "(none)";
}

async function liveRobotic() {
  const body = JSON.stringify({ question: "Is robotic surgery covered?", policy_id: C.policyIdOf(optima) });
  const t0 = Date.now();
  const resp = await fetch("http://127.0.0.1:8000/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body });
  const text = await resp.text();
  const finals = [...text.matchAll(/^data: ({.*})$/gm)].map((m) => JSON.parse(m[1])).filter((e) => e.type === "final");
  const f = finals.at(-1) || {};
  const ms = Date.now() - t0;
  add(4, f.status === "not_stated" || /not (written|stated)/i.test(f.answer || ""),
    "live robotic says not written/stated", `status=${f.status} ${ms}ms cached=${f.cached}`);
  add(4, ms < 3000, `live robotic under 3s (${ms}ms)`);
}

await liveRobotic();

console.log("\n=== quickinsure-story-test.md — 5 features ===\n");
for (const [id, f] of Object.entries(feats)) {
  const pass = f.checks.filter((c) => c.ok).length;
  const fail = f.checks.filter((c) => !c.ok).length;
  const verdict = fail === 0 ? "WORKS" : pass === 0 ? "FAIL" : "PARTIAL";
  console.log(`Feature ${id} — ${f.name}: ${verdict} (${pass}/${pass + fail})`);
  for (const c of f.checks) {
    console.log(`  ${c.ok ? "ok  " : "FAIL"} ${c.msg}${c.ok || !c.detail ? "" : `\n       ${String(c.detail).slice(0, 280)}`}`);
  }
  console.log("");
}
