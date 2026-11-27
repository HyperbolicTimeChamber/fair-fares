#!/usr/bin/env python3
"""Travel-document first pass for the form's page 3.

Step 1: embedded visa dataset + curated rules (instant, no model).
Step 2: only for questions the data can't answer, ask the agent's small model via its CLI
        (configured by setup_check.py in ~/.fair-fares/config.json) and require JSON back.

CLI:  python3 doc_check.py request.json   -> prints result JSON
"""
import json, hashlib, re, subprocess, sys, datetime, shutil
from common import DATA, STATE, read_json, write_json, parse_date, today, config

RANK = {"SELF": 0, "VF": 1, "ETA": 2, "VOA": 3, "EV": 4, "VR": 5, "NA": 6}
LABEL = {"SELF": "Own country", "VF": "Visa-free", "ETA": "Electronic travel authorisation needed",
         "VOA": "Visa on arrival", "EV": "e-Visa needed", "VR": "Visa required", "NA": "No admission"}

_visa = _rules = _countries = None


def load():
    global _visa, _rules, _countries
    if _visa is None:
        _visa = read_json(DATA / "visa.json", {})
        _rules = read_json(DATA / "doc_rules.json", {})
        _countries = {c[0]: c[1] for c in read_json(DATA / "countries.json", [])}
    return _visa, _rules, _countries


def norm_status(v):
    if isinstance(v, int):
        return "VF", v
    return (v or "UNKNOWN"), None


def rule_for(dest):
    _, rules, _ = load()
    d = rules.get("destinations", {})
    if dest in d:
        return dest, d[dest]
    if dest in rules.get("groups", {}).get("SCHENGEN", []):
        return "SCHENGEN", d.get("SCHENGEN")
    return None, None


def doc_country_matches(doc_country, dest):
    _, rules, _ = load()
    if not doc_country:
        return False
    if doc_country == dest:
        return True
    return doc_country == "SCHENGEN" and dest in rules["groups"]["SCHENGEN"]


def catalog():
    _, rules, _ = load()
    return {c["id"]: c for c in rules.get("catalog", [])}


def destination_documents(dest, has_children=False):
    """Documents the form should offer on page 2 for this destination (rules first)."""
    _, rules, names = load()
    key, rule = rule_for(dest)
    out, seen = [], set()
    if rule:
        for d in rule.get("documents", []):
            out.append({"id": d["id"], "label": d["label"], "source": "rules"})
            seen.add(d["id"])
    for c in rules.get("catalog", []):
        if c["id"] not in seen and doc_country_matches(c.get("country"), dest):
            out.append({"id": c["id"], "label": c["label"], "source": "catalog"})
            seen.add(c["id"])
    if not any(o["id"].endswith("passport") for o in out):
        out.append({"id": f"{dest.lower()}_passport", "label": f"{names.get(dest, dest)} passport", "source": "generic"})
    if not rule or rule.get("onward_travel"):
        if rule and rule.get("onward_travel"):
            out.append({"id": "onward_ticket", "label": "Proof of onward travel", "source": "rules"})
    if has_children:
        out.append({"id": "child_consent", "label": "Child travel consent letter", "source": "generic"})
    return {"destination": dest, "rules_key": key, "documents": out, "covered_by_rules": bool(rule)}


def months_after(d, m):
    y, mo = divmod(d.month - 1 + m, 12)
    import calendar
    yy, mm = d.year + y, mo + 1
    return datetime.date(yy, mm, min(d.day, calendar.monthrange(yy, mm)[1]))


