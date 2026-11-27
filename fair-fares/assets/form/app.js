/* Fair Fares form — plain JS, no build step. Talks only to the local server (127.0.0.1). */
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const norm = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
const PAGES = ["trip", "travellers", "check", "results"];
const D = {}; // datasets
let S = {}; // settings (saved to the server, pre-filled next time)

const DEFAULTS = () => ({
  version: 1,
  trip: { home_city: null, closest_airport: null, alternatives: { enabled: false, max_ground_hours: 6, no_limit: false, min_saving: "" },
    destination: null, destination_airports: [], stay_area: "",
    window: { basis: "home", mode: "flexible", earliest: "", latest: "", min_nights: 7, max_nights: 14, till_end: false, leave: "", return: "" } },
  travellers: { adults: 1, children: 0, list: [], passport_mode: "same", passports: { "*": [{ country: "", expiry: "" }] } },
  documents: [],
  doccheck: { req_key: "", result: null, choices: {} },
  prefs: { cabin: "economy", bags: 1, max_stops: 2, max_hours_each_way: "", avoid: { overnight_layovers: false, early_departures: false },
    fare_flex: "cheapest", buffer: { style: "standard", custom_minutes: 120 }, currency: "", currency_auto: true,
    miles: "", railcards: "", insurance: "no", hotels: { enabled: false, budget: "", min_rating: "", must_haves: "" }, enter_details: false },
  unattended: { enabled: true, previous_run: "fresh", new_documents: "add", blocked_sites: "skip", handoff: "wait" },
});

async function api(path, body) {
  const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json", "X-Fair-Fares": "1" }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}
function toast(msg, ms = 3500) { const t = $("#toast"); t.textContent = msg; t.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => (t.hidden = true), ms); }
let saveTimer;
function autosave() { clearTimeout(saveTimer); saveTimer = setTimeout(() => api("/api/settings", S).catch(() => {}), 700); updateNav(); }
function merge(base, over) { for (const k in over) { if (over[k] && typeof over[k] === "object" && !Array.isArray(over[k]) && base[k] && typeof base[k] === "object") merge(base[k], over[k]); else base[k] = over[k]; } return base; }

/* ---------- geography helpers ---------- */
const country = (cc) => D.countryBy[cc] || { name: cc };
function km(a, b, c, d) { const r = Math.PI / 180, x = Math.sin(((c - a) * r) / 2) ** 2 + Math.cos(a * r) * Math.cos(c * r) * Math.sin(((d - b) * r) / 2) ** 2; return 12742 * Math.asin(Math.sqrt(x)); }
const cityLabel = (c) => [c[0], c[2], country(c[3]).name].filter(Boolean).join(", ");
const apLabel = (a) => `${a[1]} (${a[0]}), ${a[2] ? a[2] + ", " : ""}${country(a[3]).name}`;
const apObj = (a) => ({ code: a[0], name: a[1], city: a[2], country: a[3], lat: a[4], lon: a[5], label: apLabel(a) });

function searchCities(q, limit = 8) {
  const parts = norm(q).split(",").map((s) => s.trim()).filter(Boolean);
  if (!parts.length) return [];
  const [p0, ...rest] = parts;
  const out = [];
  for (const c of D.cities) {
    const n = D.cityNorm[c.i];
    if (!(n.name.startsWith(p0) || n.alt.startsWith(p0))) continue;
    if (rest.length && !rest.every((r) => n.region.startsWith(r) || n.country.startsWith(r) || c.v[3].toLowerCase() === r)) continue;
    out.push(c.v);
    if (out.length >= limit) break;
  }
  return out;
}
function nearestAirports(lat, lon, n = 8, filter = () => true) {
  return D.airports.filter(filter).map((a) => [a, km(lat, lon, a[4], a[5])]).sort((x, y) => x[1] - y[1] - (y[0][6] - x[0][6]) * 15).slice(0, n);
}
function searchAirports(q, near) {
  const s = norm(q);
  let list = D.airports.filter((a) => a[0].toLowerCase() === s || norm(a[1]).includes(s) || norm(a[2]).startsWith(s) || norm(country(a[3]).name).startsWith(s));
  list.sort((x, y) => (y[0].toLowerCase() === s) - (x[0].toLowerCase() === s) || (near ? km(near.lat, near.lon, x[4], x[5]) - km(near.lat, near.lon, y[4], y[5]) : y[6] - x[6]));
  return list.slice(0, 10);
}

/* ---------- combobox ---------- */
function combo(input, { search, pick, onFocusList }) {
  const list = document.createElement("ul");
  list.className = "ac-list"; list.id = input.getAttribute("aria-controls"); list.setAttribute("role", "listbox"); list.hidden = true;
  input.after(list);
  let items = [], active = -1;
  const close = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); active = -1; };
  const render = (arr) => {
    items = arr; active = -1;
    if (!arr.length) return close();
    list.innerHTML = arr.map((it, i) => `<li role="option" id="${list.id}-${i}" aria-selected="false" data-i="${i}"><span>${esc(it.label)}</span>${it.tag ? `<span class="tag">${esc(it.tag)}</span>` : ""}</li>`).join("");
    list.hidden = false; input.setAttribute("aria-expanded", "true");
  };
  const choose = (i) => { const it = items[i]; if (!it) return; pick(it.value, it); close(); };
  input.addEventListener("input", () => render(input.value.trim() ? search(input.value) : onFocusList ? onFocusList() : []));
  input.addEventListener("focus", () => { if (!input.value.trim() && onFocusList) render(onFocusList()); });
  input.addEventListener("keydown", (e) => {
    if (list.hidden) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault(); active = (active + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
      $$("li", list).forEach((li, i) => li.setAttribute("aria-selected", i === active)); input.setAttribute("aria-activedescendant", `${list.id}-${active}`);
      $$("li", list)[active]?.scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") { e.preventDefault(); choose(active < 0 ? 0 : active); }
    else if (e.key === "Escape") close();
  });
  list.addEventListener("mousedown", (e) => { const li = e.target.closest("li"); if (li) { e.preventDefault(); choose(+li.dataset.i); } });
  input.addEventListener("blur", () => setTimeout(close, 120));
}

