# Booking hand-off ("Take Me to Booking")

Trigger: a `book` event (`wait_event.py --types book`) with `option_id`, or, when `unattended.handoff` is `top1`, the #1 pick right after results are ready. Find the row in `RUN/all_options.csv`.

1. Write `RUN/booking_status.json` → `{"option_id", "message": "Opening Skyscanner…", "at"}`; update it at each step (the page shows it).
2. With the agent's browser plugin (see setup-and-portability.md; fallback Playwright MCP in a visible browser):
   - Open the same site (`site_or_operator`, `link`), re-search the same airports and dates, same passengers.
   - Re-select the exact flights (same flight numbers/times), the same fare type, and the chosen bags if the site offers them before passenger details.
   - Stop at the passenger-details page. Do not type anything there unless the user enabled "enter details" and confirms now; never passport or payment details.
3. If the price changed, tell the user old vs new **before** handing over (chat and `booking_status.json`), and update the CSV row.
4. Separate-ticket trips: open each part in its own tab in the order of the option's `booking_parts` (hardest to replace first: long-haul flight, then positioning flight, then train/bus, then hotel). The results page has already told the user how many tabs to expect ("Take Me to Booking (3 Tabs)"). Say the order and why.
5. Hand over: "Your browser is at passenger details on <site> for <flights>, <price>. Check <checkout item> before paying."

No browser plugin or it is blocked: give direct links (`python3 scripts/links.py --from … --to … --out … --back … --adults … --children ages --currency …`) plus the airline/operator site, and the exact flights to pick.
A CAPTCHA or sign-in wall: stop, hand the tab to the user, never get around it.
