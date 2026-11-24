# Tampered belief and forged fit reports are rejected

**Date:** 23 November 2026
**Issue:** #4 (risk R2, tampered belief from the browser)
**Frameworks:** STRIDE Tampering and Repudiation; OWASP Top 10 (2021) A04 Insecure Design and A08 Software and Data Integrity Failures

## Set up

Server started from `app/` with a fresh database each time:

```
FITTING_ROOM_DB=/tmp/test.db python server.py
```

Requests sent with curl from the same machine. `Date` and `Server` headers removed below; long JSON replies are shortened where marked; nothing else is edited. Shopper and recommendation IDs are random test values, not real people.

`FORGED` below stands for this belief, which puts every bit of probability on W34:

```
{"24":0,"25":0,"26":0,"27":0,"28":0,"29":0,"30":0,"31":0,"32":0,"33":0,"34":1}
```

## Before: the code on branch feat/3-sqlite-storage

### B1. The browser chooses the belief, and the server accepts it

The shopper reports that W29 fitted just right. The honest belief put 56% on W29. The server applies the report to whatever belief the browser sent.

```
$ curl -i -X POST http://127.0.0.1:8799/api/report \
    -H 'Content-Type: application/json' \
    -d '{"belief": FORGED, "worn": 29, "report": "right"}'
HTTP/1.0 200 OK
Content-Type: application/json

{"decision": "recommend", "size": "W34", "size_num": 34, "confidence": 1.0,
 "prior": {..., "34": 1.0}, "belief": {..., "34": 1.0}, ...}
```

The app recommends W34 with 100% confidence to a shopper whose W29 fitted.

### B2. The same report can be replayed and stored again and again

With a saved shopper ID, the same forged request sent three times returned `200 200 200`, and the wardrobe then held three identical fit reports:

```
[{'id': 1, 'product_id': '501', 'worn_size': 29, 'report': 'tight', 'created_on': '2026-11-23'},
 {'id': 2, 'product_id': '501', 'worn_size': 29, 'report': 'tight', 'created_on': '2026-11-23'},
 {'id': 3, 'product_id': '501', 'worn_size': 29, 'report': 'tight', 'created_on': '2026-11-23'}]
```

No recommendation was ever made, so nothing tied these reports to a real purchase. Fit reports are what the sensor model will be relearned from, so this is a route to poisoning the model.

### B3. A fractional size was silently cut down

`"worn": 29.9` was accepted and recorded as `"worn": 29`.

## After: the code on branch feat/4-server-side-belief

The honest flow first, to get a real recommendation ID:

```
$ curl -X POST http://127.0.0.1:8799/api/recommend \
    -H 'Content-Type: application/json' -H 'X-Shopper-Id: iyAMtG9Q_d-nIdLzginScw' \
    -d '{"owned_size": 28, "feel": -2, "intent": "regular", "query": "classic straight leg rigid non stretch jeans"}'
{"decision": "recommend", "size": "W29", "confidence": 0.5569, ..., "recommendation_id": "KaDxYj-XZewkDtirdHfK7w"}
```

### A1. Sending a belief is refused

```
$ curl -i -X POST http://127.0.0.1:8799/api/report \
    -H 'Content-Type: application/json' -H 'X-Shopper-Id: iyAMtG9Q_d-nIdLzginScw' \
    -d '{"recommendation_id": "KaDxYj-XZewkDtirdHfK7w", "belief": FORGED, "worn": 29, "report": "right"}'
HTTP/1.0 400 Bad Request
Content-Type: application/json
Content-Length: 37

{"error": "Unexpected field: belief"}
```

### A2. Relabelling the product is refused

```
$ curl -i -X POST http://127.0.0.1:8799/api/report \
    -H 'Content-Type: application/json' -H 'X-Shopper-Id: iyAMtG9Q_d-nIdLzginScw' \
    -d '{"recommendation_id": "KaDxYj-XZewkDtirdHfK7w", "worn": 29, "report": "tight", "product_id": "ribcage"}'
HTTP/1.0 400 Bad Request
Content-Type: application/json
Content-Length: 41

{"error": "Unexpected field: product_id"}
```

### A3. A made up but well formed ID is refused

