#!/usr/bin/env python3
"""Download the open datasets and rebuild the compact files in assets/data/.

Usage:
  python3 update_data.py            # rebuild everything
  python3 update_data.py --visa     # refresh only the visa dataset (newest source wins)
  python3 update_data.py --check    # print dataset dates as JSON, download nothing

Python standard library only. Writes assets/data/meta.json with source, licence and date.
"""
import csv, io, json, math, re, sys, urllib.request, zipfile, datetime, os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "assets", "data")
UA = {"User-Agent": "fair-fares-skill/1.0 (data refresh)"}

CSC = "https://raw.githubusercontent.com/dr5hn/countries-states-cities-database/master/csv/"
GEONAMES = "https://download.geonames.org/export/dump/"
OURAIRPORTS = "https://raw.githubusercontent.com/davidmegginson/ourairports-data/main/airports.csv"
# Candidate Passport Index mirrors; the one with the newest commit touching the tidy CSV wins.
VISA_SOURCES = [
    ("ilyankou/passport-index-dataset", "master", "passport-index-tidy-iso2.csv"),
    ("imorte/passport-index-data", "main", "passport-index-tidy-iso2.csv"),
]


def _fetch(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def get(url, binary=False):
    try:
        b = _fetch(url, UA)
    except Exception:
        # Some networks reset raw.githubusercontent.com while api.github.com works:
        # retry the same file through the GitHub contents API (raw media type, files up to 100 MB).
        m = re.match(r"https://raw\.githubusercontent\.com/([^/]+/[^/]+)/([^/]+)/(.+)$", url)
        if not m:
            raise
        repo, ref, path = m.groups()
        print(f"raw.githubusercontent.com failed; retrying via api.github.com for {repo}/{path}", file=sys.stderr)
        b = _fetch(f"https://api.github.com/repos/{repo}/contents/{path}?ref={ref}",
                   {**UA, "Accept": "application/vnd.github.raw"})
    return b if binary else b.decode("utf-8")


def last_commit(repo, path):
    """ISO date of the last commit touching `path`, or None (API rate limits are fine to ignore)."""
    try:
        j = json.loads(get(f"https://api.github.com/repos/{repo}/commits?path={path}&per_page=1"))
        return j[0]["commit"]["committer"]["date"][:10]
    except Exception:
        pass
    # Fallback: blobless shallow clone and ask git (works when the API is rate-limited or blocked).
    import subprocess, tempfile
    try:
        with tempfile.TemporaryDirectory() as t:
            subprocess.run(["git", "clone", "-q", "--depth", "50", "--filter=blob:none", "--no-checkout",
                            f"https://github.com/{repo}", t], check=True, timeout=90, capture_output=True)
            out = subprocess.run(["git", "-C", t, "log", "-1", "--format=%cI", "--", path],
                                 capture_output=True, text=True, timeout=30).stdout.strip()
            return out[:10] or None
    except Exception:
        return None


def load_meta():
    p = os.path.join(DATA, "meta.json")
    return json.load(open(p)) if os.path.exists(p) else {"datasets": {}}


def save(name, obj):
    with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def build_places(meta):
    countries = list(csv.DictReader(io.StringIO(get(CSC + "countries.csv"))))
    states = list(csv.DictReader(io.StringIO(get(CSC + "states.csv"))))
    cmap = {}
    out_c, cur = [], {}
    for c in countries:
        iso = c["iso2"]
        cmap[iso] = c["name"]
        out_c.append([iso, c["name"], c["currency"], float(c["latitude"] or 0), float(c["longitude"] or 0), c["emoji"]])
        if c["currency"]:
            cur.setdefault(c["currency"], [c["currency_name"], c["currency_symbol"]])
    out_s = []
    for s in states:
        if s.get("parent_id"):  # keep first-level regions only
            continue
        try:
            lat, lon = float(s["latitude"]), float(s["longitude"])
        except ValueError:
            lat = lon = 0.0
        out_s.append([s["country_code"], s["name"], s["iso2"], round(lat, 4), round(lon, 4)])
    # Cities: GeoNames cities15000 (population >= 15,000) with first-level region names.
    admin1 = {}
    for line in get(GEONAMES + "admin1CodesASCII.txt").splitlines():
        p = line.split("\t")
        if len(p) >= 2:
            admin1[p[0]] = p[1]
    z = zipfile.ZipFile(io.BytesIO(get(GEONAMES + "cities15000.zip", binary=True)))
    out_ci = []
    for line in z.read("cities15000.txt").decode("utf-8").splitlines():
        p = line.split("\t")
        cc = p[8]
        if cc not in cmap:
            continue
        region = admin1.get(f"{cc}.{p[10]}", "")
        alt = p[2] if p[2] != p[1] else ""
        out_ci.append([p[1], alt, region, cc, round(float(p[4]), 4), round(float(p[5]), 4), int(p[14] or 0)])
    out_ci.sort(key=lambda r: -r[6])
    save("countries.json", out_c)
    save("states.json", out_s)
    save("cities.json", out_ci)
    save("currencies.json", cur)
    today = datetime.date.today().isoformat()
    meta["datasets"]["countries-states"] = {
        "source": "https://github.com/dr5hn/countries-states-cities-database",
        "licence": "ODbL-1.0", "date": last_commit("dr5hn/countries-states-cities-database", "csv/states.csv") or today,
        "downloaded": today, "rows": {"countries": len(out_c), "regions": len(out_s)}}
    meta["datasets"]["cities"] = {
        "source": "https://download.geonames.org/export/dump/cities15000.zip",
        "licence": "CC-BY-4.0 (GeoNames)", "date": today, "downloaded": today,
        "filter": "population >= 15,000", "rows": len(out_ci)}
    meta["datasets"]["currencies"] = {
        "source": "countries.csv currency columns (countries-states-cities-database)",
        "licence": "ODbL-1.0", "date": meta["datasets"]["countries-states"]["date"], "downloaded": today, "rows": len(cur)}


def build_airports(meta):
    rows = csv.DictReader(io.StringIO(get(OURAIRPORTS)))
    out = []
    for a in rows:
        if a["scheduled_service"] != "yes" or not a["iata_code"] or a["type"] == "closed":
            continue
        out.append([a["iata_code"], a["name"], a["municipality"], a["iso_country"],
                    round(float(a["latitude_deg"]), 4), round(float(a["longitude_deg"]), 4),
                    {"large_airport": 3, "medium_airport": 2}.get(a["type"], 1)])
    save("airports.json", out)
    today = datetime.date.today().isoformat()
    meta["datasets"]["airports"] = {
        "source": OURAIRPORTS, "licence": "Public domain (OurAirports)",
        "date": last_commit("davidmegginson/ourairports-data", "airports.csv") or today,
        "downloaded": today, "filter": "scheduled_service=yes, has IATA code, not closed", "rows": len(out)}


def build_visa(meta):
    best = None
    for repo, branch, path in VISA_SOURCES:
        d = last_commit(repo, path)
        if best is None or (d and (best[3] is None or d > best[3])):
            best = (repo, branch, path, d)
    repo, branch, path, d = best
    text = get(f"https://raw.githubusercontent.com/{repo}/{branch}/{path}")
    codes = {"visa free": "VF", "visa on arrival": "VOA", "e-visa": "EV", "eta": "ETA",
             "visa required": "VR", "no admission": "NA", "-1": "SELF"}
    out = {}
    for r in csv.DictReader(io.StringIO(text)):
        v = r["Requirement"].strip()
        out.setdefault(r["Passport"], {})[r["Destination"]] = int(v) if v.isdigit() else codes.get(v, v)
    save("visa.json", out)
    today = datetime.date.today().isoformat()
    meta["datasets"]["visa"] = {
        "source": f"https://github.com/{repo}", "licence": "MIT (data from passportindex.org)",
        "date": d or today, "downloaded": today, "rows": sum(len(v) for v in out.values()),
        "values": "number = visa-free days; VF visa free; VOA visa on arrival; EV e-visa; ETA electronic travel authorisation; VR visa required; NA no admission; SELF own country"}


def check():
    meta = load_meta()
    v = meta["datasets"].get("visa", {})
    age = None
    if v.get("date"):
        age = (datetime.date.today() - datetime.date.fromisoformat(v["date"])).days
    newest = None
    for repo, _b, path in VISA_SOURCES:
        d = last_commit(repo, path)
        if d and (newest is None or d > newest[1]):
            newest = (repo, d)
    print(json.dumps({"visa_date": v.get("date"), "visa_age_days": age, "stale": age is not None and age > 31,
                      "newer_available": bool(newest and v.get("date") and newest[1] > v["date"]),
                      "newest_source": newest}, indent=1))


if __name__ == "__main__":
    os.makedirs(DATA, exist_ok=True)
    if "--check" in sys.argv:
        check(); sys.exit(0)
    meta = load_meta()
    if "--visa" in sys.argv:
        build_visa(meta)
    else:
        build_places(meta); build_airports(meta); build_visa(meta)
    meta["updated"] = datetime.date.today().isoformat()
    json.dump(meta, open(os.path.join(DATA, "meta.json"), "w"), indent=1)
    print(json.dumps(meta, indent=1))
