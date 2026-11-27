"""Shared paths and helpers for fair-fares scripts (Python standard library only)."""
import json, os, re, datetime, math, pathlib

SKILL_DIR = pathlib.Path(__file__).resolve().parent.parent
ASSETS = SKILL_DIR / "assets"
DATA = ASSETS / "data"
STATE = pathlib.Path(os.environ.get("FAIR_FARES_HOME", pathlib.Path.home() / ".fair-fares"))
STATE.mkdir(parents=True, exist_ok=True)


def runs_root():
    return pathlib.Path(os.environ.get("FAIR_FARES_RUNS", pathlib.Path.cwd() / "fair-fares-runs"))


def read_json(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(p, obj):
    p = pathlib.Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def slug(s):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (s or "trip").lower()).strip("-")
    return s[:40] or "trip"


def today():
    return datetime.date.today()


def parse_date(s):
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def haversine_km(a, b, c, d):
    r = 6371.0
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = math.radians(c - a), math.radians(d - b)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def config():
    return read_json(STATE / "config.json", {}) or {}


def save_config(cfg):
    write_json(STATE / "config.json", cfg)


def current_run():
    p = read_json(STATE / "current_run.json", {})
    return pathlib.Path(p["path"]) if p and p.get("path") else None


def set_current_run(path):
    write_json(STATE / "current_run.json", {"path": str(path), "set_at": datetime.datetime.now().isoformat()})
