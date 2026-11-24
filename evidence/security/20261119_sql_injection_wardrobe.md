# SQL injection attempts against wardrobe storage fail

**Date:** 19 November 2026
**Issue:** #3 (risk R1, injection into wardrobe storage)
**Frameworks:** OWASP Top 10 (2021) A03 Injection; STRIDE Tampering and Information disclosure

## Set up

Server started from `app/` with a fresh database:

```
FITTING_ROOM_DB=/tmp/e2e.db python server.py
```

Requests sent with curl from the same machine. `Date` and `Server` headers removed below; nothing else is edited. The shopper ID shown is a random test value, not a real person.

## 1. Normal save (baseline)

```
$ curl -i -X POST http://127.0.0.1:8799/api/wardrobe \
    -H 'Content-Type: application/json' \
    -d '{"product_id": "501", "size": 28, "feel": -2}'
HTTP/1.0 200 OK
Content-Type: application/json

{"shopper_id": "hfHiN07AZo9D_cZYY2Q15w", "pairs": [{"id": 3, "product_id": "501", "size": 28, "feel": -2, "created_on": "2026-11-19"}]}
```

## 2. Injection in the shopper ID, trying to read every wardrobe

```
$ curl -i http://127.0.0.1:8799/api/wardrobe -H "X-Shopper-Id: x' OR '1'='1"
HTTP/1.0 400 Bad Request
Content-Type: application/json

{"error": "Invalid shopper ID"}
```

## 3. Injection in the product, trying to drop a table

```
$ curl -i -X POST http://127.0.0.1:8799/api/wardrobe \
    -H 'Content-Type: application/json' \
    -d "{\"product_id\": \"501'; DROP TABLE owned_pairs; --\", \"size\": 28, \"feel\": 0}"
HTTP/1.0 400 Bad Request
Content-Type: application/json

{"error": "Unknown product"}
```

## 4. Injection in a number field

```
$ curl -i -X POST http://127.0.0.1:8799/api/wardrobe \
    -H 'Content-Type: application/json' \
    -d '{"product_id": "501", "size": "28 OR 1=1", "feel": 0}'
HTTP/1.0 400 Bad Request
Content-Type: application/json

{"error": "This size is outside the published chart range"}
```

## 5. Guessing a well formed but unknown ID

```
$ curl -i http://127.0.0.1:8799/api/wardrobe -H "X-Shopper-Id: AAAAAAAAAAAAAAAAAAAAAA"
HTTP/1.0 404 Not Found
Content-Type: application/json

{"error": "Unknown shopper ID"}
```

## 6. Data still intact after the attacks

```
$ curl -i http://127.0.0.1:8799/api/wardrobe -H "X-Shopper-Id: hfHiN07AZo9D_cZYY2Q15w"
HTTP/1.0 200 OK
Content-Type: application/json

{"shopper_id": "hfHiN07AZo9D_cZYY2Q15w", "pairs": [{"id": 3, "product_id": "501", "size": 28, "feel": -2, "created_on": "2026-11-19"}], "fit_reports": []}
```

Tables in the database afterwards: `shoppers`, `owned_pairs`, `fit_reports` (plus SQLite's own `sqlite_sequence`). `owned_pairs` still held all 3 rows saved during testing.

## Why they fail: two layers

1. **Input checks at the server** (`app/server.py`). The shopper ID must match `^[A-Za-z0-9_-]{16,64}$`, the product must be a catalogue ID, size and feel must be whole numbers from fixed sets. Requests 2 to 4 stop here.
2. **Parameterised queries** (`app/storage.py`). Even if a hostile value got past the checks, every query passes values through `?` placeholders, so SQLite treats them as data, never as SQL.

Layer 2 is proven on its own by unit tests that call the storage functions directly with `x' OR '1'='1`, bypassing layer 1:

* `test_injection_in_shopper_id_does_not_read_other_wardrobes`
* `test_injection_in_shopper_id_does_not_delete_everyone`
* `test_injection_text_is_stored_as_plain_data`

To check these tests really detect the flaw, `list_wardrobe` and `delete_shopper` were temporarily rewritten to build SQL with an f string (the vulnerable pattern). Both injection tests then failed, and passed again once the placeholders were restored:

```
FAIL: test_injection_in_shopper_id_does_not_delete_everyone
FAIL: test_injection_in_shopper_id_does_not_read_other_wardrobes
Ran 15 tests ... FAILED (failures=2)
```

Database error text is never returned to the browser (`test_database_errors_are_not_shown_to_the_browser`), so a failed query cannot reveal table or column names.

## Residual risk

* The shopper ID is a bearer secret: anyone who obtains it can read that wardrobe. Acceptable for a prototype holding no names or body data; a pilot needs proper accounts or signed sessions.
* No rate limiting yet, so IDs could be guessed at speed. With 128 random bits this is impractical, but rate limiting belongs in the pilot.
* The database file is not encrypted at rest.