def check(req):
    """req: {destination:'IN', earliest_departure, return_by, travellers:[{id,name,child,passports:[{country,expiry}]}],
             documents:[{id,label,applies_to:[ids]}]}"""
    visa, rules, names = load()
    dest = req["destination"]
    key, rule = rule_for(dest)
    dep = parse_date(req.get("earliest_departure")) or today()
    ret = parse_date(req.get("return_by")) or dep
    days_left = (dep - today()).days
    meta = read_json(DATA / "meta.json", {})
    held = {}
    for d in req.get("documents", []):
        for t in d.get("applies_to", []):
            held.setdefault(t, set()).add(d["id"])
    items, unresolved = [], []
    cat = catalog()
    rule_docs = {d["id"]: d for d in (rule or {}).get("documents", [])}

    def add(t, doc_id, label, status, src, doc=None, note=""):
        doc = doc or {}
        it = {"traveller": t["id"], "traveller_name": t.get("name") or t["id"], "doc_id": doc_id, "label": label,
              "status": status, "source": src, "note": note or doc.get("note", ""),
              "fee": doc.get("fee"), "processing_days": doc.get("processing_days"),
              "official": doc.get("official") or ((rule or {}).get("official") or [None])[0]}
        pd = doc.get("processing_days")
        if status in ("Missing", "At risk") and pd:
            need = pd[1] + doc.get("apply_before_days", 0)
            if need >= days_left:
                it["warning"] = f"Processing can take up to {pd[1]} days; your earliest departure is in {days_left} days."
        items.append(it)

    for t in req.get("travellers", []):
        pps = [p for p in t.get("passports", []) if p.get("country")]
        mine = held.get(t["id"], set())
        if not pps:
            add(t, "passport", "Passport", "Missing", "form", note="Add a passport country.")
            continue
        # Best passport for this destination.
        best = None
        for p in pps:
            s, days = norm_status(visa.get(p["country"], {}).get(dest, "SELF" if p["country"] == dest else None))
            cand = (RANK.get(s, 9), s, days, p)
            if best is None or cand[0] < best[0]:
                best = cand
        _, s, days, p = best
        # Passport validity.
        months = (rule or {}).get("passport_validity_months", rules["generic"]["passport_validity_months"])
        exp = parse_date(p.get("expiry"))
        if s != "SELF":
            if not exp:
                add(t, "passport_validity", f"{names.get(p['country'], p['country'])} passport validity", "At risk", "rules",
                    note=f"Add the expiry date. {dest} usually needs validity of {months} months beyond your stay." if months else "Add the expiry date.")
            elif exp < ret:
                add(t, "passport_validity", "Passport expires before you're back", "Missing", "rules",
                    {"processing_days": [10, 42]}, note=f"Expires {exp.isoformat()}; renew before travel.")
            elif months and exp < months_after(ret, months):
                add(t, "passport_validity", "Passport validity", "At risk", "rules", {"processing_days": [10, 42]},
                    note=f"Expires {exp.isoformat()}; {months} months beyond the return date is usually required.")
            else:
                add(t, "passport_validity", "Passport validity", "OK", "rules", note=f"Valid until {exp.isoformat()}.")
        # Entry status.
        replaced = [d for d in mine if (rule_docs.get(d, {}).get("replaces_visa")
                    or (d in cat and cat[d].get("kind") == "residence" and doc_country_matches(cat[d].get("country"), dest)))]
        base = f"{LABEL.get(s, s)}" + (f" ({days} days)" if days else "") + f" with {names.get(p['country'], p['country'])} passport"
        if s == "SELF":
            add(t, "entry", "Entry as citizen", "OK", "dataset", note=base)
        elif replaced:
            lbl = rule_docs.get(replaced[0], cat.get(replaced[0], {})).get("label", replaced[0])
            add(t, "entry", "Entry", "OK", "rules", note=f"Covered by {lbl}. Dataset says: {base}.")
        elif s == "NA":
            add(t, "entry", "Entry", "Missing", "dataset", note=base + ". Check official sources.")
        elif s == "UNKNOWN":
            unresolved.append({"traveller": t, "question": "entry status", "passport": p["country"]})
        else:
            # Which document fulfils this status?
            need = None
            for d in rule_docs.values():
                if s in d.get("for_status", []) or (s in ("VR", "EV", "VOA") and d.get("visa_doc")):
                    need = d
                    break
            if need:
                st = "OK" if need["id"] in mine else ("Missing" if s in ("VR", "EV", "ETA") else "At risk")
                if s == "VF" and need["id"] not in mine:
                    st = "At risk"  # e.g. ETIAS / K-ETA / Visit Japan Web: check if it applies
                add(t, need["id"], need["label"], st, "rules", need, note=base)
            elif s == "VF":
                add(t, "entry", "Entry", "OK", "dataset", note=base)
            elif s == "VOA":
                add(t, "entry", "Visa on arrival", "At risk", "dataset", note=base + "; fee payable on arrival.")
                unresolved.append({"traveller": t, "question": "visa on arrival fee", "passport": p["country"]})
            else:
                add(t, "entry", LABEL.get(s, s), "Missing", "dataset", note=base)
                unresolved.append({"traveller": t, "question": f"{LABEL.get(s, s)}: fee and processing time", "passport": p["country"]})
        # Special documents the rules file doesn't understand for this destination.
        for d in mine:
            if d not in rule_docs and d not in cat and d != "child_consent":
                unresolved.append({"traveller": t, "question": f"effect of document '{d}'", "passport": p["country"]})
        if t.get("child") and ((rule or {}).get("child_consent") or not rule):
            st = "OK" if "child_consent" in mine else "At risk"
            add(t, "child_consent", rules["generic"]["child_consent"]["label"], st, "rules", rules["generic"]["child_consent"],
                note=(rule or {}).get("child_note", "Needed if the child travels without both parents or guardians."))
    if not rule:
        for t in req.get("travellers", []):
            if not any(u["traveller"]["id"] == t["id"] for u in unresolved):
                unresolved.append({"traveller": t, "question": "other entry requirements (e-arrival cards, fees, onward ticket)",
                                   "passport": (t.get("passports") or [{}])[0].get("country")})
    return items, unresolved, meta.get("datasets", {}).get("visa", {}).get("date")


