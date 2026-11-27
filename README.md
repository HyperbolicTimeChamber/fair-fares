# fair-fares

An Agent Skill that finds the **cheapest door-to-door trip** between two places: flights, trains and buses to cheaper airports, positioning flights, airport transfers, bags, travel documents and optional hotels. Then it takes you to the booking page and stops at passenger details. It never books.

Works with Claude Code, Codex (app and CLI), Grok Build, Gemini CLI and Cursor. It follows the open [Agent Skills](https://agentskills.io) format.

## Install

```sh
git clone <this repo> && cd <repo>
./install.sh            # or: python3 install.py   (shows targets, asks before copying)
```

It copies `fair-fares/` to each detected agent's skills folder:

| Agent | Folder |
|---|---|
| Claude Code | `~/.claude/skills` |
| Codex | `~/.agents/skills` |
| Grok Build | `~/.grok/skills` |
| Gemini CLI | `~/.gemini/skills` |
| Cursor | `~/.cursor/skills` |

Options: `--yes`, `--only claude,codex`, `--all` (create folders even for agents not detected), `--uninstall`.
Or with the skills CLI: `npx skills add <owner>/<repo>`.

**Requirements:** Python 3.9+ (preferred) or Node 18+, plus Playwright and its Chromium. Optional: Playwright MCP, your agent's browser plugin, the Kiwi.com connector (`https://mcp.kiwi.com`, free, no key), and a small model through your agent's CLI. The skill's setup check finds what's missing and offers to install it. It always asks first.

## Use

Ask your agent something like *"find me the cheapest way from Berlin to Goa in March"*. The skill:

1. **Setup check**: shows a status list and offers install / do-it-yourself / skip (with fallbacks) for anything missing.
2. **Form**: opens a local page (`http://127.0.0.1:8765`). It has four pages: trip, travellers & documents, document check & preferences, results. It's pre-filled from last time. Press **Start search**.
3. **Preparation**: offers to resume a previous run, takes one ECB exchange rate, researches the destination, holidays and season, and re-checks documents on official government sites.
4. **Search**: runs a broad date scan (Kiwi.com, or a low-volume Google Flights script) first. Then it searches in parallel: comparison sites, airlines direct, alternative airports with ground transport, hub routing, hotels, and transfers. It uses subagents where your agent has them.
5. **Merge & verify**: ranks options by total door-to-door cost for everyone, then checks the top 10 for price, transit visas and disruptions.
6. **Results**: shows the top picks, the top 10 with cost breakdowns, miles options and smaller savings on the form's results page and in chat. Each run is kept in `./fair-fares-runs/<destination>-<date>/` with `all_options.csv`.
7. **Take me to booking**: your agent's browser re-selects the exact flights and stops at passenger details for you.

Your settings are kept in `~/.fair-fares/`.

## Layout

```
fair-fares/
  SKILL.md                 workflow (short); details in references/
  scripts/                 setup_check, server (.py + .mjs fallback), wait_event, doc_check,
                           prepare_run, fx, gflights_scan, links, merge_results, update_data
  assets/form/             the web form (HTML/CSS/JS, no build step)
  assets/data/             embedded datasets + doc_rules.json + meta.json
  assets/results_schema.csv
  references/              setup & portability, form & settings, preparation, search workflow,
                           CSV schema, merge/verify/output, booking step, data sources
install.py / install.sh
```

## Data sources

See [`fair-fares/references/data-sources.md`](fair-fares/references/data-sources.md). In short:
- Countries, regions and currencies: [countries-states-cities-database](https://github.com/dr5hn/countries-states-cities-database), ODbL-1.0.
- Cities with population ≥ 15,000: [GeoNames](https://www.geonames.org/), CC BY 4.0. Contains information from GeoNames.
- Airports with scheduled passenger service: [OurAirports](https://ourairports.com/data/), public domain.
- Visa requirements: [Passport Index dataset](https://github.com/ilyankou/passport-index-dataset), MIT. The newest upstream data is dated **18 Feb 2026**, so the setup check flags it as stale and offers to refresh it.
- Exchange rates: ECB euro reference rates, fetched once per run.

Refresh all data with `python3 fair-fares/scripts/update_data.py`.

## Limitations

- **Not legal or visa advice.** The form's document check is a first pass from a dataset and a curated rules file. Fees and processing times there are estimates. The search re-checks everything on official government sites, but always confirm with the official source before you travel.
- **Prices change and sites block automation.** The skill keeps requests light, stops at any CAPTCHA or block and reports it. Some sites will simply be skipped. "Fees may be added" means not every fee was visible before personal details were entered.
- **Google Flights fallback.** The scan is used only when Kiwi.com isn't available. It's capped at 30 queries in a visible browser, and stops at the first block. Its page parsing depends on Google's current markup and may need updating.
- **Agent features change quickly.** Browser plugins, CLI flags and small-model names differ by agent and version. Run the setup check with `--test-model` to confirm on your machine. Model names are set in `~/.fair-fares/config.json`. The Codex small-model name and the Grok CLI flags are best guesses until that test passes.
- **Node-only machines.** `server.mjs` covers the form and the dataset part of the document check. The small-model step and the helper scripts (merge, run folders, scan) need Python, or the agent does those steps by hand.
- **Separate tickets.** Self-transfer and separate-ticket routes are cheaper partly because no one protects your connection. Buffers reduce the risk; they don't remove it.

## Safety rules built in

The skill never books, signs in, applies for visas, or enters passport or payment details. It uses official government sources for entry and transit rules and never gets around bot protection. It asks before installing anything.

## License

MIT for the code (see `LICENSE`). The datasets keep their own licences (above).
