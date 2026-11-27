#!/usr/bin/env python3
"""One daily reference rate for the whole run (ECB euro foreign exchange reference rates).

  python3 fx.py [--to EUR]                 -> fetch today's ECB rates once, save ~/.fair-fares/fx.json (+ run folder)
  python3 fx.py --convert 120 USD --to EUR -> print converted amount using the saved rates

Cross rates go through EUR. ECB publishes ~30 currencies; for others the agent records the rate it used
in exchange_rate_and_date by hand (e.g. from the card network's published rate).
"""
import json, sys, os, urllib.request, xml.etree.ElementTree as ET, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import STATE, read_json, write_json, current_run

URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"


def fetch():
    xml = urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "fair-fares"}), timeout=20).read()
    root = ET.fromstring(xml)
    rates, date = {"EUR": 1.0}, None
    for el in root.iter():
        if el.get("time"):
            date = el.get("time")
        if el.get("currency"):
            rates[el.get("currency")] = float(el.get("rate"))
    return {"source": URL, "date": date, "base": "EUR", "rates": rates,
            "fetched": datetime.datetime.now().isoformat(timespec="seconds")}


def convert(amount, frm, to, fx):
    r = fx["rates"]
    if frm not in r or to not in r:
        return None
    return round(amount / r[frm] * r[to], 2)


def main():
    a = sys.argv[1:]
    to = a[a.index("--to") + 1] if "--to" in a else "EUR"
    if "--convert" in a:
        i = a.index("--convert")
        fx = read_json(STATE / "fx.json") or fetch()
        v = convert(float(a[i + 1]), a[i + 2].upper(), to.upper(), fx)
        print(json.dumps({"amount": v, "currency": to.upper(), "rate_date": fx["date"], "basis": "ECB reference"}))
        return 0
    fx = fetch()
    write_json(STATE / "fx.json", fx)
    run = current_run()
    if run:
        write_json(run / "fx.json", fx)
    print(json.dumps({"date": fx["date"], "currencies": len(fx["rates"]), "has_target": to.upper() in fx["rates"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