PROMPT = """You are a travel-document assistant. Answer ONLY with a JSON array, no prose.
Destination country: {dest}. Earliest departure: {dep}. Return by: {ret}. Today: {today}.
For each question, return one object: {{"traveller": id, "doc_id": short_snake_id, "label": text,
"status": "OK"|"Missing"|"At risk", "fee": {{"amount": number, "currency": "ISO"}} or null,
"processing_days": [min, max] or null, "official": official government URL or null, "note": short text}}.
Be conservative: if unsure, use "At risk" and say what to verify. Questions:
{questions}"""


def model_cmd():
    cfg = config().get("doc_model") or {}
    cmd = cfg.get("cmd")
    if not cmd or cfg.get("mode") == "chat":
        return None
    if not shutil.which(cmd[0]):
        return None
    return cmd


def ask_model(req, unresolved):
    cmd = model_cmd()
    if not cmd or not unresolved:
        return None, "no_model" if unresolved else "not_needed"
    qs = [{"traveller": u["traveller"]["id"], "passports": [p.get("country") for p in u["traveller"].get("passports", [])],
           "child": bool(u["traveller"].get("child")), "question": u["question"],
           "documents_held": [d["id"] for d in req.get("documents", []) if u["traveller"]["id"] in d.get("applies_to", [])]}
          for u in unresolved]
    prompt = PROMPT.format(dest=req["destination"], dep=req.get("earliest_departure"), ret=req.get("return_by"),
                           today=today().isoformat(), questions=json.dumps(qs))
    full = [a.replace("{prompt}", prompt) for a in cmd]
    if "{prompt}" not in " ".join(cmd):
        full.append(prompt)
    try:
        out = subprocess.run(full, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL).stdout
    except Exception as e:
        return None, f"model_error: {e}"
    m = re.search(r"\[.*\]", out, re.S)
    if not m:
        return None, "model_no_json"
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None, "model_bad_json"
    clean = []
    for d in data if isinstance(data, list) else []:
        if isinstance(d, dict) and d.get("status") in ("OK", "Missing", "At risk"):
            d["source"] = "model"
            clean.append(d)
    return clean, "ok"


def run(req, use_model=True, force=False):
    key = hashlib.sha256(json.dumps(req, sort_keys=True).encode()).hexdigest()[:16]
    cache = read_json(STATE / "doccheck_cache.json", {}) or {}
    if not force and key in cache:
        r = cache[key]
        r["cached"] = True
        return r
    items, unresolved, visa_date = check(req)
    model_items, model_status = (None, "skipped")
    if use_model:
        model_items, model_status = ask_model(req, unresolved)
    pending = []
    if model_items:
        items.extend(model_items)
    elif unresolved:
        pending = [{"traveller": u["traveller"]["id"], "question": u["question"]} for u in unresolved]
    agent = config().get("agent")
    result = {"key": key, "items": items, "pending": pending, "model_status": model_status,
              "visa_dataset_date": visa_date, "checked_at": datetime.datetime.now().isoformat(timespec="seconds"),
              "agent": agent}
    cache[key] = result
    if len(cache) > 50:
        cache = dict(list(cache.items())[-50:])
    write_json(STATE / "doccheck_cache.json", cache)
    return result


if __name__ == "__main__":
    req = read_json(sys.argv[1])
    print(json.dumps(run(req, force="--force" in sys.argv), indent=1, ensure_ascii=False))
