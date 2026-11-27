#!/usr/bin/env node
// Node fallback for server.py (use only when Python 3 is missing). Same endpoints and files.
//   node server.mjs [--port 8765] [--no-open] [--page results]
// Document check: dataset + curated rules (ported from doc_check.py). The small-model step runs only
// through server.py; here unanswered questions are listed as "pending" for the agent to ask in chat.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import zlib from "node:zlib";
import { exec } from "node:child_process";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ASSETS = path.join(HERE, "..", "assets"), FORM = path.join(ASSETS, "form"), DATA = path.join(ASSETS, "data");
const STATE = process.env.FAIR_FARES_HOME || path.join(os.homedir(), ".fair-fares");
fs.mkdirSync(STATE, { recursive: true });
const rj = (p, d = null) => { try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return d; } };
const wj = (p, o) => { fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p + ".tmp", JSON.stringify(o, null, 1)); fs.renameSync(p + ".tmp", p); };
const now = () => new Date().toISOString().slice(0, 19);
const currentRun = () => rj(path.join(STATE, "current_run.json"), {})?.path || null;
const EVENTS = path.join(STATE, "events.jsonl");
function emit(type, data) {
  const n = fs.existsSync(EVENTS) ? fs.readFileSync(EVENTS, "utf8").split("\n").filter(Boolean).length : 0;
  const ev = { id: n + 1, type, at: now(), data };
  fs.appendFileSync(EVENTS, JSON.stringify(ev) + "\n");
  return ev;
}

