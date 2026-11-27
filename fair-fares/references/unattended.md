# Unattended runs

Goal: the user answers everything once (step 0 + the form) and can walk away. After "Start search" nothing waits for a human until results are ready.

## Where each approval comes from

| Decision | Asked in | Stored in |
|---|---|---|
| Installs (Playwright, browser, MCPs, connectors) | Step 0, one batch | `~/.fair-fares/approvals.json` |
| Tool permissions (so the agent never pauses at a prompt) | Step 0 | the agent's own settings file |
| Small-model test call | Step 0 | `approvals.json` |
| Reuse an earlier run vs fresh search | Form → Run on its own | `settings.unattended.previous_run` |
| Document found by the official re-check | Form → Run on its own | `settings.unattended.new_documents` (`add` / `list`) |
| Which documents' costs to include | Form page 3, per item | `settings.doccheck.choices` |
| Names/contact for the top 3 (final prices) | Form → Final prices | `settings.prefs.enter_details` (ticked = approved for this run's top 3) |
| Booking hand-off | Form → Run on its own | `settings.unattended.handoff` (`wait` / `top1`) |
| CAPTCHA / block | Not a choice | always: skip the site, log it |

## Claude Code permissions

`setup_check.py --agent claude-code --permissions` prints allow-rules scoped to this skill's scripts, `~/.fair-fares/`, `./fair-fares-runs/`, WebSearch/WebFetch, Playwright MCP, Kiwi.com, Claude in Chrome and subagents (`Task`). Merge them into the `permissions.allow` list of:
- `~/.claude/settings.json`: every project, or
- `.claude/settings.local.json` in the folder the user runs searches from: that folder only (narrower; preferred).

Only edit the file after the user approves; keep existing entries. Never add `--dangerously-skip-permissions`, never disable sandboxing or other safety settings. Other agents: grant the equivalent through their own approval settings and say exactly what you changed.

If a tool prompt still appears mid-run (a rule didn't match), the run pauses there; that's the agent's own safeguard. Mention it in the summary and suggest the extra rule for next time.

## Rules while unattended

- **No questions.** When something comes up that the approvals don't cover, take the safe default below and add a line to `RUN/report.json` → `decisions_needed` (e.g. `"Ryanair asked to sign in to show prices: skipped. Open it yourself: <link>"`). The results page shows these first.
- **Install needed mid-run** (not approved in step 0) → use the fallback, don't install, add to `decisions_needed`.
- **Site wants sign-in, a cookie wall that only accepts all, or a CAPTCHA** → choose the most private option or skip the site; log it.
- **Entering names/contact** → only if `enter_details` was ticked, only for the top 3, never passport or payment details. Otherwise record `fees_may_be_added`.
- **Transit documents found in verification** → always add their cost to that option (the spec requires it) and flag it.
- **Prices that change while verifying** → record the new price and the old one in `notes`.
- **Booking** → never. The hand-off stops at passenger details, and with `handoff: wait` it only happens when the user presses the button.
- Keep `RUN/progress.json` current so the user can glance at the results page any time.

## When the user comes back

The chat summary starts with `decisions_needed` (if any), then the top 3, then the usual output. The booking hand-off (step 6) is the only interactive part left.
