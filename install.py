#!/usr/bin/env python3
"""Install the fair-fares skill into each supported agent's skills folder.

  python3 install.py            # shows what it will do and asks before copying
  python3 install.py --yes      # no prompt
  python3 install.py --only claude,codex
  python3 install.py --all      # also create skills folders for agents not detected
  python3 install.py --uninstall

Agents are "detected" when their config folder exists (e.g. ~/.claude). Your saved settings live in
~/.fair-fares and are never touched. Alternative: npx skills add <owner>/<repo>
"""
import pathlib, shutil, sys

HOME = pathlib.Path.home()
SRC = pathlib.Path(__file__).resolve().parent / "fair-fares"
TARGETS = {
    "claude": ("Claude Code", HOME / ".claude", HOME / ".claude/skills"),
    "codex": ("Codex", HOME / ".codex", HOME / ".agents/skills"),
    "grok": ("Grok Build", HOME / ".grok", HOME / ".grok/skills"),
    "gemini": ("Gemini CLI", HOME / ".gemini", HOME / ".gemini/skills"),
    "cursor": ("Cursor", HOME / ".cursor", HOME / ".cursor/skills"),
}


def main():
    a = sys.argv[1:]
    only = set(a[a.index("--only") + 1].split(",")) if "--only" in a else set(TARGETS)
    plan = []
    for key, (name, marker, dest) in TARGETS.items():
        if key not in only:
            continue
        found = marker.exists() or (key == "codex" and (HOME / ".agents").exists())
        if found or "--all" in a or "--only" in a:
            plan.append((name, dest / "fair-fares"))
        else:
            print(f"  skip  {name:12} (not detected: {marker})")
    if not plan:
        print("No agents detected. Use --all or --only claude,codex,grok,gemini,cursor."); return 1
    verb = "Remove" if "--uninstall" in a else "Install to"
    for name, d in plan:
        print(f"  {verb:10} {name:12} {d}" + ("  (replaces existing copy)" if d.exists() and verb != "Remove" else ""))
    if "--yes" not in a and input("Proceed? [y/N] ").strip().lower() not in ("y", "yes"):
        print("Nothing changed."); return 0
    for name, d in plan:
        if d.exists():
            shutil.rmtree(d)
        if verb == "Remove":
            continue
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(SRC, d, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
        print(f"  done  {name}")
    print("Restart your agent (or open a new session) so it picks up the skill. Then ask: \"find me cheap flights\".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
