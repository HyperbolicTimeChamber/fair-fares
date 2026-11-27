#!/usr/bin/env python3
"""Merge subagent CSVs into all_options.csv + results.json (read by the form's results page).

  python3 merge_results.py [--run PATH]

Reads results/*.csv (shared schema), fills missing totals, de-duplicates (keeps cheapest source),
computes saving and extra time vs the direct round trip from the closest airport, applies the
minimum-saving rule, ranks by total door-to-door cost for all travellers, and diffs against the
previous run. Narrative parts the lead agent writes (documents summary, season note, top-3 reasons,
tools that worked/blocked, alerts) go in report.json in the run folder and are copied into results.json.
"""
import csv, glob, json, os, re, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ASSETS, read_json, write_json, current_run
import pathlib

COLS = (ASSETS / "results_schema.csv").read_text().strip().split(",")
COST_PARTS = ["flight_cost", "ground_cost", "destination_transfer_cost", "hotel_cost", "document_costs",
              "transit_document_costs", "insurance_estimate", "bag_fees", "payment_fees", "extras_cost"]
ALT_TYPES = {"separate_one_ways", "self_transfer", "open_jaw"}


def num(v):
    if v is None:
        return None
    m = re.search(r"-?\d[\d,]*\.?\d*", str(v).replace(" ", ""))
    if not m:
        return None
    s = m.group(0)
    s = s.replace(",", "") if s.count(",") and s.count(".") else s.replace(",", ".") if s.count(",") == 1 and len(s.split(",")[1]) == 2 else s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def hours(v):
    """'14h 35m', '14:35', '14.5' -> hours."""
    if not v:
        return None
    s = str(v)
    m = re.match(r"\s*(\d+)\s*h(?:\D+(\d+)\s*m)?", s)
    if m:
        return int(m.group(1)) + int(m.group(2) or 0) / 60
    m = re.match(r"\s*(\d+):(\d{2})", s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 60
    return num(s)


def key(r):
    return tuple((r.get(c) or "").strip().upper()[:16] for c in
                 ["airlines_out", "airlines_back", "depart_airport", "arrive_airport", "return_from_airport",
                  "return_to_airport", "depart_datetime", "return_datetime", "ticket_type", "hotel_name"])


def main():
    a = sys.argv[1:]
    run = pathlib.Path(a[a.index("--run") + 1]) if "--run" in a else current_run()
    if not run:
        print(json.dumps({"error": "no current run"})); return 1
    s = read_json(run / "settings.json", {}) or {}
    prefs = s.get("prefs", {})
    trip = s.get("trip", {})
    closest = (trip.get("closest_airport") or {}).get("code", "").upper()
    min_saving = num(trip.get("alternatives", {}).get("min_saving")) or 0
    currency = prefs.get("currency") or ""
    rows, warnings, sources = [], [], {}
    for f in sorted(glob.glob(str(run / "results" / "*.csv"))):
        if os.path.basename(f) == "SCHEMA.csv":
            continue
        with open(f, newline="", encoding="utf-8") as fh:
            rd = csv.DictReader(fh)
            extra = set(rd.fieldnames or []) - set(COLS)
            if extra:
                warnings.append(f"{os.path.basename(f)}: ignored columns {sorted(extra)}")
            n = 0
            for r in rd:
                r = {c: (r.get(c) or "").strip() for c in COLS}
                if not r["source_agent"]:
                    r["source_agent"] = os.path.basename(f).split(".")[0]
                tot = num(r["total_cost_all_travellers"])
                if tot is None:
                    parts = [num(r[c]) for c in COST_PARTS]
                    if parts[0] is None:
                        warnings.append(f"{os.path.basename(f)}: row without flight_cost/total skipped")
                        continue
                    tot = sum(p for p in parts if p)
                    r["total_cost_all_travellers"] = f"{tot:.2f}"
                r["_total"] = tot
                if not r["nights"]:
                    try:
                        r["nights"] = str((datetime.date.fromisoformat(r["return_datetime"][:10]) - datetime.date.fromisoformat(r["depart_datetime"][:10])).days)
                    except ValueError:
                        pass
                if currency and r["currency"] and r["currency"].upper() != currency.upper():
                    warnings.append(f"{r['option_id']}: currency {r['currency']} != {currency} (convert with fx.py)")
                rows.append(r)
                n += 1
            sources[os.path.basename(f)] = n
    # De-duplicate: keep the cheapest source for the same itinerary.
    best = {}
    fare = lambda r: (num(r["flight_cost"]) or r["_total"]) + (num(r["bag_fees"]) or 0)
    for r in rows:
        k = key(r)
        if k not in best:
            best[k] = r
            continue
        keep, other = (r, best[k]) if fare(r) < fare(best[k]) else (best[k], r)
        # Same itinerary: keep the cheaper fare, carry over cost parts only the other source priced, re-total.
        filled = False
        for c in COST_PARTS[1:]:
            if not keep[c] and other[c]:
                keep[c], filled = other[c], True
        if filled:
            keep["_total"] = sum(num(keep[c]) or 0 for c in COST_PARTS)
            keep["total_cost_all_travellers"] = f"{keep['_total']:.2f}"
        keep["notes"] = (keep["notes"] + f" | also on {other['site_or_operator']}: fare {fare(other):.0f}").strip(" |")
        best[k] = keep
    rows = sorted(best.values(), key=lambda r: r["_total"])
    # Direct baseline: simple round trip from/to the closest airport, no ground legs or positioning flight.
    def is_direct(r):
        return (r["ticket_type"] in ("round_trip", "") and (not closest or (r["depart_airport"].upper() == closest
                and (r["return_to_airport"] or r["depart_airport"]).upper() == closest))
                and not r["ground_out_details"] and not r["positioning_flight_details"])
    directs = [r for r in rows if is_direct(r)]
    direct = directs[0] if directs else None
    for r in rows:
        alt = (not is_direct(r)) and (r["ticket_type"] in ALT_TYPES or (closest and r["depart_airport"].upper() != closest)
                                      or r["positioning_flight_details"] or r["ground_out_details"])
        r["_alt"] = bool(alt)
        if direct and not r["saving_vs_direct"]:
            r["saving_vs_direct"] = f"{direct['_total'] - r['_total']:.2f}"
        if direct and r is not direct and not r["extra_time_vs_direct"]:
            ho = [hours(r["total_travel_time_out"]), hours(r["total_travel_time_back"])]
            hd = [hours(direct["total_travel_time_out"]), hours(direct["total_travel_time_back"])]
            if None not in ho + hd:
                r["extra_time_vs_direct"] = f"{(ho[0] + ho[1]) - (hd[0] + hd[1]):.1f}h"
        sv = num(r["saving_vs_direct"])
        r["_bucket"] = "smaller_savings" if (alt and direct and min_saving and (sv is None or sv < min_saving)) else "main"
    main_rows = [r for r in rows if r["_bucket"] == "main"]
    small = [r for r in rows if r["_bucket"] == "smaller_savings"]
    # Write all_options.csv (ranked).
    with open(run / "all_options.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["rank", "bucket"] + COLS)
        for i, r in enumerate(main_rows + small, 1):
            w.writerow([i, r["_bucket"]] + [r[c] for c in COLS])
    clean = lambda r: {**{c: r[c] for c in COLS}, "total": r["_total"], "alternative": r["_alt"]}
    out = {"generated_at": datetime.datetime.now().isoformat(timespec="seconds"), "currency": currency,
           "min_saving": min_saving, "closest_airport": closest, "direct": clean(direct) if direct else None,
           "top": [clean(r) for r in main_rows[:10]], "more": [clean(r) for r in main_rows[10:40]],
           "smaller_savings": [clean(r) for r in small[:30]],
           "miles": [clean(r) for r in rows if r["miles_option"]][:10],
           "counts": {"options": len(rows), "files": sources}, "warnings": warnings,
           "report": read_json(run / "report.json", {}) or {}}
    # What changed since the previous run.
    prev = read_json(run / "previous_run.json")
    if prev:
        pr = read_json(pathlib.Path(prev["path"]) / "results.json")
        if pr:
            old = {tuple(o.get(c, "") for c in ["route_summary", "depart_datetime", "return_datetime"]): o["total"]
                   for o in pr.get("top", []) + pr.get("more", [])}
            ch = []
            for o in out["top"]:
                k = (o["route_summary"], o["depart_datetime"], o["return_datetime"])
                ch.append({"option_id": o["option_id"], "route": o["route_summary"],
                           "was": old.get(k), "now": o["total"],
                           "change": None if k not in old else round(o["total"] - old[k], 2)})
            out["changes"] = {"previous_run": prev["path"], "items": ch}
    write_json(run / "results.json", out)
    print(json.dumps({"options": len(rows), "main": len(main_rows), "smaller_savings": len(small),
                      "direct_total": direct["_total"] if direct else None,
                      "cheapest": main_rows[0]["route_summary"] if main_rows else None, "warnings": warnings[:10]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