```
$ curl -i -X POST http://127.0.0.1:8799/api/report \
    -H 'Content-Type: application/json' \
    -d '{"recommendation_id": "AAAAAAAAAAAAAAAAAAAAAA", "worn": 29, "report": "tight"}'
HTTP/1.0 404 Not Found
Content-Type: application/json
Content-Length: 35

{"error": "Unknown recommendation"}
```

### A4. Injection in the ID is refused before the database

```
$ curl -i -X POST http://127.0.0.1:8799/api/report \
    -H 'Content-Type: application/json' \
    -d '{"recommendation_id": "x'"'"' OR '"'"'1'"'"'='"'"'1", "worn": 29, "report": "tight"}'
HTTP/1.0 400 Bad Request
Content-Type: application/json
Content-Length: 38

{"error": "Invalid recommendation ID"}
```

### A5. Another shopper cannot report on this recommendation

Same recommendation ID, sent with a second shopper's ID. The reply is the same as for an ID that does not exist, so it does not confirm the ID is real.

```
$ curl -i -X POST http://127.0.0.1:8799/api/report \
    -H 'Content-Type: application/json' -H 'X-Shopper-Id: blYR5pw-K26vOhzbpXX8pg' \
    -d '{"recommendation_id": "KaDxYj-XZewkDtirdHfK7w", "worn": 29, "report": "tight"}'
HTTP/1.0 404 Not Found
Content-Type: application/json
Content-Length: 35

{"error": "Unknown recommendation"}
```

### A6. A fractional size is refused

```
$ curl -i -X POST http://127.0.0.1:8799/api/report \
    -H 'Content-Type: application/json' -H 'X-Shopper-Id: iyAMtG9Q_d-nIdLzginScw' \
    -d '{"recommendation_id": "KaDxYj-XZewkDtirdHfK7w", "worn": 29.9, "report": "right"}'
HTTP/1.0 400 Bad Request
Content-Type: application/json
Content-Length: 59

{"error": "Worn size is outside the published chart range"}
```

### A7. Replaying an honest report changes nothing and is stored once

The same honest report sent three times gives the same answer each time, because the server always starts from its stored prior:

```
abstain W29 0.4439 stored
abstain W29 0.4439 stored
abstain W29 0.4439 stored
```

The wardrobe then holds one fit report, not three:

```
[{"id": 1, "product_id": "501", "worn_size": 29, "report": "tight", "created_on": "2026-11-23"}]
```

### A8. The honest report still works

```
$ curl -i -X POST http://127.0.0.1:8799/api/report \
    -H 'Content-Type: application/json' -H 'X-Shopper-Id: iyAMtG9Q_d-nIdLzginScw' \
    -d '{"recommendation_id": "KaDxYj-XZewkDtirdHfK7w", "worn": 29, "report": "tight"}'
HTTP/1.0 200 OK
Content-Type: application/json
Content-Length: 691

{"decision": "abstain", "size": "W29", "size_num": 29, "confidence": 0.4439,
 "prior": {..., "28": 0.1478, "29": 0.557, "30": 0.2727, ...},
 "belief": {..., "28": 0.1809, "29": 0.4439, "30": 0.3469, ...},
 ..., "stored": true, "recommendation_id": "KaDxYj-XZewkDtirdHfK7w"}
```

This matches the demo case in the README: one tight report on W29 drops confidence from 56% to 44%, so the app abstains.

## Automated tests

`app/tests/test_server.py` repeats each attack against a real server on every push (section "Server side belief (issue #4)"). To check the tests really detect the flaw, the server was temporarily changed back to trust a belief sent by the browser: `test_belief_sent_by_the_browser_is_refused` and `test_product_sent_by_the_browser_is_refused` failed. Removing the owner check made `test_another_shoppers_recommendation_is_refused` fail. Both changes were then reverted and all tests passed.

## What this does not stop

* Anyone can still ask for a recommendation with any owned size, and then report on it. The belief is now always the server's own calculation from validated inputs, but there is no proof the shopper bought the jeans. A pilot would link fit reports to real orders.
* There is no rate limit, so many recommendations, each with one report, can still be created. Rate limiting and anomaly checks on fit reports belong in the pilot.
