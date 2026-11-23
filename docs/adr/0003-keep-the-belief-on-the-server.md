# ADR 0003: Keep the belief on the server and refer to it by a recommendation ID

**Status:** Accepted, 23 November 2026

## Context

After a recommendation, the browser held the belief (the probability of each size) and sent it back with the fit report. The server then applied Bayes' rule to whatever it was sent. Anyone could send their own probabilities and get any size back at 100% confidence, and with a saved shopper ID the same report could be stored any number of times. Fit reports are the data the sensor model is relearned from, so this is both a tampering risk (STRIDE) and a route to poisoning the model.

## Decision

* `POST /api/recommend` stores the belief it worked out in a `recommendations` table and returns a random 128 bit `recommendation_id`. The browser still receives a copy of the belief so it can draw the chart, but that copy is only for display.
* `POST /api/report` accepts exactly three fields: `recommendation_id`, `worn` and `report`. Any other field, including `belief` and `product_id`, is refused with 400 rather than ignored, so a client that tries is told clearly and the attempt is visible.
* The product comes from the stored recommendation, not the request.
* A recommendation made for a shopper can only be reported on with that shopper's ID. A wrong owner gets the same 404 as an ID that does not exist.
* Every report starts from the stored prior. The posterior is returned but never saved over the prior, so repeating a report cannot push the belief further.
* A fit report is stored at most once per recommendation. A unique index on `fit_reports.recommendation_id` and an upsert mean a second report replaces the first, which also lets a shopper correct the size they wore.
* `worn` must be a whole number in the chart. Python's `True` and `29.9` are both refused.

## Consequences

* The client can no longer choose the probabilities the server reasons from. The confidence shown after a report is the server's own calculation.
* One stored row per recommendation, including for shoppers who have not saved a wardrobe. That data is a product ID and eleven probabilities, with no owned size, feel or search text, but anonymous rows still need a retention period (part of #5).
* Databases made by the previous version are upgraded in place: `storage._upgrade` adds the new column and keeps existing rows.
* The recommendation ID, like the shopper ID, is a bearer secret. Anyone who sees it can report on it. Acceptable for a prototype with no names or body data; a pilot needs real accounts and links to orders.

## Alternatives considered

* **Sign the belief** (for example an HMAC over the JSON) and keep it in the browser. Rejected: it stops changes but not replays, needs a secret key to manage, and is harder to explain than a lookup.
* **Ignore unknown fields silently.** Rejected: safe, but hides a misbehaving client and leaves no clear evidence that tampering was attempted.
* **Recompute the belief from the original inputs at report time** instead of storing it. Rejected: the browser would have to send the inputs back, which reopens the same tampering route, and the server would need to keep owned size and feel per recommendation, which is more personal data than eleven probabilities.
* **Save the posterior over the prior after each report,** so beliefs build up. Rejected for now: it lets one shopper move the belief without limit by repeating reports. Pooling reports belongs in relearning the sensor offline, not in each request.