// ---- document check (dataset + rules) ----
const visa = rj(path.join(DATA, "visa.json"), {}), rules = rj(path.join(DATA, "doc_rules.json"), {});
const names = Object.fromEntries((rj(path.join(DATA, "countries.json"), []) || []).map((c) => [c[0], c[1]]));
const RANK = { SELF: 0, VF: 1, ETA: 2, VOA: 3, EV: 4, VR: 5, NA: 6 };
const LABEL = { SELF: "Own country", VF: "Visa-free", ETA: "Electronic travel authorisation needed", VOA: "Visa on arrival", EV: "e-Visa needed", VR: "Visa required", NA: "No admission" };
const schengen = rules.groups?.SCHENGEN || [];
const ruleFor = (d) => rules.destinations?.[d] ? [d, rules.destinations[d]] : schengen.includes(d) ? ["SCHENGEN", rules.destinations.SCHENGEN] : [null, null];
const matches = (c, d) => c && (c === d || (c === "SCHENGEN" && schengen.includes(d)));
const catalog = Object.fromEntries((rules.catalog || []).map((c) => [c.id, c]));
function destDocs(dest, kids) {
  const [key, rule] = ruleFor(dest), out = [], seen = new Set();
  for (const d of rule?.documents || []) { out.push({ id: d.id, label: d.label, source: "rules" }); seen.add(d.id); }
  for (const c of rules.catalog || []) if (!seen.has(c.id) && matches(c.country, dest)) { out.push({ id: c.id, label: c.label, source: "catalog" }); seen.add(c.id); }
  if (!out.some((o) => o.id.endsWith("passport"))) out.push({ id: dest.toLowerCase() + "_passport", label: `${names[dest] || dest} passport`, source: "generic" });
  if (rule?.onward_travel) out.push({ id: "onward_ticket", label: "Proof of onward travel", source: "rules" });
  if (kids) out.push({ id: "child_consent", label: "Child travel consent letter", source: "generic" });
  return { destination: dest, rules_key: key, documents: out, covered_by_rules: !!rule, model: rule ? undefined : "unavailable" };
}
const addMonths = (d, m) => { const x = new Date(d); x.setMonth(x.getMonth() + m); return x; };
function docCheck(req) {
  const dest = req.destination, [, rule] = ruleFor(dest), items = [], pending = [];
  const dep = new Date(req.earliest_departure || Date.now()), ret = new Date(req.return_by || dep);
  const daysLeft = Math.round((dep - Date.now()) / 864e5);
  const held = {}; for (const d of req.documents || []) for (const t of d.applies_to || []) (held[t] ||= new Set()).add(d.id);
  const rdocs = Object.fromEntries((rule?.documents || []).map((d) => [d.id, d]));
  const add = (t, doc_id, label, status, source, doc = {}, note = "") => {
    const it = { traveller: t.id, traveller_name: t.name || t.id, doc_id, label, status, source, note: note || doc.note || "", fee: doc.fee || null, processing_days: doc.processing_days || null, official: doc.official || rule?.official?.[0] || null };
    if (status !== "OK" && doc.processing_days && doc.processing_days[1] + (doc.apply_before_days || 0) >= daysLeft) it.warning = `Processing can take up to ${doc.processing_days[1]} days; your earliest departure is in ${daysLeft} days.`;
    items.push(it);
  };
  for (const t of req.travellers || []) {
    const pps = (t.passports || []).filter((p) => p.country), mine = held[t.id] || new Set();
    if (!pps.length) { add(t, "passport", "Passport", "Missing", "form", {}, "Add a passport country."); continue; }
    let best = null;
    for (const p of pps) { let v = visa[p.country]?.[dest] ?? (p.country === dest ? "SELF" : "UNKNOWN"); const days = typeof v === "number" ? v : null; if (days) v = "VF"; const c = [RANK[v] ?? 9, v, days, p]; if (!best || c[0] < best[0]) best = c; }
    const [, s, days, p] = best, months = rule?.passport_validity_months ?? rules.generic.passport_validity_months, exp = p.expiry ? new Date(p.expiry) : null;
    if (s !== "SELF") {
      if (!exp) add(t, "passport_validity", "Passport validity", "At risk", "rules", {}, "Add the expiry date.");
      else if (exp < ret) add(t, "passport_validity", "Passport expires before you're back", "Missing", "rules", { processing_days: [10, 42] }, `Expires ${p.expiry}; renew before travel.`);
      else if (months && exp < addMonths(ret, months)) add(t, "passport_validity", "Passport validity", "At risk", "rules", { processing_days: [10, 42] }, `Expires ${p.expiry}; ${months} months beyond the return date is usually required.`);
      else add(t, "passport_validity", "Passport validity", "OK", "rules", {}, `Valid until ${p.expiry}.`);
    }
    const base = `${LABEL[s] || s}${days ? ` (${days} days)` : ""} with ${names[p.country] || p.country} passport`;
    const replaced = [...mine].filter((d) => rdocs[d]?.replaces_visa || (catalog[d]?.kind === "residence" && matches(catalog[d].country, dest)));
    if (s === "SELF") add(t, "entry", "Entry as citizen", "OK", "dataset", {}, base);
    else if (replaced.length) add(t, "entry", "Entry", "OK", "rules", {}, `Covered by ${(rdocs[replaced[0]] || catalog[replaced[0]] || {}).label}. Dataset says: ${base}.`);
    else if (s === "NA") add(t, "entry", "Entry", "Missing", "dataset", {}, base);
    else if (s === "UNKNOWN") pending.push({ traveller: t.id, question: "entry status" });
    else {
      const need = Object.values(rdocs).find((d) => (d.for_status || []).includes(s) || (["VR", "EV", "VOA"].includes(s) && d.visa_doc));
      if (need) add(t, need.id, need.label, mine.has(need.id) ? "OK" : ["VR", "EV", "ETA"].includes(s) ? "Missing" : "At risk", "rules", need, base);
      else if (s === "VF") add(t, "entry", "Entry", "OK", "dataset", {}, base);
      else { add(t, "entry", LABEL[s], s === "VOA" ? "At risk" : "Missing", "dataset", {}, base); pending.push({ traveller: t.id, question: `${LABEL[s]}: fee and processing time` }); }
    }
    for (const d of mine) if (!rdocs[d] && !catalog[d] && d !== "child_consent") pending.push({ traveller: t.id, question: `effect of document '${d}'` });
    if (t.child && (rule?.child_consent || !rule)) add(t, "child_consent", rules.generic.child_consent.label, mine.has("child_consent") ? "OK" : "At risk", "rules", rules.generic.child_consent, rule?.child_note || "Needed if the child travels without both parents or guardians.");
  }
  if (!rule) for (const t of req.travellers || []) if (!pending.some((x) => x.traveller === t.id)) pending.push({ traveller: t.id, question: "other entry requirements (e-arrival cards, fees, onward ticket)" });
  return { items, pending, model_status: pending.length ? "no_model" : "not_needed", visa_dataset_date: rj(path.join(DATA, "meta.json"), {})?.datasets?.visa?.date, checked_at: now(), agent: rj(path.join(STATE, "config.json"), {})?.agent };
}

