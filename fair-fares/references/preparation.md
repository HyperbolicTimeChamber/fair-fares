# Preparation (before searching)

## Resume check
`prepare_run.py` lists earlier runs with the same destination and dates. Ask the user:
- **Reuse**: re-check prices of the saved options only (`--reuse PATH`). Re-open each option's `link`, update price columns and `checked_at`, merge. Skip phases 1–2 unless prices moved a lot.
- **Start fresh**: `--new`. The new folder records the previous run so `merge_results.py` can show what changed.

Run folder: `./fair-fares-runs/<destination>-<YYYY-MM-DD>/` with `settings.json`, `fx.json`, `results/`, `progress.json`, `report.json`, `all_options.csv`, `results.json`, `booking_status.json`.

## Destination research (quick, keep it short)
Save to `RUN/research.md`:
- Every airport serving the destination/stay area, with transfer time and rough cost to the stay area (G refines the cost later).
- Hub airports in the destination country/region (for E).
- Public and school holidays in **both** countries, plus major local events, inside the window. Add them to `report.json` → `holidays: [{"name","start","end"}]` early; the form's timeline marks them as likely price spikes.
- Typical weather/season for the window.
- Locally popular booking sites and airlines (feed into B and C).

## Official re-check of documents
For each traveller's nationality/passports: entry rules, passport validity and blank pages, e-arrival cards, onward-ticket rules, rules for children, from the destination's official immigration/foreign-ministry/embassy pages. Compare with the form's `doccheck.result`. Report differences in one short list; ask only about new findings (e.g. "ETIAS has started: add €20 per adult?"). Answer any `pending` items from the form here.
