#!/usr/bin/env python3
"""Pre-filled search links (fallback when no browser plugin works, and for fare alerts).

  python3 links.py --from BER --to GOI --out 2027-03-06 --back 2027-03-20 --adults 2 --children 8,5 --cabin economy --currency EUR
  python3 links.py ... --one-way        (omit --back)

Prints JSON {site: url}. Links open a search; they never book anything.
"""
import json, sys
from urllib.parse import quote

CABIN = {"economy": ("economy", "e"), "premium": ("premiumeconomy", "p"), "business": ("business", "b"), "first": ("first", "f")}


def build(frm, to, out, back=None, adults=1, children=(), cabin="economy", currency="EUR"):
    sky_cab, kay_cab = CABIN.get(cabin, CABIN["economy"])
    d1 = out.replace("-", "")[2:]
    d2 = back.replace("-", "")[2:] if back else ""
    kids = "|".join(str(c) for c in children)
    sky = f"https://www.skyscanner.net/transport/flights/{frm.lower()}/{to.lower()}/{d1}/" + (f"{d2}/" if back else "")
    sky += f"?adultsv2={adults}&cabinclass={sky_cab}&rtn={1 if back else 0}" + (f"&childrenv2={quote(kids)}" if kids else "")
    pax = f"{adults}adults" + (f"/children-{'-'.join(str(c) for c in children)}" if children else "")
    path = f"{frm.upper()}-{to.upper()}/{out}" + (f"/{back}" if back else "")
    cab = "" if kay_cab == "e" else f"/{ {'p': 'premium', 'b': 'business', 'f': 'first'}[kay_cab] }".replace(" ", "")
    q = f"Flights from {frm} to {to} on {out}" + (f" through {back}" if back else " one way") + \
        f" {adults} adults" + (f" {len(children)} children" if children else "") + (f" {cabin}" if cabin != "economy" else "")
    return {
        "google_flights": f"https://www.google.com/travel/flights?q={quote(q)}&curr={currency}&hl=en",
        "skyscanner": sky,
        "kayak": f"https://www.kayak.com/flights/{path}{cab}/{pax}?sort=price_a",
        "momondo": f"https://www.momondo.com/flight-search/{path}{cab}/{pax}?sort=price_a",
    }


def main():
    a = sys.argv[1:]
    g = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    kids = [int(x) for x in (g("--children", "") or "").split(",") if x.strip()]
    print(json.dumps(build(g("--from"), g("--to"), g("--out"), g("--back"), int(g("--adults", 1)), kids,
                           g("--cabin", "economy"), g("--currency", "EUR")), indent=1))


if __name__ == "__main__":
    main()