// ---- http ----
const TYPES = { ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8" };
function send(req, res, code, body, type = "application/json; charset=utf-8") {
  let buf = Buffer.isBuffer(body) ? body : Buffer.from(typeof body === "string" ? body : JSON.stringify(body));
  const h = { "Content-Type": type, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" };
  if (/gzip/.test(req.headers["accept-encoding"] || "") && buf.length > 2048) { buf = zlib.gzipSync(buf); h["Content-Encoding"] = "gzip"; }
  h["Content-Length"] = buf.length; res.writeHead(code, h); res.end(buf);
}
function file(req, res, root, rel) {
  const p = path.resolve(root, rel);
  if (!p.startsWith(path.resolve(root)) || !fs.existsSync(p) || !fs.statSync(p).isFile()) return send(req, res, 404, { error: "not found" });
  send(req, res, 200, fs.readFileSync(p), TYPES[path.extname(p)] || "application/octet-stream");
}
const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, "http://127.0.0.1"), p = u.pathname;
  if (req.method === "GET") {
    if (p === "/" || p === "/index.html") return file(req, res, FORM, "index.html");
    if (p.startsWith("/form/")) return file(req, res, FORM, p.slice(6));
    if (p.startsWith("/data/") && p.endsWith(".json")) return file(req, res, DATA, path.basename(p));
    if (p === "/api/settings") return send(req, res, 200, rj(path.join(STATE, "settings.json"), {}));
    if (p === "/api/meta") return send(req, res, 200, { data: rj(path.join(DATA, "meta.json"), {}), config: rj(path.join(STATE, "config.json"), {}), setup: rj(path.join(STATE, "setup_cache.json"), {}), fx: rj(path.join(STATE, "fx.json"), {}) });
    if (p === "/api/destdocs") return send(req, res, 200, destDocs((u.searchParams.get("country") || "").toUpperCase().slice(0, 2), u.searchParams.get("children") === "1"));
    if (p === "/api/results") { const r = currentRun(); return send(req, res, 200, { run: r, results: r ? rj(path.join(r, "results.json")) : null, progress: r ? rj(path.join(r, "progress.json")) : null }); }
    if (p === "/api/booking-status") { const r = currentRun(); return send(req, res, 200, r ? rj(path.join(r, "booking_status.json"), {}) : {}); }
    return send(req, res, 404, { error: "not found" });
  }
  if (req.method !== "POST" || req.headers["x-fair-fares"] !== "1") return send(req, res, 403, { error: "forbidden" });
  let raw = ""; for await (const c of req) { raw += c; if (raw.length > 5e6) return send(req, res, 413, { error: "too large" }); }
  let b; try { b = JSON.parse(raw || "{}"); } catch { return send(req, res, 400, { error: "bad json" }); }
  if (p === "/api/settings") { b.saved_at = now(); wj(path.join(STATE, "settings.json"), b); return send(req, res, 200, { ok: true }); }
  if (p === "/api/start") { b.saved_at = now(); wj(path.join(STATE, "settings.json"), b); return send(req, res, 200, { ok: true, event: emit("start", { settings_file: path.join(STATE, "settings.json") }).id }); }
  if (p === "/api/doccheck") { delete b._force; return send(req, res, 200, docCheck(b)); }
  if (p === "/api/book") return send(req, res, 200, { ok: true, event: emit("book", { option_id: String(b.option_id).slice(0, 60) }).id });
  send(req, res, 404, { error: "not found" });
});
const args = process.argv.slice(2), arg = (k, d) => (args.includes(k) ? args[args.indexOf(k) + 1] : d);
let port = +arg("--port", 8765);
const page = arg("--page", "");
const open = (url) => exec(process.platform === "darwin" ? `open "${url}"` : process.platform === "win32" ? `start "" "${url}"` : `xdg-open "${url}"`);
server.on("error", (e) => { if (e.code === "EADDRINUSE" && port < 8815) server.listen(++port, "127.0.0.1"); else throw e; });
server.on("listening", () => {
  const url = `http://127.0.0.1:${port}/${page ? "#" + page : ""}`;
  wj(path.join(STATE, "server.json"), { port, pid: process.pid, url, started: Date.now() / 1000, runtime: "node" });
  console.log(JSON.stringify({ reused: false, url }));
  if (!args.includes("--no-open")) open(url);
});
server.listen(port, "127.0.0.1");
