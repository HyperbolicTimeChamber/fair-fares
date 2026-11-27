---
name: fair-fares
description: Finds the cheapest door-to-door trip between two places (flights plus trains/buses to other airports, positioning flights, transfers, documents, bags, optional hotels), using a local web form for input, a travel-document check, parallel searches and a final hand-off to the booking page. Use when the user wants cheap flights, the cheapest way to get somewhere, flexible-date fare searches, or help comparing airports and routes for a trip.
---

# Fair Fares

Find the cheapest door-to-door trip and take the user to the booking page. Never book.

`SKILL_DIR` = the folder containing this file. Scripts are in `SKILL_DIR/scripts/` (Python 3 standard library; `server.mjs` is the Node fallback for the form server). Run them with the user's current folder as working directory, so runs are saved in `./fair-fares-runs/`. User state lives in `~/.fair-fares/`. Below, `python3` means whichever works: on Windows that is usually `python` or `py` (a `python3` that opens the Microsoft Store doesn't count).

**Talk to the user in plain, everyday language.** Say what you want to do and why ("I'd like to install Playwright, which lets me open travel sites in a browser window you can watch"), not the command. Don't paste terminal commands, file paths or JSON into the chat unless the user asks to see them ("show me the commands"). Run commands yourself after approval.

**Ask everything at the start, then run on your own.** All questions and approvals happen in step 0 and in the form. After the user presses "Start search", do not ask anything until the results are ready, unless `settings.unattended.enabled` is false. Details: `references/unattended.md`.

## Hard rules (always)

- Never book, apply for visas, sign in, or enter payment or passport details. Names/contact details only if the user enabled "enter details" in the form **and** confirms each time.
- Visa, entry and transit information only from official government sites (embassy, immigration, foreign-ministry pages). Third-party sites may point you there; they are never the source.
- Respect site terms. Visible browser, randomised pauses, modest request counts, one subagent per website. At a CAPTCHA or block: stop on that site, log it, move on. Never get around bot protection.
- Ask before installing anything, all in one batch in step 0. Describe each install in plain words (the `plain` field from the setup check); show the exact commands only if the user asks.
- Never fall back silently: when a tool is missing or blocked, say what changes and which fallback you use.

## Workflow

### Before anything: quick update check (asks first)

Run `python3 SKILL_DIR/scripts/update_check.py`. It only checks (a few seconds at most, at most once every 6 hours) and never changes anything or stops the run.
- `update_available`: ask the user in plain words, as the first question of the run, e.g. "A newer fair-fares (1.3.0) is available: <notes>. Update now? <how>". Then:
  - **yes**: run `update_check.py --apply`. If it says `updated`, **read this SKILL.md again** before going on, because the instructions may have changed. If `updated_next_session`, say it arrives next session and carry on with this one. If `failed` or `update_available` (local edits), say so in one line and carry on.
  - **no**: run `update_check.py --decline` and carry on; that version won't be offered again.
- Anything else (`up_to_date`, `skipped_recent`, `declined`, `offline`): say nothing.

### 0. One approval round (start of every run)

Collect every approval the run can need in **one** exchange, then don't ask again:
1. Run the setup check (step 1) and show a short, plain status list. For everything missing, explain in a sentence what it is and what you'd lose without it; the user approves or skips them all at once. Things that need the user's click (a browser extension, a connector) get simple step-by-step instructions.
2. Permissions for running unattended: ask in plain words, e.g. "So I don't stop to ask permission for every step while you're away, may I allow this skill's own helpers, web searches and the browser tools for this folder?" If yes, run `python3 SKILL_DIR/scripts/setup_check.py --agent <you> --permissions` and add its rules to the agent's settings yourself (Claude Code: `.claude/settings.local.json` in the current folder; `~/.claude/settings.json` only if the user wants it everywhere). Options to offer: **yes, set it up**, **I'll approve each step myself**. Show the rules only if asked.
3. Tell the user the remaining run decisions are in the form's **Run on its own** card (page 3): earlier runs, documents the official re-check finds, the booking hand-off, and entering names for the top 3. Defaults are safe.
4. Save what was approved to `~/.fair-fares/approvals.json` (`{"at", "installs_approved", "installs_skipped", "permissions": "added|user|manual"}`). From here, only the form's answers and this file decide.

