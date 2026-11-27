#!/usr/bin/env python3
"""Fast setup check. Run first, every time.

  python3 setup_check.py --agent claude-code|codex-app|codex-cli|grok|gemini|cursor [--test-model] [--refresh]

Prints JSON: {agent, cached, items:[{id,label,required,status,detail,install,fallback}]}
status: ok | missing | stale | agent_check (the agent must look at its own tool list) | not_applicable
Results are cached in ~/.fair-fares/setup_cache.json and reused while nothing relevant changed.
Installs nothing. The agent shows install commands to the user and runs them only after approval.
"""
import json, os, platform, shutil, subprocess, sys, sysconfig, time, hashlib, pathlib, datetime, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import STATE, DATA, read_json, write_json, config, save_config

HOME = pathlib.Path.home()
AGENTS = ["claude-code", "codex-app", "codex-cli", "grok", "gemini", "cursor"]

MODEL_CMDS = {
    "claude-code": ["claude", "-p", "--model", "claude-haiku-5-5", "{prompt}"],
    "codex-app": ["codex", "exec", "--skip-git-repo-check", "-m", "{codex_model}", "{prompt}"],
    "codex-cli": ["codex", "exec", "--skip-git-repo-check", "-m", "{codex_model}", "{prompt}"],
    "gemini": ["gemini", "-m", "{gemini_model}", "-p", "{prompt}"],
    "grok": ["grok", "-m", "{grok_model}", "-p", "{prompt}"],
}
DEFAULT_MODELS = {"codex_model": "gpt-5-codex-mini", "gemini_model": "gemini-2.5-flash", "grok_model": "grok-code-fast-1"}

BROWSER = {
    "claude-code": ("Claude in Chrome", "Install from https://claude.ai/chrome, sign in, then run /chrome in Claude Code (or start it with `claude --chrome`)."),
    "codex-app": ("Codex Chrome extension", "Install the Codex Chrome extension from the Codex app's settings (Browser / Chrome section) and allow it for this workspace."),
    "codex-cli": ("Playwright MCP", None),
    "grok": ("Browser Use plugin (local Chrome)", "Install the Browser Use plugin from Grok Build's plugin marketplace and point it at your local Chrome."),
    "gemini": ("Chrome DevTools for agents", "gemini mcp add chrome-devtools npx chrome-devtools-mcp@latest"),
    "cursor": ("Cursor built-in browser", "Enable the built-in browser in Cursor Settings → Beta/Browser (it ships with Cursor)."),
}
PW_MCP_ADD = {
    "claude-code": "claude mcp add playwright -- npx @playwright/mcp@latest",
    "codex-app": "codex mcp add playwright -- npx @playwright/mcp@latest",
    "codex-cli": "codex mcp add playwright -- npx @playwright/mcp@latest",
    "gemini": "gemini mcp add playwright npx @playwright/mcp@latest",
    "grok": 'Add to Grok Build MCP config: {"playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}}',
    "cursor": 'Add to ~/.cursor/mcp.json: {"mcpServers": {"playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}}}',
}
KIWI_ADD = {
    "claude-code": "claude mcp add --transport http kiwi-com-flight-search https://mcp.kiwi.com",
    "codex-app": "codex mcp add kiwi -- npx mcp-remote https://mcp.kiwi.com",
    "codex-cli": "codex mcp add kiwi -- npx mcp-remote https://mcp.kiwi.com",
    "gemini": "gemini mcp add --transport http kiwi https://mcp.kiwi.com",
    "grok": "Add a custom connector / MCP server with URL https://mcp.kiwi.com",
    "cursor": 'Add to ~/.cursor/mcp.json: {"mcpServers": {"kiwi": {"url": "https://mcp.kiwi.com"}}}',
}


def detect_agent():
    e = os.environ
    if e.get("CLAUDECODE") or e.get("CLAUDE_CODE_ENTRYPOINT"):
        return "claude-code"
    if any(k.startswith("CODEX_") for k in e):
        return "codex-app" if e.get("CODEX_INTERNAL_ORIGINATOR_OVERRIDE") or e.get("CODEX_APP") else "codex-cli"
    if e.get("GEMINI_CLI"):
        return "gemini"
    if e.get("CURSOR_AGENT") or e.get("CURSOR_TRACE_ID"):
        return "cursor"
    if any(k.startswith("GROK") for k in e):
        return "grok"
    return None


