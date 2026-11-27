#!/usr/bin/env python3
"""Broad date scan on Google Flights with Playwright — fallback when Kiwi.com isn't connectable.

LOW VOLUME BY DESIGN: visible browser, one tab, randomised 4-10 s pauses, --max-queries (default 30).
Stops immediately at any CAPTCHA / "unusual traffic" page and logs it. Never tries to get around a block.
Consent banners: clicks "Reject all" (most private option).

  python3 gflights_scan.py --from BER --to GOI,GOX --earliest 2027-03-06 --latest 2027-04-25 \
      --min-nights 7 --max-nights 21 --adults 2 --children 8 --currency EUR --max-stops 2 \
      --out RUN/results/A_gflights.csv [--max-queries 30] [--headless]

Writes rows in the shared schema (flight_cost only; the lead agent adds the rest) and prints a short summary.
"""
import csv, datetime, json, os, random, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ASSETS
from links import build

COLS = (ASSETS / "results_schema.csv").read_text().strip().split(",")
PRICE_RE = re.compile(r"From ([\d,\.]+) ([A-Za-z ]+?) round trip total|From ([\d,\.]+) ([A-Za-z ]+?)\.", re.I)


def date_pairs(earliest, latest, nmin, nmax, cap):
    e, l = datetime.date.fromisoformat(earliest), datetime.date.fromisoformat(latest)
    lengths = sorted({nmin, (nmin + nmax) // 2, nmax})
    pairs = []
    d = e
    step = max(1, ((l - e).days - nmin) // max(1, cap // len(lengths)))
    while d <= l:
        for n in lengths:
            r = d + datetime.timedelta(days=n)
            if r <= l:
                pairs.append((d.isoformat(), r.isoformat()))
        d += datetime.timedelta(days=step)
    random.shuffle(pairs)
    return pairs[:cap]


def parse_label(lbl):
    m = PRICE_RE.search(lbl)
    if not m:
        return None
    price = float((m.group(1) or m.group(3)).replace(",", ""))
    stops = 0 if "Nonstop" in lbl else int((re.search(r"(\d+) stops?", lbl) or [0, 0])[1])
    air = re.search(r"flight with ([^\.]+)\.", lbl)
    dur = re.search(r"Total duration ([\d hrmin]+)", lbl)
    lay = re.findall(r"Layover \(\d+ of \d+\) is a ([^\.]+)\.", lbl)
    return {"price": price, "stops": stops, "airlines": air.group(1) if air else "",
            "duration": dur.group(1).replace(" hr", "h").replace(" min", "m") if dur else "", "layovers": "; ".join(lay)}


def main():
    a = sys.argv[1:]
    g = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(json.dumps({"error": "playwright not installed (see setup check)"})); return 1
    frm, tos = g("--from").split(","), g("--to").split(",")
    adults, kids = int(g("--adults", 1)), [int(x) for x in (g("--children", "") or "").split(",") if x]
    cur, cap, max_stops = g("--currency", "EUR"), int(g("--max-queries", 30)), int(g("--max-stops", 9))
    pairs = date_pairs(g("--earliest"), g("--latest"), int(g("--min-nights", 7)), int(g("--max-nights", 14)), cap)
    jobs = [(f, t, o, r) for (o, r) in pairs for f in frm for t in tos][:cap]
    out = g("--out")
    rows, log, blocked = [], [], None
    with sync_playwright() as p:
        br = p.chromium.launch(headless="--headless" in a)
        page = br.new_page(locale="en-GB")
        for i, (f, t, o, r) in enumerate(jobs):
            url = build(f, t, o, r, adults, kids, "economy", cur)["google_flights"]
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                if "consent.google" in page.url:
                    btn = page.get_by_role("button", name=re.compile("Reject all", re.I))
                    if btn.count():
                        btn.first.click()
                        page.wait_for_load_state("domcontentloaded")
                if "/sorry/" in page.url or page.get_by_text(re.compile("unusual traffic", re.I)).count():
                    blocked = f"Block/CAPTCHA at query {i + 1}; stopped."
                    break
                page.wait_for_selector('[aria-label*="round trip total"]', timeout=25000)
                labels = page.eval_on_selector_all('[aria-label*="round trip total"]', "els => els.map(e => e.getAttribute('aria-label'))")
            except Exception as ex:
                log.append(f"{f}-{t} {o}/{r}: {ex.__class__.__name__}")
                labels = []
            seen = 0
            for lbl in labels:
                d = parse_label(lbl or "")
                if not d or d["stops"] > max_stops:
                    continue
                rows.append({c: "" for c in COLS} | {
                    "option_id": f"A-gf-{len(rows) + 1}", "source_agent": "A", "site_or_operator": "Google Flights",
                    "route_summary": f"{f}→{t} {o} / {t}→{f} {r}", "airlines_out": d["airlines"], "airlines_back": d["airlines"],
                    "depart_airport": f, "arrive_airport": t, "return_from_airport": t, "return_to_airport": f,
                    "depart_datetime": o, "return_datetime": r,
                    "nights": str((datetime.date.fromisoformat(r) - datetime.date.fromisoformat(o)).days),
                    "layover_details": d["layovers"], "total_travel_time_out": d["duration"], "stops": str(d["stops"]),
                    "ticket_type": "round_trip", "flight_cost": f"{d['price']:.2f}", "currency": cur,
                    "price_status": "fees_may_be_added", "link": url,
                    "checked_at": datetime.datetime.now().isoformat(timespec="minutes"),
                    "notes": "broad scan; outbound duration only; verify bags/fare type"})
                seen += 1
                if seen >= 3:
                    break
            time.sleep(random.uniform(4, 10))
        br.close()
    if out:
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=COLS)
            w.writeheader()
            w.writerows(rows)
    best = sorted(rows, key=lambda r: float(r["flight_cost"]))[:5]
    print(json.dumps({"queries": len(jobs), "rows": len(rows), "blocked": blocked, "errors": log[:5],
                      "best5": [(r["route_summary"], r["flight_cost"], r["airlines_out"]) for r in best]}, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
