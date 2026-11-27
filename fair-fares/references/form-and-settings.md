# Form and settings

The form (`assets/form/`) is served by `scripts/server.py` on 127.0.0.1 (port 8765 or the next free one). It autosaves every change to `~/.fair-fares/settings.json` (so it opens pre-filled), and "Start search" writes the same file plus a `start` event in `~/.fair-fares/events.jsonl`. `prepare_run.py` copies it into the run folder.

Server API (POSTs need header `X-Fair-Fares: 1`): `GET /api/settings`, `POST /api/settings`, `POST /api/start`, `POST /api/doccheck`, `GET /api/destdocs?country=XX&children=0|1`, `GET /api/results`, `POST /api/book`, `GET /api/booking-status`, `GET /api/meta`, `GET /data/*.json`.

## settings.json

```jsonc
{
  "trip": {
    "home_city": {"name","region","country","lat","lon","label"},
    "closest_airport": {"code","name","city","country","lat","lon","label"},   // searched first and most thoroughly
    "alternatives": {"enabled": bool, "max_ground_hours": number|"", "no_limit": bool, "min_saving": number|""},
    "destination": {"type": "country|region|city","name","country","region?","lat","lon","label"},
    "destination_airports": [ {code,...} ],        // empty = any airport serving the destination
    "stay_area": "text",                          // used to price the airport transfer
    "window": {
      "basis": "home|destination",   // home = dates include travel days; destination = dates are only the days at the destination
      "mode": "flexible|exact", "earliest","latest","min_nights","max_nights",
      "till_end": bool,              // true = no upper limit: stay can last up to the whole window (ignore max_nights)
      "leave","return"               // exact mode
    }
  },
  "travellers": {
    "adults", "children",
    "list": [{"id": "a1|c1", "name", "child": bool, "age"}],
    "passport_mode": "same|per",
    "passports": {"*": [{"country","expiry"}], "a1": [...]}   // "*" applies to everyone when mode = same
  },
  "documents": [{"id","label","kind": "destination|other","applies_to": ["a1",...]}],
  "doccheck": {"result": {...}, "choices": {"<traveller>:<doc_id>": "add|arrange"}},  // "add" = include cost in totals
  "prefs": {
    "cabin", "bags" (checked bags per person), "max_stops" (each way; 3 = 3+), "max_hours_each_way" (door to door, "" = none),
    "avoid": {"overnight_layovers", "early_departures"},  // early = before 06:00
    "fare_flex": "cheapest|changeable",
    "buffer": {"style": "relaxed|standard|extra|custom", "custom_minutes"},
    "currency", "miles", "railcards", "insurance": "yes|no",
    "hotels": {"enabled","budget","min_rating","must_haves"},
    "enter_details": bool    // may enter names/contact for top 3; unattended = approved for this run, else ask each time; never passport/payment
  },
  "unattended": {            // see unattended.md
    "enabled": bool,         // true = no questions after Start search
    "previous_run": "fresh|reuse",
    "new_documents": "add|list",
    "blocked_sites": "skip",
    "handoff": "wait|top1"
  }
}
```

## Document check (page 3)

Runs when page 3 opens, again only when its inputs change, and on "Check again". Never while typing.
1. Embedded visa dataset + curated `assets/data/doc_rules.json` → instant status per traveller (no model). Dataset date shown.
2. Questions the data can't answer (special documents, unknown destinations, visa-on-arrival fees…) go to the agent's small model through the server, which must return JSON. Cursor or no model: they are listed as "pending"; ask the user in chat or check official sites during preparation.
3. Each item: OK / Missing / At risk, fee, processing time, warning if processing could clash with the earliest departure, and "Add cost to estimate" / "I'll arrange it".

Use `choices` when costing: `add` → put the fee (converted) in `document_costs` for every option, for the affected travellers.

Destination document list (page 2) comes from the rules file; destinations it doesn't cover get extra items from the small model (`source: "model"`), cached in `~/.fair-fares/destdocs_cache.json`.