### 1. Setup check (every run; cached, so fast when nothing changed)

1. Identify yourself as one of: `claude-code`, `codex-app`, `codex-cli`, `grok`, `gemini`, `cursor`. Then run
   `python3 SKILL_DIR/scripts/setup_check.py --agent <you>` (add `--refresh` to bypass the cache).
2. For items with `status: agent_check`, look at **your own tool list**: the browser plugin (see `references/setup-and-portability.md`) and a Kiwi.com tool (`search-flight` from `mcp.kiwi.com`). If Kiwi is connected, just use it.
3. Show a short status list (✓ ok / ✗ missing / ⚠ out of date / – not needed here), using each item's `plain` description. For every missing item, offer exactly:
   1. **Install it for me**: run the `install.commands` yourself after the user approves (show them only if asked). For clicks (browser extensions, marketplace installs, connectors), give simple steps and the link from `install.manual`, then wait.
   2. **I'll install it myself**: give simple steps (commands only if the user wants them), then re-run the check with `--refresh`.
   3. **Skip** (optional items only): say what changes (`fallback` field), then use the fallback.
   Required: Python or Node, Playwright and its Chromium. Visa data older than 31 days → offer `update_data.py --visa`.
4. If the user agrees (ask in step 0), run once with `--test-model` to confirm the small model works for the document check.
Details and per-agent notes: `references/setup-and-portability.md`.

### 2. Form

1. Start the server in the background and leave it running:
   `python3 SKILL_DIR/scripts/server.py` (no Python → `node SKILL_DIR/scripts/server.mjs`). It opens the form in the user's browser, pre-filled from last time. Tell the user the URL it prints.
2. Wait for "Start search": `python3 SKILL_DIR/scripts/wait_event.py --types start` (blocks up to 9 minutes; exit code 2 = timeout, run it again; keep the user informed). Without Python, watch `~/.fair-fares/events.jsonl` for a new `start` line.
3. Read `~/.fair-fares/settings.json`. Field meanings: `references/form-and-settings.md`. From now on, when `unattended.enabled` is true, follow `references/unattended.md`: no questions; anything not pre-approved is skipped safely and added to `report.json` → `decisions_needed`.

### 3. Preparation (`references/preparation.md`)

1. Unattended: `python3 SKILL_DIR/scripts/prepare_run.py --auto` (follows the form's choice). Attended: run it without flags; if `previous_runs` is non-empty, ask **reuse** (`--reuse PATH`) or **start fresh** (`--new`), else `--new`.
2. `python3 SKILL_DIR/scripts/fx.py --to <currency>` once: one ECB reference rate for the whole run.
3. Quick destination research, official re-check of the form's document results, holidays/events. Attended: report differences and ask only about new findings. Unattended: apply `unattended.new_documents` (`add` = add the cost to every option and list it; `list` = only list it) and note it in `report.json`.
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
4. Tell the user the results page is ready (`server.py --page results` re-opens it) and give the same summary in chat, starting with anything in `decisions_needed`. If `unattended.handoff` is `top1`, open the #1 pick at passenger details (step 6) without waiting.

### 6. Booking hand-off (`references/booking-step.md`)

Keep listening: `wait_event.py --types book`. For each request, open the same site in your browser plugin, re-search the same dates, re-select the exact flights (fare type and bags too), and stop at the passenger-details page. Write `RUN/booking_status.json` `{"message": ...}` so the page shows progress (old vs new price first if it changed). Separate tickets: one tab per part, hardest-to-replace leg first. No browser plugin: give the direct links (`links.py`).