def sh(cmd, timeout=8):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as ex:
        return 1, str(ex)


def pw_browser_dirs():
    roots = [os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or "",
             str(HOME / ".cache/ms-playwright"), str(HOME / "Library/Caches/ms-playwright"),
             str(HOME / "AppData/Local/ms-playwright")]
    found = []
    for r in roots:
        if r:
            found += glob.glob(os.path.join(r, "chromium*"))
    return found


MCP_FILES = [HOME / ".claude.json", pathlib.Path.cwd() / ".mcp.json", HOME / ".codex/config.toml",
             HOME / ".gemini/settings.json", HOME / ".cursor/mcp.json", HOME / ".grok/settings.json",
             HOME / ".grok/config.toml", HOME / ".grok/mcp.json"]


def mcp_text():
    out = ""
    for f in MCP_FILES:
        try:
            out += f.read_text(errors="ignore")[:2_000_000]
        except Exception:
            pass
    return out.lower()


def fingerprint(agent):
    parts = [agent, sys.version, platform.platform()]
    for b in ["node", "npx", "claude", "codex", "gemini", "grok", "cursor-agent"]:
        parts.append(f"{b}={shutil.which(b)}")
    for f in MCP_FILES + [DATA / "meta.json"]:
        try:
            parts.append(f"{f}:{f.stat().st_mtime}")
        except Exception:
            pass
    parts += pw_browser_dirs()
    try:
        import importlib.util
        parts.append(str(bool(importlib.util.find_spec("playwright"))))
    except Exception:
        pass
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


PLAIN = {  # what to tell the user, in everyday words (commands stay in "install" for when they ask)
    "runtime": "Python or Node: the program that runs this skill's helpers.",
    "playwright": "Playwright: lets me open and read travel websites in a browser window you can watch.",
    "playwright_browser": "A browser for Playwright to use (a separate copy of Chromium, about 150 MB).",
    "playwright_mcp": "Playwright for the agent: lets me click through a website step by step when a quick read isn't enough.",
    "browser_plugin": "Your agent's own browser helper: used for the final price checks and to take you to the booking page.",
    "kiwi": "Kiwi.com connection: a free flight-search service that checks many dates at once. Faster and gentler than visiting sites.",
    "doc_model": "A small, cheap AI model for the document check on page 3, used only for questions the visa list can't answer.",
    "visa_data": "The built-in visa list. It's older than a month, so I can download the newest version.",
}


def windows_alias():
    """Names (python3/python) that resolve to a Windows App Execution Alias (in a WindowsApps folder).
    Such aliases can run Python with a virtualised %APPDATA%, so packages pip put in the user site
    (pip install --user) are invisible. Always run the skill's scripts with sys.executable instead."""
    if platform.system() != "Windows":
        return []
    return [b for b in ("python3", "python") if "windowsapps" in (shutil.which(b) or "").lower()]


def pip_install_cmd():
    """pip command for Playwright. On Windows, skip --user when the interpreter's own site-packages is
    writable (per-user python.org install): that folder is visible under every launcher, the user site is not."""
    cmd = f'"{sys.executable}" -m pip install'
    purelib = sysconfig.get_paths().get("purelib", "")
    if not (platform.system() == "Windows" and purelib and os.access(purelib, os.W_OK)):
        cmd += " --user"
    cmd += " playwright"
    if platform.system() == "Linux":
        cmd += "  # add --break-system-packages if pip refuses (PEP 668)"
    return cmd


def item(i, label, required, status, detail="", install=None, fallback=None):
    return {"id": i, "label": label, "plain": PLAIN.get(i, label), "required": required, "status": status,
            "detail": detail, "install": install or {}, "fallback": fallback}


