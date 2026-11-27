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

## Turning the form's dates into flight dates

`trip.window.basis` decides where travel days go:
- **home**: the dates include travel. The outbound journey starts (leaving home, including any train/bus to the airport) on or after `earliest`, and the return journey ends at home on or before `latest`. Nights = nights at the destination, so a trip with a 1-day journey each way uses `nights + 2` days of the window. Drop date pairs whose door-to-door journey doesn't fit.
- **destination**: the dates are days at the destination. Arrival at the destination (after the airport transfer) must be on or after `earliest`, and departure from it on or before `latest`; travel happens outside. Search outbound flights departing up to 1–2 days before `earliest` (long-haul or overnight) and returns landing home after `latest`.
- Exact mode works the same way with `leave`/`return`.
- `till_end: true` means no maximum stay: use `max_nights` = the full window length.
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
