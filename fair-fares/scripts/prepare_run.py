#!/usr/bin/env python3
"""Create (or find) the run folder for the saved settings.

  python3 prepare_run.py            -> JSON: {previous_runs:[...], proposed:path}  (creates nothing)
  python3 prepare_run.py --new      -> creates ./fair-fares-runs/<destination>-<YYYY-MM-DD>/ (+ -2, -3 ...)
  python3 prepare_run.py --reuse P  -> makes P the current run again (re-check prices only)

The new folder gets settings.json, results/ and results/SCHEMA.csv (header shared by all subagents).
"""
import json, sys, os, shutil, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import STATE, ASSETS, read_json, write_json, slug, runs_root, set_current_run

SCHEMA = (ASSETS / "results_schema.csv").read_text().strip()


def trip_key(s):
    t = s.get("trip", {})
    w = t.get("window", {})
    return [t.get("destination", {}).get("label"), w.get("mode"), w.get("earliest") or w.get("leave"),
            w.get("latest") or w.get("return")]


def main():
    s = read_json(STATE / "settings.json")
    if not s:
        print(json.dumps({"error": "No settings yet. Open the form and press Start search."}))
        return 1
    dest = s.get("trip", {}).get("destination", {})
    base = f"{slug(dest.get('name') or dest.get('label'))}-{datetime.date.today().isoformat()}"
    root = runs_root()
    prev = []
    if root.exists():
        for d in sorted(root.iterdir()):
            ps = read_json(d / "settings.json")
            if ps and trip_key(ps) == trip_key(s):
                prev.append({"path": str(d), "has_results": (d / "all_options.csv").exists(),
                             "saved_at": ps.get("saved_at")})
    a = sys.argv[1:]
    if "--auto" in a:  # unattended: follow the choice made in the form, never ask
        choice = (s.get("unattended") or {}).get("previous_run", "fresh")
        if prev and choice == "reuse":
            a = ["--reuse", prev[-1]["path"]]
        else:
            a = ["--new"]
    if "--reuse" in a:
        p = root / os.path.basename(a[a.index("--reuse") + 1])
        write_json(p / "settings.json", s)
        set_current_run(p)
        print(json.dumps({"current": str(p), "mode": "reuse"}))
        return 0
    if "--new" in a:
        p, n = root / base, 2
        while p.exists():
            p, n = root / f"{base}-{n}", n + 1
        (p / "results").mkdir(parents=True)
        write_json(p / "settings.json", s)
        (p / "results" / "SCHEMA.csv").write_text(SCHEMA + "\n")
        if prev:
            write_json(p / "previous_run.json", {"path": prev[-1]["path"]})
        set_current_run(p)
        print(json.dumps({"current": str(p), "mode": "new", "schema": SCHEMA.split(",")}))
        return 0
    print(json.dumps({"previous_runs": prev, "proposed": str(root / base)}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
