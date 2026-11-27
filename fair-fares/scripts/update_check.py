#!/usr/bin/env python3
"""Quick update check, run at the start of every fair-fares run.

  python3 update_check.py            -> check only (prints JSON); never changes anything
  python3 update_check.py --apply    -> update to the newer version (run only after the user said yes)
  python3 update_check.py --decline  -> remember that the user said no to the newer version (not asked again for it)
  python3 update_check.py --force    -> ignore the 6-hour "checked recently" cache

Compares fair-fares/version.json here with the copy on GitHub (main branch). How it updates
depends on how the skill was installed:
  - Claude Code plugin   -> runs `claude plugin marketplace update fair-fares` and
                            `claude plugin update fair-fares@fair-fares` (takes effect next session)
  - git working copy     -> `git pull --ff-only` (only if there are no local edits)
  - plain copy           -> downloads the repo archive and replaces this skill folder's files
Your settings and runs live outside the skill folder (~/.fair-fares, ./fair-fares-runs) and are never touched.
Never blocks a run: offline, slow or failed checks just report and carry on.

Status values: up_to_date | update_available | updated | updated_next_session | declined | offline | skipped_recent | failed
"""
import io, json, os, pathlib, shutil, subprocess, sys, tarfile, tempfile, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import SKILL_DIR, STATE, read_json, write_json

REPO = "HyperbolicTimeChamber/fair-fares"
BRANCH = "main"
RAW = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/fair-fares/version.json"
ARCHIVE = f"https://codeload.github.com/{REPO}/tar.gz/refs/heads/{BRANCH}"
CACHE = STATE / "update_check.json"
RECENT = 6 * 3600


def vtuple(v):
    try:
        return tuple(int(x) for x in str(v).split(".")[:3])
    except ValueError:
        return (0,)


def fetch(url, timeout=5):
    req = urllib.request.Request(url, headers={"User-Agent": "fair-fares-update-check", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def install_kind():
    p = str(SKILL_DIR).replace("\\", "/")
    if "/.claude/plugins/" in p:
        return "plugin"
    for parent in [SKILL_DIR, *SKILL_DIR.parents][:3]:
        if (parent / ".git").exists():
            return "git"
    return "copy"


def update_plugin():
    claude = shutil.which("claude")
    if not claude:
        return "failed", "The claude command isn't on PATH; run /plugin marketplace update fair-fares in Claude Code."
    for cmd in (["plugin", "marketplace", "update", "fair-fares"], ["plugin", "update", "fair-fares@fair-fares"]):
        r = subprocess.run([claude, *cmd], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return "failed", (r.stdout + r.stderr).strip()[-300:]
    return "updated_next_session", "Updated. Claude Code loads the new version in your next session."


def update_git():
    root = next(p for p in [SKILL_DIR, *SKILL_DIR.parents] if (p / ".git").exists())
    dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain"], capture_output=True, text=True, timeout=30).stdout.strip()
    if dirty:
        return "update_available", f"This copy has local edits in {root}, so it wasn't updated automatically."
    r = subprocess.run(["git", "-C", str(root), "pull", "--ff-only"], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        return "failed", (r.stdout + r.stderr).strip()[-300:]
    return "updated", "Updated with git pull."


def update_copy():
    data = fetch(ARCHIVE, timeout=60)
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            prefix = None
            members = []
            for m in tf.getmembers():
                parts = m.name.split("/")
                if len(parts) >= 2 and parts[1] == "fair-fares" and (m.isfile() or m.isdir()):
                    prefix = parts[0]
                    members.append(m)
            if not members:
                return "failed", "The download didn't contain the skill folder."
            for m in members:  # refuse anything that would land outside the temp folder
                if m.name.startswith("/") or ".." in m.name.split("/"):
                    return "failed", "The download had an unsafe path in it."
            try:
                tf.extractall(tmp, members=members, filter="data")
            except TypeError:  # Python without extraction filters
                tf.extractall(tmp, members=members)
        new = pathlib.Path(tmp) / prefix / "fair-fares"
        if not (new / "SKILL.md").exists():
            return "failed", "The download didn't contain SKILL.md."
        new_files = {p.relative_to(new) for p in new.rglob("*") if p.is_file()}
        # Remove files that no longer exist upstream (only inside the skill folder, never caches or user data).
        for p in list(SKILL_DIR.rglob("*")):
            rel = p.relative_to(SKILL_DIR)
            if p.is_file() and rel not in new_files and "__pycache__" not in rel.parts:
                p.unlink()
        for rel in new_files:
            dst = SKILL_DIR / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(new / rel, dst)
    return "updated", "Updated from GitHub."


HOW = {"plugin": "Claude Code's plugin manager updates it; the new version loads in the next session.",
       "git": "It runs git pull in your copy (only if you haven't edited it).",
       "copy": "It downloads the new version from GitHub and replaces the skill's files. Your settings and past searches aren't touched."}


def main():
    a = sys.argv[1:]
    local = read_json(SKILL_DIR / "version.json", {}) or {}
    cache = read_json(CACHE, {}) or {}
    out = {"local": local.get("version"), "install": install_kind()}
    if "--decline" in a:
        cache["declined"] = cache.get("remote")
        write_json(CACHE, cache)
        out.update(status="declined", remote=cache.get("remote"), message="OK, staying on this version. You won't be asked about this one again.")
        print(json.dumps(out)); return 0
    if "--apply" not in a and "--force" not in a and time.time() - cache.get("at", 0) < RECENT and cache.get("local") == local.get("version"):
        out.update(status="skipped_recent", remote=cache.get("remote"), message="Checked in the last 6 hours.")
        print(json.dumps(out)); return 0
    try:
        remote = json.loads(fetch(RAW))
    except Exception as e:
        out.update(status="offline", message=f"Couldn't reach GitHub ({e.__class__.__name__}); carrying on with this version.")
        print(json.dumps(out)); return 0
    out["remote"] = remote.get("version")
    out["notes"] = remote.get("notes", "")
    write_json(CACHE, {"at": time.time(), "local": local.get("version"), "remote": remote.get("version"), "declined": cache.get("declined")})
    if vtuple(remote.get("version")) <= vtuple(local.get("version")):
        out.update(status="up_to_date", message="You have the latest version.")
        print(json.dumps(out)); return 0
    if "--apply" not in a:
        if cache.get("declined") == remote.get("version"):
            out.update(status="declined", message="The user already said no to this version.")
        else:
            out.update(status="update_available", how=HOW[out["install"]], message=f"Version {remote.get('version')} is available (you have {local.get('version')}).")
        print(json.dumps(out)); return 0
    try:
        status, msg = {"plugin": update_plugin, "git": update_git, "copy": update_copy}[out["install"]]()
    except Exception as e:
        status, msg = "failed", f"{e.__class__.__name__}: {e}"
    out.update(status=status, message=msg)
    if status in ("updated", "updated_next_session"):
        write_json(CACHE, {"at": time.time(), "local": remote.get("version"), "remote": remote.get("version")})
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
