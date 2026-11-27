---
name: fair-fares
description: Finds the cheapest door-to-door trip between two places (flights plus trains/buses to other airports, positioning flights, transfers, documents, bags, optional hotels), using a local web form for input, a travel-document check, parallel searches and a final hand-off to the booking page. Use when the user wants cheap flights, the cheapest way to get somewhere, flexible-date fare searches, or help comparing airports and routes for a trip.
---

# Fair Fares

Find the cheapest door-to-door trip and take the user to the booking page. Never book.

`SKILL_DIR` = the folder containing this file. Scripts are in `SKILL_DIR/scripts/` (Python 3 standard library; `server.mjs` is the Node fallback for the form server). Run them with the user's current folder as working directory, so runs are saved in `./fair-fares-runs/`. User state lives in `~/.fair-fares/`.

## Hard rules (always)

- Never book, apply for visas, sign in, or enter payment or passport details. Names/contact details only if the user enabled "enter details" in the form **and** confirms each time.
- Visa, entry and transit information only from official government sites (embassy, immigration, foreign-ministry pages). Third-party sites may point you there; they are never the source.
- Respect site terms. Visible browser, randomised pauses, modest request counts, one subagent per website. At a CAPTCHA or block: stop on that site, log it, move on. Never get around bot protection.
- Ask before installing anything. Show exact commands first.
- Never fall back silently: when a tool is missing or blocked, say what changes and which fallback you use.

## Workflow

### 1. Setup check (every run; cached, so fast when nothing changed)

1. Identify yourself as one of: `claude-code`, `codex-app`, `codex-cli`, `grok`, `gemini`, `cursor`. Then run
   `python3 SKILL_DIR/scripts/setup_check.py --agent <you>` (add `--refresh` to bypass the cache).
2. For items with `status: agent_check`, look at **your own tool list**: the browser plugin (see `references/setup-and-portability.md`) and a Kiwi.com tool (`search-flight` from `mcp.kiwi.com`). If Kiwi is connected, just use it.
3. Show a short status list (✓ ok / ✗ missing / ⚠ stale / – not applicable). For every missing item, offer exactly:
   1. **Install it for me**: show the commands from `install.commands`, run them only after the user approves. For clicks (Chrome extensions, marketplace installs, connectors), give the link/steps from `install.manual` and wait.
   2. **I'll install it myself**: show the steps, then re-run the check with `--refresh`.
   3. **Skip** (optional items only): say what changes (`fallback` field), then use the fallback.
   Required: Python or Node, Playwright and its Chromium. Visa data older than 31 days → offer `update_data.py --visa`.
4. If the user agrees, run once with `--test-model` to confirm the small model works for the document check.
Details and per-agent notes: `references/setup-and-portability.md`.

### 2. Form

1. Start the server in the background and leave it running:
   `python3 SKILL_DIR/scripts/server.py` (no Python → `node SKILL_DIR/scripts/server.mjs`). It opens the form in the user's browser, pre-filled from last time. Tell the user the URL it prints.
2. Wait for "Start search": `python3 SKILL_DIR/scripts/wait_event.py --types start` (blocks up to 9 minutes; exit code 2 = timeout, run it again; keep the user informed). Without Python, watch `~/.fair-fares/events.jsonl` for a new `start` line.
3. Read `~/.fair-fares/settings.json`. Field meanings: `references/form-and-settings.md`.

### 3. Preparation (`references/preparation.md`)

1. `python3 SKILL_DIR/scripts/prepare_run.py`. If `previous_runs` is non-empty, ask: **reuse** (re-check prices only, `--reuse PATH`) or **start fresh** (`--new`). Otherwise run `--new`.
2. `python3 SKILL_DIR/scripts/fx.py --to <currency>` once: one ECB reference rate for the whole run.
3. Quick destination research, official re-check of the form's document results, holidays/events. Report differences; ask only about new findings.
4. Write progress for the results page to `RUN/progress.json`: `{"phase", "message", "updated_at", "done": false}`. Update it at every phase.

### 4. Search (`references/search-workflow.md`)

- Phase 1 alone: broad scan (subagent A). Kiwi.com tool if available, else `gflights_scan.py` (low volume, stops at any block).
- Phase 2 in parallel on the 5 cheapest windows ±2 days: B comparison sites, C airlines direct, D alternative airports + ground (only if ticked), E hub routing, F hotels (only if ticked), G transfers/insurance.
- Use subagents where your agent has them; otherwise run the same briefs one after another. Every subagent writes `RUN/results/<letter>_<site>.csv` in the shared schema (`RUN/results/SCHEMA.csv`; column guide in `references/csv-schema.md`).
- Lead agent: per-direction pricing, buffers, minimum-saving rule.

### 5. Merge, verify, output (`references/merge-verify-output.md`)

1. `python3 SKILL_DIR/scripts/merge_results.py` → `all_options.csv` + `results.json`. Fix any warnings it prints (e.g. currency conversions).
2. Verify the top 10 one at a time (price status, transit documents with costs, disruptions, `checked_at`), update the CSV rows, merge again.
3. Write `RUN/report.json` (documents summary, season, top-3 reasons, tools, checkout check, alerts, holidays), merge once more, set `progress.json` `done: true`.
4. Tell the user the results page is ready (`server.py --page results` re-opens it) and give the same summary in chat.

### 6. Booking hand-off (`references/booking-step.md`)

Keep listening: `wait_event.py --types book`. For each request, open the same site in your browser plugin, re-search the same dates, re-select the exact flights (fare type and bags too), and stop at the passenger-details page. Write `RUN/booking_status.json` `{"message": ...}` so the page shows progress (old vs new price first if it changed). Separate tickets: one tab per part, hardest-to-replace leg first. No browser plugin: give the direct links (`links.py`).