def check(agent, test_model=False):
    items = []
    py = sys.version.split()[0]
    node = shutil.which("node")
    nv = sh(["node", "--version"])[1] if node else ""
    alias = windows_alias()
    rt = f"Python {py} at {sys.executable}" + (f", Node {nv}" if node else "")
    if alias:
        rt += (f". `{'`/`'.join(alias)}` on PATH is a Windows Store alias that can hide user-installed packages:"
               f" run every skill script with \"{sys.executable}\".")
    items.append(item("runtime", "Python or Node", True, "ok", rt))
    # Playwright library + browser
    import importlib.util
    py_pw = importlib.util.find_spec("playwright") is not None
    node_pw = bool(node) and sh(["node", "-e", "require.resolve('playwright')"], 5)[0] == 0
    pip = pip_install_cmd()
    if py_pw or node_pw:
        items.append(item("playwright", "Playwright library", True, "ok", "python" if py_pw else "node"))
    else:
        items.append(item("playwright", "Playwright library", True, "missing",
                          f"Not importable from {sys.executable} or Node."
                          + (" If you already installed it, re-run this check with that full path, not the python3 alias." if alias else ""),
                          {"commands": [pip] if not node else [pip, "# or Node: npm install -g playwright"]}))
    br = pw_browser_dirs()
    items.append(item("playwright_browser", "Playwright Chromium", True, "ok" if br else "missing",
                      br[0] if br else "No Playwright browser download found.",
                      {"commands": [f'"{sys.executable}" -m playwright install chromium' if py_pw or not node else "npx playwright install chromium"]}))
    text = mcp_text()
    # Playwright MCP
    has_pw_mcp = "@playwright/mcp" in text or '"playwright"' in text or "[mcp_servers.playwright]" in text
    if agent == "claude-code" and not has_pw_mcp and shutil.which("claude"):
        has_pw_mcp = "playwright" in sh(["claude", "mcp", "list"], 15)[1].lower()
    items.append(item("playwright_mcp", "Playwright MCP", agent == "codex-cli", "ok" if has_pw_mcp else "missing",
                      "Configured" if has_pw_mcp else "Not found in this agent's MCP config.",
                      {"commands": [PW_MCP_ADD.get(agent, PW_MCP_ADD["claude-code"])], "needs_restart": True},
                      "Playwright scripts only; one-off clicks happen in scripts, and final checks give direct links."))
    # Agent's own browser plugin
    name, how = BROWSER.get(agent, ("Agent browser", None))
    if agent == "codex-cli":
        items.append(item("browser_plugin", "Codex Chrome extension", False, "not_applicable",
                          "The Codex Chrome extension works in the Codex app, not the Codex CLI. Using Playwright MCP in a visible browser instead.",
                          fallback="Playwright MCP (visible browser)"))
    else:
        items.append(item("browser_plugin", name, False, "agent_check",
                          "Look at your own tool list for this browser's tools.",
                          {"manual": [how]} if how else {},
                          "Playwright MCP in a visible browser; if blocked, direct links."))
    # Kiwi.com
    kiwi = "mcp.kiwi.com" in text or "kiwi-com" in text
    items.append(item("kiwi", "Kiwi.com connector/MCP", False, "ok" if kiwi else "agent_check",
                      "Configured in an MCP config file. If no Kiwi search-flight tool is in your tool list yet, the agent needs a restart to load it; use the fallback until then." if kiwi else "Not in MCP config files; check your tool list for a Kiwi search-flight tool (it may be an account connector).",
                      {"commands": [KIWI_ADD.get(agent, KIWI_ADD["claude-code"])], "manual": ["Connector URL: https://mcp.kiwi.com (no API key)"]},
                      "Google Flights via a low-volume Playwright script (stops at any block)."))
    # Small model for the document check
    cfg = config()
    models = {**DEFAULT_MODELS, **(cfg.get("models") or {})}
    if os.environ.get("FAIR_FARES_MODEL_CMD"):
        cmd = json.loads(os.environ["FAIR_FARES_MODEL_CMD"])
    else:
        cmd = [c.format(**models) if "{prompt}" not in c else c for c in MODEL_CMDS.get(agent, [])]
    if agent == "cursor" or not cmd:
        items.append(item("doc_model", "Small model for document check", False, "not_applicable",
                          "Cursor: no CLI model call. Dataset answers instantly; anything else is asked in chat.",
                          fallback="Dataset only / ask in chat"))
        cfg["doc_model"] = {"mode": "chat"}
    elif shutil.which(cmd[0]):
        st, det = "ok", f"{' '.join(cmd[:-1])} (not test-called yet)"
        if test_model:
            t0 = time.time()
            rc, out = sh([a.replace("{prompt}", 'Reply with exactly: ["ok"]') for a in cmd], 90)
            st = "ok" if rc == 0 and "ok" in out.lower() else "missing"
            det = f"Test call {'worked' if st == 'ok' else 'failed'} in {time.time() - t0:.0f}s: {out[:160]}"
        items.append(item("doc_model", "Small model for document check", False, st, det,
                          {"manual": ["Set a different model: edit ~/.fair-fares/config.json → models, or FAIR_FARES_MODEL_CMD"]},
                          "Dataset only; unanswered items are asked in chat."))
        cfg["doc_model"] = {"mode": "cli", "cmd": cmd, "tested": test_model and st == "ok"}
    else:
        items.append(item("doc_model", "Small model for document check", False, "missing",
                          f"`{cmd[0]}` CLI not on PATH.", {"manual": [f"Install the {cmd[0]} CLI and sign in."]},
                          "Dataset only; unanswered items are asked in chat."))
        cfg["doc_model"] = {"mode": "chat"}
    # Visa dataset freshness
    meta = read_json(DATA / "meta.json", {}) or {}
    visa = meta.get("datasets", {}).get("visa") or {}
    vd, dl = visa.get("date"), visa.get("downloaded")
    today = datetime.date.today()
    age = (today - datetime.date.fromisoformat(vd)).days if vd else None
    dl_age = (today - datetime.date.fromisoformat(dl)).days if dl else None
    # The upstream mirrors are not updated monthly. A dataset downloaded in the last 31 days is the newest
    # available, even when its own date is older, so it is not stale.
    fresh = (age is not None and age <= 31) or (dl_age is not None and dl_age <= 31)
    detail = f"Dataset date {vd} ({age} days old)" if vd else "No visa dataset"
    if vd and dl and age is not None and age > 31 and fresh:
        detail += f"; downloaded {dl}, which was the newest upstream version"
    sd = str(pathlib.Path(__file__).parent / "update_data.py")
    items.append(item("visa_data", "Visa dataset freshness", False,
                      "ok" if fresh else "stale", detail,
                      {"commands": [f'"{sys.executable}" "{sd}" --check', f'"{sys.executable}" "{sd}" --visa']},
                      "Use the current dataset; the search re-verifies on official government sites anyway."))
    cfg["agent"] = agent
    cfg.setdefault("models", models)
    save_config(cfg)
    return items


