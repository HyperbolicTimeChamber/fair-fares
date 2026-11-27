# Shared CSV schema

Header: `assets/results_schema.csv` (copied to `RUN/results/SCHEMA.csv`). One row per complete door-to-door option. Leave unknown cells empty; never invent numbers. All money in the user's currency unless the column says otherwise.

| Column | Meaning |
|---|---|
| option_id | Unique id, prefixed by subagent letter: `B-sky-3` |
| source_agent | A…G or `lead` |
| route_summary | Short human line: `Train BER→AMS, AMS→GOI (KLM) / GOI→BER (IndiGo)` |
| site_or_operator | Where it was priced (`Skyscanner → Pegasus`, `KLM.com`, `DB + FlixBus`) |
| airlines_out / airlines_back | Marketing carriers |
| depart_airport, arrive_airport, return_from_airport, return_to_airport | IATA codes |
| depart_datetime / return_datetime | Local `YYYY-MM-DD HH:MM` of the first flight each way |
| nights | At destination (filled from dates if empty) |
| layover_details | `IST 2h05 (same terminal)`; flag overnight or airport changes |
| ground_out_details / ground_back_details | Operator, times, price each, next alternative |
| positioning_flight_details | Separate ticket to/from the hub incl. bag fee |
| buffers_and_delay_basis | Base + delay allowance + source of punctuality data |
| total_travel_time_out / _back | Door to door: `22h 10m` |
| stops | Stops on the worst direction |
| baggage_included, bag_fees | What's included; fees for the chosen bags (all travellers) |
| fare_type, change_fee | e.g. `Economy Light`, change fee if known |
| ticket_type | `round_trip` / `one_way` / `open_jaw` / `separate_one_ways` / `self_transfer` / `package` (a one-way trip uses `one_way` and leaves the return columns empty) |
| stopover_option | Free/cheap stopover offered |
| flight_cost, ground_cost, destination_transfer_cost, hotel_name, hotel_cost | Components |
| document_costs | Fees for documents the user chose "Add cost to estimate" |
| transit_document_costs | Transit visas/authorisations found in verification |
| insurance_estimate, payment_fees, extras_cost | Extras incl. airport hotel/taxi for tight connections |
| total_cost_all_travellers | Sum for everyone (filled by merge if empty) |
| currency | User's currency |
| original_price_and_currency, exchange_rate_and_date | e.g. `1,640 USD`, `ECB 0.9128 2026-11-27` |
| saving_vs_direct, extra_time_vs_direct | Filled by merge if empty |
| price_status | `confirmed` (all fees visible) / `fees_may_be_added` |
| coupon_or_offer, miles_option | Codes/card offers; award price |
| link | Search or deep link (never a personal/session URL with details in it) |
| checked_at | ISO time of the last price check |
| booking_parts | Separate bookings in the order to make them, hardest to replace first: `KLM: AMS→GOI \| IndiGo: GOI→BER \| Deutsche Bahn: BER→AMS`. Leave empty for a single booking; the merge infers it if missing. The results page shows "Take Me to Booking (3 Tabs)" |
| risks, notes | Self-transfer, tight buffer, FX fee, last-seat pricing, disruptions… |
