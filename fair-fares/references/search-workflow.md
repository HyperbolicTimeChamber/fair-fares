# Search workflow (lead agent + subagents)

## Rules for every subagent (paste into each brief)
- Tool order: flight connector (Kiwi.com `search-flight`) → Playwright script writing CSV → Playwright MCP for one-off interactions → the agent's Chrome plugin only when the others are blocked.
- Never read whole pages into context. Extract only the fields you need (scripts, `browser_evaluate`, targeted snapshots) and write rows to `RUN/results/<letter>_<site>.csv` with the header from `RUN/results/SCHEMA.csv`. Read only CSVs.
- Drop options that break the user's limits before saving: max stops, max door-to-door hours each way, things to avoid, cabin, bags.
- One site, one owner: only the subagent named below uses a given website. Ask the lead before touching another site.
- Visible browser, randomised pauses (4–10 s), modest request counts. CAPTCHA or block: stop on that site, log it, move on. Never get around bot protection.
- Prices in the user's currency using the run's ECB rate (`fx.py --convert AMOUNT CUR --to USERCUR`); keep `original_price_and_currency` and `exchange_rate_and_date`; note foreign-transaction-fee risk in `risks` when charged in another currency.
- `total_cost_all_travellers` covers **all** travellers. Bag fees for the chosen number of bags each way.
- Return to the lead only: best 5 (one line each), sites that worked, sites blocked. No page dumps.