def permissions(agent):
    """Claude Code allow-rules so an unattended run never stops at a tool prompt.
    Scoped to this skill's scripts, the run folder and the tools the workflow uses."""
    sd = str(pathlib.Path(__file__).resolve().parent).replace("\\", "/")
    rules = []
    for py in ["python3", "python", "py"]:
        rules.append(f"Bash({py} {sd}/*)")
    rules += [f"Bash(node {sd}/server.mjs*)", "Bash(python -m playwright install chromium)",
              "Read(~/.fair-fares/**)", "Edit(~/.fair-fares/**)", "Read(./fair-fares-runs/**)", "Edit(./fair-fares-runs/**)",
              "Write(./fair-fares-runs/**)", "WebSearch", "WebFetch", "mcp__playwright", "mcp__kiwi-com-flight-search",
              "mcp__claude-in-chrome", "Task"]
    return {"agent": agent, "settings_file": "~/.claude/settings.json (all projects) or .claude/settings.local.json (this folder only)",
            "merge_into": {"permissions": {"allow": rules}},
            "never_allowed": "Booking, payment, passport details, sign-ins, CAPTCHAs: the skill never does these, whatever the permissions say.",
            "note": "Other agents: grant the equivalent in their own permission settings (Codex approval policy, Gemini trustedFolders/allowed tools, Cursor auto-run allowlist)."}


def main():
    a = sys.argv[1:]
    agent = a[a.index("--agent") + 1] if "--agent" in a else (detect_agent() or "unknown")
    if "--permissions" in a:
        print(json.dumps(permissions(agent), indent=1))
        return 0
    if agent not in AGENTS:
        print(json.dumps({"error": f"Unknown agent '{agent}'. Pass --agent one of {AGENTS}."}))
        return 1
    fp = fingerprint(agent)
    cache = read_json(STATE / "setup_cache.json", {}) or {}
    if "--refresh" not in a and "--test-model" not in a and cache.get("fingerprint") == fp \
            and time.time() - cache.get("at", 0) < 7 * 86400:
        cache["cached"] = True
        print(json.dumps(cache, indent=1))
        return 0
    items = check(agent, "--test-model" in a)
    out = {"agent": agent, "detected": detect_agent(), "fingerprint": fp, "at": time.time(), "cached": False,
           "os": platform.system(), "python": sys.executable, "items": items}
    write_json(STATE / "setup_cache.json", out)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
