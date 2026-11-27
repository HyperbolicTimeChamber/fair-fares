# Setup check and portability

## Which agent am I?

Pass `--agent` yourself; it is more reliable than environment sniffing. Codex: use `codex-app` inside the Codex desktop/IDE app and `codex-cli` in the terminal CLI. `setup_check.py` also reports what it detected from the environment (`detected`); if that disagrees with you, trust yourself and mention it.

## Per-agent parts

| Part | Claude Code | Codex app | Codex CLI | Grok Build | Gemini CLI | Cursor |
|---|---|---|---|---|---|---|
| Browser (final checks, booking hand-off) | Claude in Chrome | Codex Chrome extension | Playwright MCP | Browser Use plugin (local Chrome) | Chrome DevTools for agents (`chrome-devtools-mcp`) | Built-in browser |
| Document-check model | Haiku (`claude-haiku-5-5`) via `claude -p` | Codex small model via `codex exec -m` | same as app | Grok fast model via `grok` CLI | Gemini Flash via `gemini -m` | none: dataset only, ask in chat |
| Parallel searches | Subagents (Task/Agent tool) | If supported, else sequential | ← | ← | ← | ← |
| Broad date scan | Kiwi.com if connectable, else `gflights_scan.py` (all agents) | | | | | |

Fallback for any browser plugin: Playwright MCP in a **visible** browser; if that is blocked or missing, give direct links (`links.py`).

**Test, don't assume.** Agent features change quickly. Look at the tools you actually have:
- Claude in Chrome tools are named like `mcp__claude-in-chrome__*`. Chrome DevTools MCP tools usually include `navigate_page`, `take_snapshot`. Playwright MCP tools are `browser_navigate`, `browser_snapshot`, `browser_click`…
- Kiwi.com: a tool named `search-flight` (server `https://mcp.kiwi.com`, no API key).
- If a plugin exists but cannot work here, say why and use the fallback without asking the user to install it. Example: the Codex Chrome extension works in the Codex app, not in the Codex CLI.

## Small-model commands

Defaults live in `setup_check.py` (`MODEL_CMDS`, `DEFAULT_MODELS`) and are written to `~/.fair-fares/config.json` → `doc_model.cmd`. Model names change; if `--test-model` fails:
1. Ask the CLI which small models exist (e.g. `codex --help`, `/model` in the agent, or the vendor's docs).
2. Edit `~/.fair-fares/config.json` → `models` (`codex_model`, `gemini_model`, `grok_model`) and re-run `setup_check.py --refresh --test-model`.
3. Or set a full command: `FAIR_FARES_MODEL_CMD='["mycli","--model","x","{prompt}"]'`.
The server calls the model only from the document check, only for questions the dataset can't answer, and asks for JSON.

The Grok Build CLI flags (`grok -m … -p …`) and the Codex small-model name (`gpt-5-codex-mini`) are best guesses that `--test-model` must confirm on the user's machine.

## Install commands shown to the user

`setup_check.py` returns them per agent in `install.commands` / `install.manual`, plus a `plain` one-line description. Explain each item to the user with `plain`, get approval, run the commands yourself, re-check with `--refresh`. Show the commands only if the user asks to see them. Things that need the user's click (Chrome Web Store, marketplace plugins, account connectors) are never "run": give the link and wait.

- Playwright (Python): `python3 -m pip install --user playwright` then `python3 -m playwright install chromium`. On Linux/Homebrew Python with PEP 668, pip may need `--break-system-packages` or a venv; ask which the user prefers.
- Windows: run everything with the full interpreter path from the check's `python` field. The `python3`/`python` App Execution Aliases (in `...\Microsoft\WindowsApps\`) can start Python with a virtualised `%APPDATA%`. A `pip install --user` done with the full path then cannot be imported through the alias, and the check reports Playwright as missing. For a per-user python.org install, `setup_check.py` omits `--user`, so the package goes to the interpreter's own `site-packages`, which every launcher sees. `python` and `python3` may also be different versions (3.13 vs 3.14 seen), each with its own packages.
- Playwright MCP (Claude Code): `claude mcp add playwright -- npx @playwright/mcp@latest`; Codex: `codex mcp add playwright -- npx @playwright/mcp@latest`; Gemini: `gemini mcp add playwright npx @playwright/mcp@latest`. MCP changes need an agent restart; tell the user.
- Kiwi.com: Claude Code `claude mcp add --transport http kiwi-com-flight-search https://mcp.kiwi.com`; Claude/Grok/Gemini apps: add a custom connector with that URL.
- Claude in Chrome: https://claude.ai/chrome, then `/chrome` in Claude Code.

## Visa dataset freshness

`update_data.py --check` compares the local dataset date with the newest of the Passport Index mirrors on GitHub. Older than 31 days → flag it and offer `update_data.py --visa`. If no newer upstream exists, say so: the search re-verifies on official sites anyway.

Some networks reset connections to `raw.githubusercontent.com` (`WinError 10054`) while `api.github.com` works. `update_data.py` then retries each file through the GitHub contents API (`Accept: application/vnd.github.raw`). If both fail, report it and continue with the current dataset.
