# Merge, verify, output

## Merge
Before merging, make sure every row has destination transfer costs (from G), the document costs the user chose to include, insurance (if requested), bag fees, and hotels (if included).
`merge_results.py` combines `results/*.csv`, de-duplicates the same itinerary (keeps the cheapest fare, carries over cost parts the other source priced), computes saving and extra time vs the direct round trip, applies the minimum-saving rule, ranks by total door-to-door cost for all travellers, writes `all_options.csv` and `results.json`, and diffs against the previous run.
If deep search found cheaper dates than phase 1, run a targeted follow-up on those dates, then merge again.

## Verify the top 10, one at a time
1. **Price**: go as far as possible without entering personal details and record the price. `price_status = confirmed` if all fees are visible; otherwise `fees_may_be_added` with an estimate from the site's published fee/payment-charge pages in `payment_fees`. Enter names/contact details only if `prefs.enter_details` is on **and** the user confirms for this option. Never passport or payment details.
2. **Transit documents**: for every connection country and each traveller's nationality, check transit visa/authorisation rules on official sites (consider residence permits/visas from the form: e.g. some nationalities transit visa-free with a valid US visa). If required, add the cost to `transit_document_costs`, describe it in `risks` (with processing time), and it is flagged in the table and totals.
3. **Disruptions**: recent airspace closures, strikes, frequent delays on that route/operator → `risks`.
4. Set `checked_at`.
Then merge again.

## report.json (narrative parts for the results page)
```json
{
  "documents": [{"traveller": "Anna", "has": "German passport", "missing": "Indian e-Visa", "costs_included": "≈ €23", "apply_by": "2027-02-27"}],
  "season": "March: hot and dry, end of peak season; Holi on 22 Mar raises fares that week.",
  "top3": [{"option_id": "D1", "reason": "Cheapest by €310; train leg has 3 h buffer", "risks": "Separate tickets"}],
  "holidays": [{"name": "Holi", "start": "2027-03-22", "end": "2027-03-23"}],
  "tools": {"worked": ["Kiwi.com", "Skyscanner"], "blocked": ["Kayak (CAPTCHA, skipped)"]},
  "checkout_check": "On Pegasus, re-check that 20 kg bags were added for all 3 travellers before paying.",
  "alerts": ["Set Google Flights alerts for BER–GOI 9–23 Mar…", "Re-run on 15 Jan or if alerts drop by 10%."]
}
```

## Output (results page and chat)
- Documents summary: what each traveller has, what's missing, costs included, apply-by dates.
- Season/weather note for the cheapest windows.
- Top 10 door-to-door options with key columns and cost breakdown (flights, ground, positioning flights, destination transfers, hotel, documents, transit documents, insurance, bag and payment fees, extras), saving vs direct and extra time.
- Miles/points options separately.
- Top 3 recommendations with a one-line reason and risks.
- Links; tools/sites that worked or were blocked; which checkout step to double-check.
- Price tracking: how to set fare alerts for the top 3 (Google Flights "Track prices", Skyscanner/Kayak alerts, airline alerts) and when to re-run; on re-runs show what changed (the page does this from `results.json.changes`).
- `all_options.csv` stays in the run folder.
In chat keep it short: top 3 with price, saving/extra time, main risk; point to the results page for the rest.