/* ---------- page 1 ---------- */
function setupTrip() {
  combo($("#home"), {
    search: (q) => searchCities(q).map((c) => ({ label: cityLabel(c), tag: c[6] ? `${Math.round(c[6] / 1000)}k people` : "", value: c })),
    pick: (c) => {
      S.trip.home_city = { name: c[0], region: c[2], country: c[3], lat: c[4], lon: c[5], label: cityLabel(c) };
      $("#home").value = cityLabel(c);
      const near = nearestAirports(c[4], c[5], 1, (a) => a[6] >= 2)[0];
      if (near && !S.trip.closest_airport) { S.trip.closest_airport = apObj(near[0]); $("#airport").value = apLabel(near[0]); }
      if (S.prefs.currency_auto !== false) { S.prefs.currency = country(c[3]).currency || S.prefs.currency; $("#p-cur").value = S.prefs.currency; updateCurrency(); }
      autosave();
    },
  });
  combo($("#airport"), {
    search: (q) => searchAirports(q, S.trip.home_city).map((a) => ({ label: apLabel(a), tag: S.trip.home_city ? `${Math.round(km(S.trip.home_city.lat, S.trip.home_city.lon, a[4], a[5]))} km` : "", value: a })),
    onFocusList: () => (S.trip.home_city ? nearestAirports(S.trip.home_city.lat, S.trip.home_city.lon, 8).map(([a, d]) => ({ label: apLabel(a), tag: `${Math.round(d)} km`, value: a })) : []),
    pick: (a) => { S.trip.closest_airport = apObj(a); $("#airport").value = apLabel(a); autosave(); },
  });
  combo($("#dest"), {
    search: (q) => {
      const s = norm(q), out = [];
      for (const c of D.countries) if (norm(c[1]).startsWith(s)) out.push({ label: c[1], tag: "Country", value: { type: "country", name: c[1], country: c[0], lat: c[3], lon: c[4], label: c[1] } });
      for (const st of D.states) if (norm(st[1]).startsWith(s)) out.push({ label: `${st[1]}, ${country(st[0]).name}`, tag: "Region", value: { type: "region", name: st[1], country: st[0], lat: st[3], lon: st[4], label: `${st[1]}, ${country(st[0]).name}` } });
      for (const c of searchCities(q, 6)) out.push({ label: cityLabel(c), tag: "City", value: { type: "city", name: c[0], region: c[2], country: c[3], lat: c[4], lon: c[5], label: cityLabel(c) } });
      return out.slice(0, 12);
    },
    pick: (v) => { S.trip.destination = v; $("#dest").value = v.label; S.trip.destination_airports = []; renderDestAirports(); S.destdocs = null; autosave(); },
  });
  combo($("#dest-ap"), {
    search: (q) => searchAirports(q, S.trip.destination).map((a) => ({ label: apLabel(a), tag: a[0], value: a })),
    pick: (a) => { addDestAirport(a); $("#dest-ap").value = ""; },
  });
  $("#alt-enabled").addEventListener("change", (e) => { S.trip.alternatives.enabled = e.target.checked; $("#alt-box").hidden = !e.target.checked; autosave(); });
  $("#alt-nolimit").addEventListener("change", (e) => { S.trip.alternatives.no_limit = e.target.checked; $("#alt-hours-wrap").hidden = e.target.checked; autosave(); });
  bind("#alt-hours", (v) => (S.trip.alternatives.max_ground_hours = v === "" ? "" : +v));
  bind("#alt-saving", (v) => (S.trip.alternatives.min_saving = v === "" ? "" : +v));
  bind("#stay", (v) => (S.trip.stay_area = v));
  $$("[data-mode]").forEach((b) => b.addEventListener("click", () => { S.trip.window.mode = b.dataset.mode; renderWindow(); autosave(); }));
  [["#w-earliest", "earliest"], ["#w-latest", "latest"], ["#w-leave", "leave"], ["#w-return", "return"]].forEach(([id, k]) => bind(id, (v) => { S.trip.window[k] = v; renderWindow(); }));
  bind("#w-min", (v) => { S.trip.window.min_nights = +v || ""; renderWindow(); });
  bind("#w-max", (v) => { S.trip.window.max_nights = +v || ""; renderWindow(); });
  $("#w-tillend").addEventListener("change", (e) => { S.trip.window.till_end = e.target.checked; renderWindow(); autosave(); });
  $$("[data-basis]").forEach((b) => b.addEventListener("click", () => { S.trip.window.basis = b.dataset.basis; renderWindow(); autosave(); }));
}
function bind(sel, fn) { $(sel).addEventListener("input", (e) => { fn(e.target.type === "checkbox" ? e.target.checked : e.target.value); autosave(); }); }
function addDestAirport(a) { if (!S.trip.destination_airports.some((x) => x.code === a[0])) S.trip.destination_airports.push(apObj(a)); renderDestAirports(); autosave(); }
function renderDestAirports() {
  $("#dest-ap-chips").innerHTML = S.trip.destination_airports.map((a) => `<span class="chip">${esc(a.code)} · ${esc(a.city || a.name)}<button type="button" aria-label="Remove ${esc(a.code)}" data-rm="${esc(a.code)}">×</button></span>`).join("");
  $$("#dest-ap-chips [data-rm]").forEach((b) => b.addEventListener("click", () => { S.trip.destination_airports = S.trip.destination_airports.filter((x) => x.code !== b.dataset.rm); renderDestAirports(); autosave(); }));
  const d = S.trip.destination, box = $("#dest-ap-suggest");
  if (!d) { box.innerHTML = ""; return; }
  let sug;
  if (d.type === "country") sug = D.airports.filter((a) => a[3] === d.country).sort((x, y) => y[6] - x[6]).slice(0, 8).map((a) => [a]);
  else sug = nearestAirports(d.lat, d.lon, 6).filter(([, dist]) => dist < 300);
  sug = sug.filter(([a]) => !S.trip.destination_airports.some((x) => x.code === a[0]));
  box.innerHTML = sug.length ? `<span class="hint" style="width:100%">Nearby — tap to add (empty means any airport):</span>` + sug.map(([a, dist]) => `<button type="button" data-add="${esc(a[0])}">+ ${esc(a[0])} ${esc(a[2] || a[1])}${dist ? ` · ${Math.round(dist)} km` : ""}</button>`).join("") : "";
  $$("[data-add]", box).forEach((b) => b.addEventListener("click", () => addDestAirport(D.apBy[b.dataset.add])));
}
const fmt = (iso, year) => {
  const d = new Date(iso + "T12:00:00");
  if (isNaN(d)) return "";
  const p = (o) => d.toLocaleDateString("en-GB", o);
  return `${p({ weekday: "short" })} ${d.getDate()} ${p({ month: "short" })}${year ? " " + d.getFullYear() : ""}`;
};
const nightsBetween = (a, b) => Math.round((new Date(b) - new Date(a)) / 864e5);
function windowSpan() { const w = S.trip.window; return w.earliest && w.latest ? nightsBetween(w.earliest, w.latest) : 0; }
function renderWindow() {
  const w = S.trip.window, flex = w.mode === "flexible", dest = w.basis === "destination";
  $$("[data-mode]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.mode === w.mode));
  $$("[data-basis]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.basis === w.basis));
  $("#win-flex").hidden = !flex; $("#win-exact").hidden = flex;
  const addD = (iso, n) => { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };
  const place = S.trip.destination?.name || "your destination";
  const exA = (flex ? w.earliest : w.leave) || "2027-03-06", exB = (flex ? w.latest : w.return) || "2027-04-25";
  $("#basis-hint").innerHTML = dest
    ? `<strong>Travel happens outside your dates.</strong> Your dates are when you can be in ${esc(place)}. To be there from ${esc(fmt(exA))}, you might leave home on ${esc(fmt(addD(exA, -1)))}, and after leaving on ${esc(fmt(exB))} you might get home on ${esc(fmt(addD(exB, 1)))}. Choose this when the dates are fixed by something at the destination, like an event or a booking there.`
    : `<strong>Your travel days count inside your dates.</strong> You leave home on or after ${esc(fmt(exA))} and are back home by ${esc(fmt(exB))}. A long trip often takes about a day each way, so you get a day or two fewer nights in ${esc(place)} than the dates suggest. Choose this when the dates are your time off.`;
  $("#l-earliest").textContent = dest ? "First day I can be at my destination" : "Earliest day I can leave home";
  $("#l-latest").textContent = dest ? "Last day I can be at my destination" : "Latest day I must be back home";
  $("#l-leave").textContent = dest ? "Arrive at my destination on" : "Leave home on";
  $("#l-return").textContent = dest ? "Leave my destination on" : "Get back home on";
  // Keep the nights within the window.
  const span = windowSpan();
  const minI = $("#w-min"), maxI = $("#w-max");
  if (span > 0) {
    minI.max = span; maxI.max = span; maxI.min = Math.max(1, w.min_nights || 1);
    if (w.min_nights > span) { w.min_nights = span; minI.value = span; }
    if (w.max_nights > span) { w.max_nights = span; maxI.value = span; }
    if (w.max_nights && w.min_nights > w.max_nights) { w.max_nights = w.min_nights; maxI.value = w.min_nights; }
  } else { minI.max = 365; maxI.max = 365; }
  $("#w-max-wrap").hidden = !!w.till_end; $("#w-tillend").checked = !!w.till_end;
  $("#nights-hint").textContent = span > 0 ? (dest
    ? `You can be there for up to ${span} nights. Travel days are extra.`
    : `${span} nights from leaving home to getting back, travel days included. Count only the nights you want at the destination.`) : "";
  let msg = "Pick your dates.", ok = false;
  if (flex && w.earliest && w.latest) {
    const y = new Date(w.earliest).getFullYear() !== new Date(w.latest).getFullYear();
    const maxN = w.till_end ? span : Math.min(w.max_nights || span, span);
    const stay = w.till_end ? `at least ${w.min_nights || 1} nights in ${place} (longer is fine, up to your whole window)` : `${w.min_nights || 1} to ${maxN} nights in ${place}`;
    if (span <= 0) msg = "The second date must be after the first.";
    else if (!w.min_nights) msg = "How many nights do you want at the destination?";
    else { ok = true; msg = dest
      ? `Be at your destination any time from ${fmt(w.earliest, y)} to ${fmt(w.latest, true)}, staying ${stay}. Travel there and back can be the day before and the day after.`
      : `Leave home any day from ${fmt(w.earliest, y)}, be back home by ${fmt(w.latest, true)}, staying ${stay}. Travel days count inside these dates.`; }
  } else if (!flex && w.leave && w.return) {
    const n = nightsBetween(w.leave, w.return);
    ok = n > 0;
    msg = !ok ? "The second date must be after the first." : dest
      ? `Arrive on ${fmt(w.leave)} and leave on ${fmt(w.return, true)} (${n} nights there). Travel can be a day before and after.`
      : `Leave home on ${fmt(w.leave)}, get back home on ${fmt(w.return, true)} (${n} nights from leaving to getting back, travel days included).`;
  }
  $("#win-summary").textContent = msg;
  const tl = $("#timeline");
  const a = flex ? w.earliest : w.leave, b = flex ? w.latest : w.return;
  if (!ok) { tl.innerHTML = ""; return; }
  const total = nightsBetween(a, b), pct = (iso) => Math.max(0, Math.min(100, (nightsBetween(a, iso) / total) * 100));
  const addDays = (iso, n) => { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };
  const minEnd = flex ? addDays(a, w.min_nights || 1) : b, maxEnd = flex ? addDays(a, w.till_end ? total : Math.min(w.max_nights || total, total)) : b;
  const hols = (S._holidays || []).filter((h) => h.end >= a && h.start <= b)
    .map((h) => `<div class="tl-hol" title="${esc(h.name)}" style="left:${pct(h.start)}%;width:${Math.max(0.8, pct(h.end) - pct(h.start))}%"></div>`).join("");
  tl.innerHTML = `<div class="tl-track"></div><div class="tl-trip" style="left:0;width:${pct(maxEnd)}%;opacity:.25"></div><div class="tl-trip" style="left:0;width:${pct(minEnd)}%"></div>${hols}
    <span class="tl-lab" style="left:0">${esc(fmt(a))}</span><span class="tl-lab" style="right:0">${esc(fmt(b))}</span>`;
}

/* ---------- page 2 ---------- */
function syncTravellers() {
  const t = S.travellers, old = Object.fromEntries((t.list || []).map((x) => [x.id, x])), list = [];
  for (let i = 1; i <= t.adults; i++) list.push(old[`a${i}`] || { id: `a${i}`, name: "", child: false });
  for (let i = 1; i <= t.children; i++) list.push(old[`c${i}`] || { id: `c${i}`, name: "", child: true, age: "" });
  t.list = list;
  for (const x of list) if (t.passport_mode === "per" && !t.passports[x.id]) t.passports[x.id] = JSON.parse(JSON.stringify(t.passports["*"] || [{ country: "", expiry: "" }]));
}
const tName = (x) => x.name || (x.child ? `Child ${x.id.slice(1)}` : `Adult ${x.id.slice(1)}`);
function countryOptions(sel) { return `<option value="">Choose country…</option>` + D.countries.map((c) => `<option value="${c[0]}" ${c[0] === sel ? "selected" : ""}>${esc(c[1])}</option>`).join(""); }
function renderTravellers() {
  syncTravellers();
  const t = S.travellers;
  $("#adults").textContent = t.adults; $("#children").textContent = t.children;
  $$("[data-pp]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.pp === t.passport_mode));
  const blocks = t.passport_mode === "same" ? [{ key: "*", title: "Everyone", person: null }] : t.list.map((x) => ({ key: x.id, title: tName(x), person: x }));
  $("#pp-list").innerHTML = blocks.map((b) => {
    const pps = t.passports[b.key] || (t.passports[b.key] = [{ country: "", expiry: "" }]);
    const person = b.person ? `<div class="grid two"><div class="field"><label for="nm-${b.key}">Name (optional)</label><input id="nm-${b.key}" type="text" data-name="${b.key}" value="${esc(b.person.name)}"></div>
      ${b.person.child ? `<div class="field"><label for="age-${b.key}">Age</label><input id="age-${b.key}" type="number" min="0" max="17" data-age="${b.key}" value="${esc(b.person.age)}" inputmode="numeric"></div>` : ""}</div>` : "";
    return `<div class="traveller"><strong>${esc(b.title)}</strong>${person}${pps.map((p, i) => `
      <div class="grid two"><div class="field"><label for="pc-${b.key}-${i}">${i ? "Second passport" : "Passport country"}</label><select id="pc-${b.key}-${i}" data-ppc="${b.key}:${i}">${countryOptions(p.country)}</select></div>
      <div class="field"><label for="pe-${b.key}-${i}">Passport expiry date</label><div class="inline"><input id="pe-${b.key}-${i}" type="date" data-ppe="${b.key}:${i}" value="${esc(p.expiry)}" style="max-width:220px">
      ${i ? `<button type="button" class="btn small" data-pprm="${b.key}:${i}">Remove</button>` : ""}</div></div></div>`).join("")}
      ${pps.length < 3 ? `<div><button type="button" class="btn small" data-ppadd="${b.key}">+ Add second passport</button> <span class="hint">for dual nationals</span></div>` : ""}</div>`;
  }).join("");
  if (t.passport_mode === "same") {
    const kids = t.list.filter((x) => x.child);
    $("#pp-list").insertAdjacentHTML("beforeend", `<div class="grid two">${t.list.map((x) => `<div class="field"><label for="nm-${x.id}">${esc(x.child ? `Child ${x.id.slice(1)}` : `Adult ${x.id.slice(1)}`)} name (optional)</label><input id="nm-${x.id}" type="text" data-name="${x.id}" value="${esc(x.name)}"></div>${x.child ? `<div class="field"><label for="age-${x.id}">Age</label><input id="age-${x.id}" type="number" min="0" max="17" data-age="${x.id}" value="${esc(x.age)}"></div>` : ""}`).join("")}</div>`);
  }
  $$("[data-name]").forEach((i) => i.addEventListener("change", () => { t.list.find((x) => x.id === i.dataset.name).name = i.value.trim(); autosave(); renderDocGrids(); }));
  $$("[data-age]").forEach((i) => i.addEventListener("input", () => { t.list.find((x) => x.id === i.dataset.age).age = i.value; autosave(); }));
  $$("[data-ppc]").forEach((s) => s.addEventListener("change", () => { const [k, i] = s.dataset.ppc.split(":"); t.passports[k][i].country = s.value; autosave(); }));
  $$("[data-ppe]").forEach((s) => s.addEventListener("input", () => { const [k, i] = s.dataset.ppe.split(":"); t.passports[k][i].expiry = s.value; autosave(); }));
  $$("[data-ppadd]").forEach((b) => b.addEventListener("click", () => { t.passports[b.dataset.ppadd].push({ country: "", expiry: "" }); renderTravellers(); autosave(); }));
  $$("[data-pprm]").forEach((b) => b.addEventListener("click", () => { const [k, i] = b.dataset.pprm.split(":"); t.passports[k].splice(+i, 1); renderTravellers(); autosave(); }));
  renderDocGrids();
}
async function loadDestDocs() {
  const d = S.trip.destination;
  $("#dest-name").textContent = d ? d.label : "your destination";
  if (!d) { $("#destdocs").innerHTML = `<tr><td class="muted">Choose a destination on page 1.</td></tr>`; return; }
  const key = `${d.country}:${S.travellers.children > 0 ? 1 : 0}`;
  if (!S.destdocs || S.destdocs.key !== key) {
    $("#destdocs").innerHTML = `<tr><td><span class="progress"><span class="spinner"></span> Looking up documents for ${esc(country(d.country).name)}…</span></td></tr>`;
    try { const r = await api(`/api/destdocs?country=${d.country}&children=${S.travellers.children > 0 ? 1 : 0}`); S.destdocs = { key, ...r }; }
    catch { S.destdocs = { key, documents: [] }; }
    autosave();
  }
  const m = S.destdocs.model;
  $("#destdocs-hint").textContent = "Tick who holds each document." + (S.destdocs.covered_by_rules ? "" : m === "ok" || m === "cached" ? " Some items came from the small model — the search double-checks them." : " This destination isn't in the curated list; the search will check official sources.");
  renderDocGrids();
}
function docRows(kind, docs) {
  const people = S.travellers.list;
  if (!docs.length) return `<tr><td class="muted">${kind === "other" ? "None added." : "No specific documents found."}</td></tr>`;
  return `<thead><tr><th scope="col">Document</th><th scope="col">Everyone</th>${people.map((p) => `<th scope="col">${esc(tName(p))}</th>`).join("")}${kind === "other" ? "<th></th>" : ""}</tr></thead><tbody>` +
    docs.map((d) => {
      const held = (S.documents.find((x) => x.id === d.id) || {}).applies_to || [];
      const all = people.length && people.every((p) => held.includes(p.id));
      const some = !all && people.some((p) => held.includes(p.id));
      return `<tr><th scope="row" style="font-weight:500">${esc(d.label)}</th><td><label class="cell"><input type="checkbox" data-all="${esc(d.id)}" ${all ? "checked" : ""} ${some ? 'data-partial="1" aria-checked="mixed"' : ""} aria-label="${esc(d.label)}: everyone"></label></td>` +
        people.map((p) => `<td><label class="cell"><input type="checkbox" data-doc="${esc(d.id)}" data-who="${p.id}" ${held.includes(p.id) ? "checked" : ""} aria-label="${esc(d.label)}: ${esc(tName(p))}"></label></td>`).join("") +
        (kind === "other" ? `<td><button type="button" class="btn small" data-docrm="${esc(d.id)}" aria-label="Remove ${esc(d.label)}">×</button></td>` : "") + "</tr>";
    }).join("") + "</tbody>";
}
function renderDocGrids() {
  const dd = (S.destdocs?.documents || []).filter((d) => !(d.id === "child_consent" && !S.travellers.children));
  const other = S.documents.filter((d) => d.kind === "other");
  $("#destdocs").innerHTML = S.trip.destination ? docRows("destination", dd) : `<tr><td class="muted">Choose a destination on page 1.</td></tr>`;
  $("#otherdocs").innerHTML = docRows("other", other);
  const upsert = (id) => { let d = S.documents.find((x) => x.id === id); if (!d) { const src = dd.find((x) => x.id === id) || other.find((x) => x.id === id); d = { id, label: src?.label || id, kind: "destination", applies_to: [] }; S.documents.push(d); } return d; };
  $$("[data-doc]").forEach((c) => c.addEventListener("change", () => { const d = upsert(c.dataset.doc); d.applies_to = d.applies_to.filter((x) => x !== c.dataset.who); if (c.checked) d.applies_to.push(c.dataset.who); renderDocGrids(); autosave(); }));
  $$("[data-all][data-partial]").forEach((c) => (c.indeterminate = true));
  $$("[data-all]").forEach((c) => c.addEventListener("change", () => { const d = upsert(c.dataset.all); d.applies_to = c.checked ? S.travellers.list.map((p) => p.id) : []; renderDocGrids(); autosave(); }));
  $$("[data-docrm]").forEach((b) => b.addEventListener("click", () => { S.documents = S.documents.filter((x) => x.id !== b.dataset.docrm); renderDocGrids(); autosave(); }));
}
function setupTravellers() {
  $$("[data-step]").forEach((b) => b.addEventListener("click", () => {
    const [k, n] = b.dataset.step.split(":"), t = S.travellers;
    t[k] = Math.max(k === "adults" ? 1 : 0, Math.min(9, t[k] + +n));
    renderTravellers(); if (k === "children") loadDestDocs(); autosave();
  }));
  $$("[data-pp]").forEach((b) => b.addEventListener("click", () => { S.travellers.passport_mode = b.dataset.pp; renderTravellers(); autosave(); }));
  const cat = D.rules.catalog || [];
  $("#other-pick").innerHTML = `<option value="">Choose a document…</option>` + cat.map((c) => `<option value="${esc(c.id)}">${esc(c.label)}</option>`).join("");
  $("#other-add").addEventListener("click", () => {
    const id = $("#other-pick").value, free = $("#other-free").value.trim();
    const label = id ? cat.find((c) => c.id === id).label : free;
    if (!label) return toast("Choose or type a document first.");
    const did = id || "custom_" + norm(free).replace(/[^a-z0-9]+/g, "_").slice(0, 30);
    if (!S.documents.some((d) => d.id === did)) S.documents.push({ id: did, label, kind: "other", applies_to: S.travellers.list.length === 1 ? [S.travellers.list[0].id] : [] });
    else S.documents.find((d) => d.id === did).kind = "other";
    $("#other-pick").value = ""; $("#other-free").value = ""; renderDocGrids(); autosave();
  });
}

/* ---------- page 3 ---------- */
function docRequest() {
  const t = S.travellers, w = S.trip.window;
  return {
    destination: S.trip.destination?.country || "",
    earliest_departure: w.mode === "flexible" ? w.earliest : w.leave,
    return_by: w.mode === "flexible" ? w.latest : w.return,
    travellers: t.list.map((x) => ({ id: x.id, name: tName(x), child: x.child, passports: (t.passport_mode === "same" ? t.passports["*"] : t.passports[x.id] || []).filter((p) => p.country) })),
    documents: S.documents.filter((d) => d.applies_to.length).map((d) => ({ id: d.id, label: d.label, applies_to: d.applies_to })),
  };
}
async function runDocCheck(force = false) {
  const req = docRequest();
  if (!req.destination) { $("#dc-status").textContent = "Choose a destination on page 1 first."; return; }
  const k = JSON.stringify(req);
  if (!force && S.doccheck.req_key === k && S.doccheck.result) return renderDocCheck();
  $("#dc-status").innerHTML = `<span class="spinner"></span> Checking documents…`;
  $("#dc-again").disabled = true;
  try { S.doccheck.result = await api("/api/doccheck", { ...req, _force: force }); S.doccheck.req_key = k; autosave(); }
  catch (e) { $("#dc-status").textContent = "The document check failed: " + e.message; }
  $("#dc-again").disabled = false;
  renderDocCheck();
}
const STATUS_CLS = { OK: "s-ok", Missing: "s-missing", "At risk": "s-risk" };
function money(f) {
  if (!f || f.amount == null) return "";
  let s = `${f.approx ? "≈ " : ""}${Number(f.amount).toLocaleString("en-GB")} ${f.currency}`;
  const fx = D.fx?.rates, to = S.prefs.currency;
  if (fx && to && f.currency !== to && fx[f.currency] && fx[to]) s += ` (≈ ${Math.round((f.amount / fx[f.currency]) * fx[to]).toLocaleString("en-GB")} ${to})`;
  return s + (f.note ? ` — ${f.note}` : "");
}
function renderDocCheck() {
  const r = S.doccheck.result;
  if (!r) return;
  $("#dc-date").textContent = `Visa dataset dated ${r.visa_dataset_date || "unknown"} · checked ${r.checked_at?.replace("T", " ") || ""}${r.cached ? " (unchanged inputs — reused)" : ""}`;
  $("#dc-status").textContent = "";
  const people = S.travellers.list;
  const byT = (id) => r.items.filter((i) => i.traveller === id);
  let html = people.map((p) => `<h3 style="margin:16px 0 4px">${esc(tName(p))}</h3>` + byT(p.id).map((it) => {
    const ck = `${it.traveller}:${it.doc_id}`, ch = S.doccheck.choices[ck] || "";
    const pd = it.processing_days ? (it.processing_days[0] === it.processing_days[1] ? `${it.processing_days[0]} days` : `${it.processing_days[0]}–${it.processing_days[1]} days`) : "";
    return `<div class="doc-item"><div class="doc-head"><span class="status ${STATUS_CLS[it.status] || "s-info"}">${esc(it.status)}</span><strong>${esc(it.label)}</strong>${it.source === "model" ? `<span class="status s-info">small model</span>` : ""}</div>
      <div class="doc-meta">${esc(it.note || "")}${it.fee ? ` · Fee ${esc(money(it.fee))}` : ""}${pd ? ` · Processing ${esc(pd)}` : ""}${it.official ? ` · <a href="${esc(it.official)}" target="_blank" rel="noopener">official site</a>` : ""}</div>
      ${it.warning ? `<div class="warning">⚠ ${esc(it.warning)}</div>` : ""}
      ${it.status !== "OK" ? `<div class="seg" role="group" aria-label="${esc(it.label)}"><button type="button" data-choice="${esc(ck)}:add" aria-pressed="${ch === "add"}">Add Cost to Estimate</button><button type="button" data-choice="${esc(ck)}:arrange" aria-pressed="${ch === "arrange"}">I'll Arrange It</button></div>` : ""}</div>`;
  }).join("")).join("");
  if (r.pending?.length) html += `<div class="note" style="margin-top:12px"><strong>Not answerable from the dataset${r.model_status === "no_model" ? " (no small model available)" : ""}:</strong><ul>${r.pending.map((p) => `<li>${esc(tName(people.find((x) => x.id === p.traveller) || { id: p.traveller }))}: ${esc(p.question)}</li>`).join("")}</ul>The agent will ask you in chat or check official sources during the search.</div>`;
  $("#dc-items").innerHTML = html;
  $$("[data-choice]").forEach((b) => b.addEventListener("click", () => { const i = b.dataset.choice.lastIndexOf(":"); S.doccheck.choices[b.dataset.choice.slice(0, i)] = b.dataset.choice.slice(i + 1); renderDocCheck(); autosave(); }));
}
function updateCurrency() { $$(".cur-suffix").forEach((s) => (s.textContent = S.prefs.currency || "")); const c = D.currencies[S.prefs.currency]; $("#cur-hint").textContent = c ? `${c[0]} (${c[1]})` + (S.prefs.currency_auto !== false ? " — set from your home city's country." : "") : "Type a 3-letter code."; }
function setupPrefs() {
  const P = S.prefs;
  bind("#p-cabin", (v) => (P.cabin = v)); bind("#p-bags", (v) => (P.bags = +v)); bind("#p-stops", (v) => (P.max_stops = +v)); bind("#p-hours", (v) => (P.max_hours_each_way = v === "" ? "" : +v));
  bind("#p-avoid-overnight", (v) => (P.avoid.overnight_layovers = v)); bind("#p-avoid-early", (v) => (P.avoid.early_departures = v));
  $("#p-cabin").addEventListener("change", (e) => { P.cabin = e.target.value; autosave(); }); $("#p-stops").addEventListener("change", (e) => { P.max_stops = +e.target.value; autosave(); });
  $$("[data-flex]").forEach((b) => b.addEventListener("click", () => { P.fare_flex = b.dataset.flex; renderPrefs(); autosave(); }));
  $$("[data-buf]").forEach((b) => b.addEventListener("click", () => { P.buffer.style = b.dataset.buf; renderPrefs(); autosave(); }));
  bind("#buf-min", (v) => { P.buffer.custom_minutes = +v; renderPrefs(); });
  $("#cur-list").innerHTML = Object.entries(D.currencies).sort().map(([k, v]) => `<option value="${k}">${esc(v[0])}</option>`).join("");
  $("#p-cur").addEventListener("input", (e) => { const v = e.target.value.toUpperCase().slice(0, 3); P.currency = v; P.currency_auto = false; updateCurrency(); autosave(); });
  bind("#p-ins", (v) => (P.insurance = v)); $("#p-ins").addEventListener("change", (e) => { P.insurance = e.target.value; autosave(); });
  bind("#p-miles", (v) => (P.miles = v)); bind("#p-rail", (v) => (P.railcards = v));
  $("#h-enabled").addEventListener("change", (e) => { P.hotels.enabled = e.target.checked; $("#h-box").hidden = !e.target.checked; autosave(); });
  bind("#h-budget", (v) => (P.hotels.budget = v === "" ? "" : +v)); $("#h-rating").addEventListener("change", (e) => { P.hotels.min_rating = e.target.value; autosave(); }); bind("#h-must", (v) => (P.hotels.must_haves = v));
  bind("#p-details", (v) => (P.enter_details = v));
  const U = () => S.unattended;
  $("#u-enabled").addEventListener("change", (e) => { U().enabled = e.target.checked; $("#u-box").hidden = !e.target.checked; autosave(); });
  [["#u-prev", "previous_run"], ["#u-docs", "new_documents"], ["#u-blocked", "blocked_sites"], ["#u-handoff", "handoff"]].forEach(([id, k]) =>
    $(id).addEventListener("change", (e) => { U()[k] = e.target.value; autosave(); }));
  $("#dc-again").addEventListener("click", () => runDocCheck(true));
}
function renderPrefs() {
  const P = S.prefs;
  $$("[data-flex]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.flex === P.fare_flex));
  $$("[data-buf]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.buf === P.buffer.style));
  $("#buf-custom").hidden = P.buffer.style !== "custom";
  const BUF = {
    relaxed: "Tighter connections for a cheaper or quicker trip: about three quarters of the usual margin. For example, reaching the airport about 2¼ hours before a long-haul flight. More risk of a missed connection.",
    standard: "The usual safety margin: the minimum time for the connection plus how late that train, bus or airline typically runs. For example, reaching the airport about 3 hours before a long-haul flight.",
    extra: "Half as much margin again, for important trips or unreliable connections. For example, reaching the airport about 4½ hours before a long-haul flight. Overnight stays near the airport are suggested more often.",
    custom: `Exactly ${P.buffer.custom_minutes || "the"} minutes on top of the minimum time for each connection, whatever the usual delays are.`,
  };
  $("#buf-hint").textContent = BUF[P.buffer.style] || "";
}

/* ---------- fill every input from S ---------- */
function fillAll() {
  const T = S.trip, P = S.prefs, A = T.alternatives, W = T.window;
  $("#home").value = T.home_city?.label || ""; $("#airport").value = T.closest_airport?.label || ""; $("#dest").value = T.destination?.label || "";
  $("#alt-enabled").checked = A.enabled; $("#alt-box").hidden = !A.enabled; $("#alt-hours").value = A.max_ground_hours; $("#alt-nolimit").checked = A.no_limit; $("#alt-hours-wrap").hidden = A.no_limit; $("#alt-saving").value = A.min_saving;
  $("#stay").value = T.stay_area;
  $("#w-earliest").value = W.earliest; $("#w-latest").value = W.latest; $("#w-min").value = W.min_nights; $("#w-max").value = W.max_nights; $("#w-tillend").checked = !!W.till_end; $("#w-leave").value = W.leave; $("#w-return").value = W.return;
  $("#p-cabin").value = P.cabin; $("#p-bags").value = P.bags; $("#p-stops").value = P.max_stops; $("#p-hours").value = P.max_hours_each_way;
  $("#p-avoid-overnight").checked = P.avoid.overnight_layovers; $("#p-avoid-early").checked = P.avoid.early_departures;
  $("#buf-min").value = P.buffer.custom_minutes; $("#p-cur").value = P.currency; $("#p-ins").value = P.insurance; $("#p-miles").value = P.miles; $("#p-rail").value = P.railcards;
  $("#h-enabled").checked = P.hotels.enabled; $("#h-box").hidden = !P.hotels.enabled; $("#h-budget").value = P.hotels.budget; $("#h-rating").value = P.hotels.min_rating; $("#h-must").value = P.hotels.must_haves;
  $("#p-details").checked = P.enter_details;
  const U = S.unattended;
  $("#u-enabled").checked = U.enabled; $("#u-box").hidden = !U.enabled;
  $("#u-prev").value = U.previous_run; $("#u-docs").value = U.new_documents; $("#u-blocked").value = U.blocked_sites; $("#u-handoff").value = U.handoff;
  renderDestAirports(); renderWindow(); renderTravellers(); renderPrefs(); updateCurrency();
}

/* ---------- validation & start ---------- */
function problems() {
  const T = S.trip, W = T.window, out = [];
  if (!T.home_city) out.push(["trip", "Choose your home city."]);
  if (!T.closest_airport) out.push(["trip", "Choose your closest airport."]);
  if (!T.destination) out.push(["trip", "Choose a destination."]);
  if (W.mode === "flexible") {
    if (!(W.earliest && W.latest)) out.push(["trip", "Pick both dates."]);
    else if (nightsBetween(W.earliest, W.latest) <= 0) out.push(["trip", "The second date must be after the first."]);
    else if (!W.min_nights) out.push(["trip", "Say how many nights you want to stay."]);
    else if (!W.till_end && !W.max_nights) out.push(["trip", "Add the longest stay, or tick \"up to the end of my window\"."]);
  } else if (!(W.leave && W.return)) out.push(["trip", "Pick both dates."]);
  else if (nightsBetween(W.leave, W.return) <= 0) out.push(["trip", "The second date must be after the first."]);
  const t = S.travellers;
  for (const x of t.list) { const pps = t.passport_mode === "same" ? t.passports["*"] : t.passports[x.id]; if (!(pps || []).some((p) => p.country)) { out.push(["travellers", `Add a passport country for ${tName(x)}.`]); break; } }
  if (!/^[A-Z]{3}$/.test(S.prefs.currency || "")) out.push(["check", "Choose a currency."]);
  return out;
}
async function start() {
  const p = problems();
  if (p.length) { toast(p[0][1]); return go(p[0][0]); }
  S.started_from_form = new Date().toISOString();
  try { await api("/api/start", S); toast("Search started — the agent picks it up now.", 5000); go("results"); }
  catch (e) { toast("Couldn't reach the local server: " + e.message); }
}

/* ---------- results ---------- */
let pollTimer;
const n0 = (v) => (v === "" || v == null || isNaN(+v) ? "" : Math.round(+v).toLocaleString("en-GB"));
function optionRow(o, cur) {
  const parts = [["Flights", o.flight_cost], ["Ground", o.ground_cost], ["Positioning flight", o.positioning_flight_details ? "" : null], ["Destination transfers", o.destination_transfer_cost], ["Hotel", o.hotel_cost],
    ["Documents", o.document_costs], ["Transit documents", o.transit_document_costs], ["Insurance", o.insurance_estimate], ["Bag fees", o.bag_fees], ["Payment fees", o.payment_fees], ["Extras", o.extras_cost]].filter(([, v]) => v !== null && v !== "" && v !== undefined);
  const saving = o.saving_vs_direct !== "" && +o.saving_vs_direct > 0 ? `${n0(o.saving_vs_direct)} ${cur} cheaper` : o.saving_vs_direct !== "" && +o.saving_vs_direct < 0 ? `${n0(-o.saving_vs_direct)} ${cur} dearer` : "";
  const eh = parseFloat(o.extra_time_vs_direct);
  const extra = !isNaN(eh) && Math.abs(eh) >= 0.1 ? `${saving ? ", " : ""}${esc(Math.abs(eh).toFixed(1))}h ${eh > 0 ? "longer" : "shorter"}` : "";
  return `<tr><td><strong>${esc(o.route_summary)}</strong><div class="muted">${esc(o.site_or_operator)} · ${esc(o.ticket_type)}${o.transit_document_costs && +o.transit_document_costs > 0 ? ` · <span class="status s-risk">transit document added</span>` : ""}</div>
    <details><summary>Details &amp; cost breakdown</summary><p>${esc(o.airlines_out)}${o.airlines_back && o.airlines_back !== o.airlines_out ? " / " + esc(o.airlines_back) : ""} · ${esc(o.stops)} stops · out ${esc(o.total_travel_time_out)} · back ${esc(o.total_travel_time_back)}</p>
    ${o.layover_details ? `<p>Layovers: ${esc(o.layover_details)}</p>` : ""}${o.ground_out_details ? `<p>Ground out: ${esc(o.ground_out_details)}</p>` : ""}${o.ground_back_details ? `<p>Ground back: ${esc(o.ground_back_details)}</p>` : ""}${o.positioning_flight_details ? `<p>Positioning: ${esc(o.positioning_flight_details)}</p>` : ""}
    ${o.buffers_and_delay_basis ? `<p>Buffers: ${esc(o.buffers_and_delay_basis)}</p>` : ""}<table class="results">${parts.map(([k, v]) => `<tr><td>${k}</td><td class="num">${n0(v)} ${esc(cur)}</td></tr>`).join("")}</table>
    ${o.risks ? `<p class="warning">Risks: ${esc(o.risks)}</p>` : ""}${o.notes ? `<p class="muted">${esc(o.notes)}</p>` : ""}<p class="muted">Original: ${esc(o.original_price_and_currency)} · rate ${esc(o.exchange_rate_and_date)} · checked ${esc(o.checked_at)}</p></details></td>
    <td>${esc(o.depart_datetime)}<br>${esc(o.return_datetime)}${o.nights ? `<div class="muted">${esc(o.nights)} nights</div>` : ""}</td>
    <td class="num"><span class="price" style="font-size:1.1rem">${n0(o.total)} ${esc(cur)}</span><div class="muted">${saving}${extra}</div><span class="status ${o.price_status === "confirmed" ? "s-ok" : "s-risk"}">${o.price_status === "confirmed" ? "Confirmed" : "Fees may be added"}</span></td>
    <td><button type="button" class="btn small primary" data-book="${esc(o.option_id)}">Take me to booking</button></td></tr>`;
}
function table(list, cur) { return `<div class="scroll-x"><table class="results"><thead><tr><th>Route</th><th>Dates</th><th style="text-align:right">Total, all travellers</th><th></th></tr></thead><tbody>${list.map((o) => optionRow(o, cur)).join("")}</tbody></table></div>`; }
function block(v) {
  if (!v) return "";
  if (typeof v === "string") return `<p>${esc(v)}</p>`;
  if (Array.isArray(v)) return v.length && typeof v[0] === "object" ? `<div class="scroll-x"><table class="results"><thead><tr>${Object.keys(v[0]).map((k) => `<th>${esc(k.replace(/_/g, " "))}</th>`).join("")}</tr></thead><tbody>${v.map((r) => `<tr>${Object.entries(r).map(([k, x]) => `<td data-l="${esc(k.replace(/_/g, " "))}">${esc(Array.isArray(x) ? x.join(", ") : x)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : `<ul>${v.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
  return `<ul>${Object.entries(v).map(([k, x]) => `<li><strong>${esc(k.replace(/_/g, " "))}:</strong> ${esc(Array.isArray(x) ? x.join(", ") : x)}</li>`).join("")}</ul>`;
}
async function pollResults() {
  clearTimeout(pollTimer);
  let r;
  try { r = await api("/api/results"); } catch { $("#r-progress").textContent = "Can't reach the local server."; pollTimer = setTimeout(pollResults, 8000); return; }
  const pr = r.progress, res = r.results;
  $("#r-progress").innerHTML = pr ? `${pr.done ? "" : `<span class="spinner"></span>`}<div><strong>${esc(pr.phase || "")}</strong> ${esc(pr.message || "")}<div class="muted">${esc(pr.updated_at || "")}</div></div>` : `<span class="spinner"></span> Waiting for the agent to start the search…`;
  if (res) {
    const cur = res.currency, rep = res.report || {};
    S._holidays = rep.holidays || []; renderWindow();
    const byId = Object.fromEntries([...res.top, ...(res.more || []), ...res.smaller_savings, ...(res.miles || [])].map((o) => [o.option_id, o]));
    const top3 = (rep.top3 && rep.top3.length ? rep.top3 : res.top.slice(0, 3).map((o) => ({ option_id: o.option_id }))).map((t) => ({ ...t, o: byId[t.option_id] })).filter((t) => t.o);
    let h = "";
    if (res.changes) h += `<section class="card"><h2>Changes since the last run</h2>${block(res.changes.items.map((c) => ({ route: c.route, was: c.was == null ? "new" : n0(c.was), now: n0(c.now), change: c.change == null ? "" : (c.change > 0 ? "+" : "") + n0(c.change) })))}</section>`;
    if (rep.documents) h += `<section class="card"><h2>Documents</h2>${block(rep.documents)}</section>`;
    if (rep.season) h += `<section class="card"><h2>Season &amp; weather</h2>${block(rep.season)}</section>`;
    if (top3.length) h += `<h2 style="margin-top:20px">Top picks</h2><div class="picks">${top3.map((t, i) => `<div class="pick"><span class="muted">#${i + 1}</span><strong>${esc(t.o.route_summary)}</strong><span class="price">${n0(t.o.total)} ${esc(cur)}</span>
      <span>${esc(t.reason || "")}</span>${t.risks ? `<span class="warning">${esc(t.risks)}</span>` : ""}<button type="button" class="btn primary" data-book="${esc(t.o.option_id)}">Take me to booking</button></div>`).join("")}</div>`;
    if (res.direct) h += `<p class="muted">Direct round trip from ${esc(res.closest_airport)}: ${n0(res.direct.total)} ${esc(cur)} (${esc(res.direct.route_summary)}).</p>`;
    h += `<section class="card"><h2>Top ${res.top.length} door-to-door options</h2>${table(res.top, cur)}</section>`;
    if (res.miles?.length) h += `<section class="card"><h2>Miles &amp; points options</h2>${table(res.miles, cur)}</section>`;
    if (res.smaller_savings?.length) h += `<details><summary>Smaller savings (${res.smaller_savings.length}) — below your ${n0(res.min_saving)} ${esc(cur)} minimum</summary>${table(res.smaller_savings, cur)}</details>`;
    if (rep.decisions_needed && rep.decisions_needed.length) h += `<section class="card" style="border-color:var(--warn)"><h2>Needs your decision</h2>${block(rep.decisions_needed)}</section>`;
    if (rep.tools) h += `<section class="card"><h2>Tools &amp; sites</h2>${block(rep.tools)}</section>`;
    if (rep.checkout_check) h += `<section class="card"><h2>Double-check at checkout</h2>${block(rep.checkout_check)}</section>`;
    if (rep.alerts) h += `<section class="card"><h2>Price tracking</h2>${block(rep.alerts)}</section>`;
    if (res.warnings?.length) h += `<details><summary>Merge warnings (${res.warnings.length})</summary>${block(res.warnings)}</details>`;
    $("#r-body").innerHTML = h;
    $$("[data-book]").forEach((b) => b.addEventListener("click", () => book(b.dataset.book)));
  }
  try { const bs = await api("/api/booking-status"); if (bs.message) toast(bs.message, 6000); } catch {}
  if (!(pr && pr.done && res)) pollTimer = setTimeout(pollResults, 4000);
}
async function book(id) {
  try { await api("/api/book", { option_id: id }); toast("Sent to the agent: it re-opens the site, re-selects these flights and stops at passenger details for you.", 7000); }
  catch (e) { toast("Couldn't reach the agent: " + e.message); }
}

/* ---------- navigation ---------- */
function go(page) {
  if (!PAGES.includes(page)) page = "trip";
  PAGES.forEach((p) => ($(`#page-${p}`).hidden = p !== page));
  $$("nav.steps button").forEach((b) => (b.dataset.go === page ? b.setAttribute("aria-current", "step") : b.removeAttribute("aria-current")));
  const i = PAGES.indexOf(page);
  $$(".js-back").forEach((b) => (b.hidden = i === 0));
  $$(".js-next").forEach((b) => { b.hidden = page === "results"; b.textContent = page === "check" ? "Start search" : "Next →"; });
  if (location.hash !== "#" + page) history.replaceState(null, "", "#" + page);
  if (page === "travellers") { renderTravellers(); loadDestDocs(); }
  if (page === "check") runDocCheck(false);
  if (page === "results") pollResults(); else clearTimeout(pollTimer);
  window.scrollTo({ top: 0 });
  updateNav();
}
// Next is only usable once everything up to and including this page is filled in.
function updateNav() {
  const page = location.hash.slice(1) || "trip", i = PAGES.indexOf(page);
  if (i < 0 || page === "results") { $$(".nav-hint").forEach((h) => (h.textContent = "")); return; }
  const p = problems().filter(([pg]) => PAGES.indexOf(pg) <= i);
  $$(".js-next").forEach((b) => (b.disabled = p.length > 0));
  $$(".nav-hint").forEach((h) => (h.textContent = p.length ? p[0][1] : ""));
}
function setupNav() {
  $$("nav.steps button").forEach((b) => b.addEventListener("click", () => go(b.dataset.go)));
  $$(".js-back").forEach((b) => b.addEventListener("click", () => go(PAGES[Math.max(0, PAGES.indexOf(location.hash.slice(1)) - 1)])));
  $$(".js-next").forEach((b) => b.addEventListener("click", () => { const cur = location.hash.slice(1) || "trip"; if (cur === "check") start(); else go(PAGES[PAGES.indexOf(cur) + 1]); }));
  $("#save-file").addEventListener("click", () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(S, null, 1)], { type: "application/json" }));
    a.download = `fair-fares-settings-${new Date().toISOString().slice(0, 10)}.json`; a.click(); URL.revokeObjectURL(a.href);
  });
  $("#load-file").addEventListener("change", async (e) => {
    const f = e.target.files[0]; if (!f) return;
    try { S = merge(DEFAULTS(), JSON.parse(await f.text())); fillAll(); autosave(); toast("Settings loaded."); } catch { toast("That file isn't a Fair Fares settings file."); }
    e.target.value = "";
  });
  document.querySelector('label[for="load-file"]').addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#load-file").click(); } });
  window.addEventListener("hashchange", () => go(location.hash.slice(1)));
}

/* ---------- boot ---------- */
(async function boot() {
  const get = (n) => fetch(`/data/${n}.json`).then((r) => r.json());
  const [countries, states, cities, airports, currencies, rules, meta, saved] = await Promise.all([get("countries"), get("states"), get("cities"), get("airports"), get("currencies"), get("doc_rules"), api("/api/meta"), api("/api/settings")]);
  Object.assign(D, { countries: countries.sort((a, b) => a[1].localeCompare(b[1])), states, airports, currencies, rules, fx: meta.fx });
  D.countryBy = Object.fromEntries(countries.map((c) => [c[0], { name: c[1], currency: c[2] }]));
  D.apBy = Object.fromEntries(airports.map((a) => [a[0], a]));
  D.cities = cities.map((v, i) => ({ v, i }));
  D.cityNorm = cities.map((c) => ({ name: norm(c[0]), alt: norm(c[1]), region: norm(c[2]), country: norm(D.countryBy[c[3]]?.name) }));
  S = merge(DEFAULTS(), saved || {});
  setupTrip(); setupTravellers(); setupPrefs(); setupNav(); fillAll();
  go(location.hash.slice(1) || "trip");
})().catch((e) => { document.body.insertAdjacentHTML("afterbegin", `<p class="warning" style="padding:16px">Couldn't load the form data: ${esc(e.message)}</p>`); });