## Coverage log (mandatory, no skipping)
Before phase 2, write `RUN/coverage.json` with the full source list:
```json
{"local_sites": ["MakeMyTrip", "Cleartrip", "Ixigo", "EaseMyTrip"],
 "airlines": ["Qatar Airways", "IndiGo", "Air India", "Turkish Airlines", "Emirates", "Etihad Airways"],
 "sources": [{"agent": "B", "site": "Kayak", "status": "done", "note": "8 rows"}]}
```
- `local_sites`: every booking site from research that is popular in the destination country. `airlines`: every carrier seen serving the route in phase 1 and in research.
- Each subagent appends one entry per site it covers. Status: `done` (searched, rows saved), `no_results`, `blocked` (CAPTCHA, region block, sign-in wall: note says which), `not_applicable` (with reason). `skipped` is never acceptable.
- Every required comparison site gets its own entry: Skyscanner, Kayak, Momondo, eDreams/Opodo, Trip.com, Booking.com Flights.
- When a tool fails (e.g. the Google Flights scan times out), use the next tool in the order below for that same phase (Kiwi, then a comparison site's flexible-date or month view). Never drop the phase.
- **A "not available in your region" page is not automatically a block.** Many sites (e.g. MakeMyTrip) refuse a deep link into their search results from abroad but work normally from their own homepage. Before logging `blocked`, in this order:
  1. Read the page's message. If it points to the homepage, an international site or a country version (e.g. "please visit the website homepage", a `.global`/`.com`/country domain link run by the same company), go there.
  2. Search the way a person would: open the homepage, use the site's own search form (type origin, destination, dates, passengers), and read the results. Deep links are a shortcut, never a requirement.
  3. Try the same company's international or country version once if the homepage also refuses.
  Log `blocked` only when all of these fail, with a note saying what was tried (e.g. "deep link: region page; homepage form: region page; .global: not offered").
- Allowed: following the site's own links and forms, its own regional versions, accepting only essential cookies. Never allowed: VPN, proxy, changing the browser's location, user agent or language to pretend to be elsewhere, clearing cookies to reset a limit, or anything that gets around a CAPTCHA or bot check. Those stop the site: log `blocked`.
- Tell the user about every `blocked` site in `decisions_needed` with the link, so they can check it themselves in their own browser.
- Cross-check: the cheapest fares from each site go in its CSV even if they break a limit, with accurate `depart_datetime`/`return_datetime` (with times), `stops`, `layover_details` (write "overnight" for an overnight wait), `ticket_type` (`self_transfer` whenever any leg is a separate ticket) and bag facts (`baggage_included`, `bag_fees`, or "no checked bag" in notes). `merge_results.py` decides from these fields which rows break the user's current settings and lists them under "Outside your limits" with the reason. Then a lower price seen elsewhere can be explained (no bag, 3+ stops, 03:45 departure), and the user can re-rank after changing a setting without a new search.
- Limits in briefs: copy the form's definitions exactly (`references/form-and-settings.md`): early departure = before 06:00.
- `merge_results.py` reads this file and reports `coverage_gaps`. Results are not final until the list is empty.

## Turning the form's dates into flight dates

`trip.window.basis` decides where travel days go:
- **home**: the dates include travel. The outbound journey starts (leaving home, including any train/bus to the airport) on or after `earliest`, and the return journey ends at home on or before `latest`. Nights = nights at the destination, so a trip with a 1-day journey each way uses `nights + 2` days of the window. Drop date pairs whose door-to-door journey doesn't fit.
- **destination**: the dates are days at the destination. Arrival at the destination (after the airport transfer) must be on or after `earliest`, and departure from it on or before `latest`; travel happens outside. Search outbound flights departing up to 1–2 days before `earliest` (long-haul or overnight) and returns landing home after `latest`.
- Exact mode works the same way with `leave`/`return`.
- `till_end: true` means no maximum stay: use `max_nights` = the full window length.
- **One way** (`trip_type: oneway`): there is no return and no nights. With basis `home`, `earliest`–`latest` (or `leave`) are the days the journey may start; with basis `destination`, they are the days the user must arrive. Search one-way fares only (`ticket_type = one_way`, return columns empty); still compare airports, ground legs and positioning flights, and compare a one-way ticket with the outbound half of cheap return fares only when the airline allows it (some charge no-show fees for unused returns: note that in `risks`). `gflights_scan.py --one-way`.
Tell the subagents which rule applies and the resulting flight-date ranges.

## Phase 1: broad scan (alone, first)
**A**: fares from the closest airport (and other home-city airports) to all destination airports across every valid date pair in the window.
- Kiwi.com tool: query date ranges/flexible dates; it returns booking links.
- No Kiwi: `gflights_scan.py --from BER --to GOI,GOX --earliest … --latest … --min-nights … --max-nights … --adults … --children ages --currency … --max-stops … --out RUN/results/A_gflights.csv`. Capped at 30 queries; stops at any block. Pass flight dates worked out with the rules above (for basis `destination`, `--earliest` may be a day before the form's date).
- Output: the 5 cheapest date windows and any mixed-airline itineraries.
- More than one traveller: also price 1 traveller on the best windows. A lower per-person price than the group total ÷ n means last-seat pricing: note it in `risks` (splitting bookings may save money).

## Phase 2: deep search, in parallel, on the 5 cheapest windows ±2 days
- **B, comparison/booking sites**: Skyscanner, Kayak, Momondo, eDreams/Opodo, Trip.com, Booking.com Flights, plus the destination country's main local sites (from research). Round trip, one-ways, open-jaw; coupons and card offers; other country versions/currencies where practical (convert, note FX fees).
- **C, airlines direct**: every airline serving the route incl. low-cost and charters. Changeable fares and change fees if `fare_flex = changeable`. Free/cheap stopover programmes (`stopover_option`). Award seats if the user has miles/points (`miles_option`, listed separately).
- **D, alternative airports + ground** (only if `alternatives.enabled`):
  - With "No limit": prioritise airports most likely to save money (big hubs, airports with direct or cheap flights to the destination). Skip airports where ground cost alone wipes out the saving. Report checked and skipped airports.
  - Each ground leg: compare all operators (FlixBus, BlaBlaCar Bus, national rail saver/early-bird fares, night trains, regional trains), apply railcards, check nearby departure times, pick the cheapest that meets the buffer, list the next alternative in `ground_*_details`.
  - Positioning flights from the closest airport to the hub, incl. bag fees, getting to the home airport and airport changes. Treat as separate-ticket self-transfers with the larger buffer.
- **E, hub routing**: fly to a hub in the destination country/region, then a separate onward flight, train or bus. Flag self-transfer risks.
- **F, hotels and packages** (only if hotels included): hotels in the stay area meeting budget/rating/must-haves for each window; flight+hotel packages vs booking separately.
- **G, logistics and extras**: airport → stay-area transfer cost/time for every destination airport (write `RUN/results/G_transfers.csv` or a table in research.md the others use); insurance estimate if requested.
- **All**: round trip vs one-ways vs open-jaw; coupons; holiday price effects; baggage costs; layover quality (overnight, airport changes, terminal changes).

Without subagents: run A, then B…G one after another with the same briefs, and keep the one-site-one-owner rule trivially.

## Per-direction pricing (lead agent)
Price outbound and return independently, from/to the closest airport and every reachable alternative airport (adding one-way ground or positioning-flight cost). Combine every best outbound with every best return, priced three ways: open-jaw/multi-city single ticket, two separate one-ways, simple round trip from the closest airport. Example: Berlin → train to Amsterdam → fly AMS–GOI, return GOI–BER direct.

## Buffers
Buffer = base minimum for the connection type + delay allowance for the specific operator/route/airline from published punctuality data, adjusted by buffer style.

| Connection | Base minimum (standard) |
|---|---|
| ground → flight (to departure) | 2 h before departure (3 h long-haul) |
| flight → flight, separate tickets | 3 h same terminal, 4 h with airport/terminal change or re-check of bags |
| flight → ground home | 1.5 h after scheduled arrival (long-haul) / 1 h (short-haul) |

Delay allowance: use the operator's published punctuality/on-time stats (e.g. national rail punctuality reports, airline on-time data). E.g. a train at 65% punctuality on the route with typical delays of 30 min → add 30–45 min.
Style: Relaxed ×0.75, Standard ×1, Extra safe ×1.5, Custom = base + custom minutes. Record the basis in `buffers_and_delay_basis`.
Too tight → find an earlier train/bus; else price an overnight stay near the airport (`extras_cost`); else mark "risky connection" with the reason in `risks`. On the return, if a delay would miss the last train/bus home, add a hotel or taxi.

## Minimum saving
Alternative airports, positioning flights and separate-ticket routes are recommended only if they beat the direct option by at least `alternatives.min_saving`; the rest go to "Smaller savings" (done by `merge_results.py`). Always show saving and extra time together, e.g. "€120 cheaper, 11 hours longer".
