# Delete my data, body data refused, deleted rows overwritten

**Date:** 26 November 2026
**Issue:** #5
**Risk:** R3 personal data and profiling. UK GDPR Article 17 (erasure), Article 5(1)(c) data minimisation and 5(1)(e) storage limitation. STRIDE Information disclosure.
**Decision record:** [ADR 0004](../../docs/adr/0004-delete-my-data-and-retention.md)

All requests were sent with curl to the server running locally (`python server.py`) with a fresh database. `Date` and `Server` headers are removed for length. Shopper and recommendation IDs are random test values, not real people.

## Before (main at commit dbefd48)

### B1. Body data sent with a saved pair is accepted

```
POST /api/wardrobe
{"product_id":"501","size":28,"feel":0,"height_cm":170,"weight_kg":60}

HTTP/1.0 200 OK
{"shopper_id": "v3m4K53Mbq2JWYDyqB8u0g", "pairs": [{"id": 1, "product_id": "501", "size": 28, "feel": 0, "created_on": "2026-11-26"}]}
```

The extra fields were not stored, but nothing told the client they were not wanted. The no body data promise rested on the page alone.

### B2. A date of birth sent with a recommendation request is accepted

```
POST /api/recommend
{"owned_size":28,"feel":0,"intent":"regular","query":"rigid straight","date_of_birth":"1999-01-01"}

HTTP/1.0 200 OK
```

### B3. There is no way to delete your data

```
DELETE /api/shopper
X-Shopper-Id: v3m4K53Mbq2JWYDyqB8u0g

HTTP/1.0 501 Unsupported method ('DELETE')
```

### B4. Deleting at storage level leaves the ID in the file

The server stopped, `storage.delete_shopper` was called directly on the same database, and the raw file was searched:

```
{'shoppers': 1, 'owned_pairs': 1, 'fit_reports': 0, 'recommendations': 0}
ID still in file bytes: True
```

## After (branch feat/5-delete-my-data)

### A1. Body data refused

```
POST /api/wardrobe
{"product_id":"501","size":28,"feel":0,"height_cm":170,"weight_kg":60}

HTTP/1.0 400 Bad Request
{"error": "Unexpected field: height_cm, weight_kg"}
```

```
POST /api/recommend
{"owned_size":28,"feel":0,"intent":"regular","query":"rigid straight","date_of_birth":"1999-01-01"}

HTTP/1.0 400 Bad Request
{"error": "Unexpected field: date_of_birth"}
```

### A2. A shopper builds up data

Saved a pair (200, new shopper `Zo2B4BWNqTOosRRwFfqVLw`), asked for a size (recommendation `EiJE-30OQOyeewCu091YYA`) and reported W29 as tight (200, `"stored": true`).

### A3. Delete my data

```
DELETE /api/shopper
X-Shopper-Id: Zo2B4BWNqTOosRRwFfqVLw

HTTP/1.0 200 OK
{"deleted": {"shoppers": 1, "owned_pairs": 1, "fit_reports": 1, "recommendations": 1}}
```

### A4. The ID no longer works anywhere

| Request | Status | Body |
| --- | --- | --- |
| `GET /api/wardrobe` with the deleted ID | 404 | `{"error": "Unknown shopper ID"}` |
| `POST /api/wardrobe` with the deleted ID (trying to revive it) | 404 | `{"error": "Unknown shopper ID"}` |
| `POST /api/report` on the deleted recommendation | 404 | `{"error": "Unknown recommendation"}` |
| `DELETE /api/shopper` a second time | 404 | `{"error": "Unknown shopper ID"}` |
| `DELETE /api/shopper` with `X-Shopper-Id: x' OR '1'='1` | 400 | `{"error": "Invalid shopper ID"}` |

### A5. Nothing left in the database or in the file

Server stopped, then the database file was checked:

```
ID in file bytes: False | rec ID in file bytes: False
{'shoppers': 0, 'owned_pairs': 0, 'fit_reports': 0, 'recommendations': 0}
```

### A6. In the browser

Headless Chromium: save a pair, get a size, report the fit, reload (the button appears), click Delete my data, cancel (ID kept), click again and confirm. The note reads "Deleted 1 saved pair, 1 fit report and 1 recommendation. Nothing linked to you is left on our server.", the ID is removed from localStorage and the button hides. No console errors. Screenshot: [20261126_delete_my_data_confirmation.png](20261126_delete_my_data_confirmation.png).

## Tests that prove it

* `app/tests/test_server.py`: `test_delete_removes_everything_the_shopper_stored` (checks every table directly), `test_after_deletion_the_id_no_longer_works`, `test_delete_leaves_other_shoppers_alone`, `test_delete_needs_a_valid_shopper_id`, `test_body_data_is_refused_when_saving_a_pair`, `test_body_data_is_refused_when_asking_for_a_size`, `test_refused_request_stores_nothing`, `test_making_a_recommendation_purges_old_ones`.
* `app/tests/test_storage.py`: `test_deleted_shopper_id_is_not_left_in_the_database_file` (reads raw bytes), `test_secure_delete_is_switched_on`, three retention tests.

**Do the tests catch a regression?** With `secure_delete` removed, the two file tests fail. With `PRAGMA foreign_keys` switched off (so cascade silently does nothing), seven tests fail, including both delete tests above. Both changes were reverted.

## Limitations

* The shopper ID is a bearer secret: whoever holds it can delete that shopper's data.
* Copies outside the live file (backups, a copy already taken) are not reached. The prototype has no backups.
* Shoppers who never return are not expired yet; there is no last seen date.
