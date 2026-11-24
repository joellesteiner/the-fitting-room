# The database and source code can no longer be downloaded

**Date:** 24 November 2026
**Issue:** #17 (risk R3, personal data)
**Frameworks:** OWASP Top 10 (2021) A01 Broken Access Control and A05 Security Misconfiguration; STRIDE Information disclosure and Spoofing

## How it was found

While preparing the front end redesign, a review of `server.py` showed that the static file handler used the whole `app` folder as its web root. The database lives in `app/data/fitting_room.db`, inside that folder. The automated tests did not catch it because they use a database in a temporary folder.

## Set up

Server started from `app/` with no `FITTING_ROOM_DB` set, so the database sits in its default place, `app/data/fitting_room.db`. One shopper saved a pair first. Requests sent with curl from the same machine. `Date` and `Server` headers removed; nothing else is edited. IDs are random test values, not real people.

## Before: main at commit dbefd48 (after PR #16)

### B1. The whole database downloads

```
$ curl -s http://127.0.0.1:8799/data/fitting_room.db -o stolen.db -w '%{http_code} %{size_download}B\n'
200 36864B
```

### B2. Reading it gives every shopper ID and wardrobe

```
$ python -c "import sqlite3; c = sqlite3.connect('stolen.db'); ..."
shoppers: [('ARc6sD_lbxf2qOWnB_n2uw', '2026-11-24')]
owned_pairs: [('ARc6sD_lbxf2qOWnB_n2uw', '501', 28, -2)]
```

### B3. A stolen ID lets the attacker act as that shopper

The shopper ID is the only thing that proves who a shopper is (see ADR 0002), so with it the attacker can read the wardrobe, add pairs and send fit reports in that shopper's name:

```
$ curl -s http://127.0.0.1:8799/api/wardrobe -H 'X-Shopper-Id: ARc6sD_lbxf2qOWnB_n2uw'
{"shopper_id": "ARc6sD_lbxf2qOWnB_n2uw", "pairs": [{"id": 1, "product_id": "501", "size": 28, "feel": -2, "created_on": "2026-11-24"}], "fit_reports": []}
```

### B4. The source code downloads too

```
/server.py  -> 200 8107B
/storage.py -> 200 8125B
```

The source is public on GitHub anyway, so this matters less, but it shows the web root was wrong.

## After: branch feat/17-serve-only-public-files

The front end moved to `app/static/`, and the server's web root is now that folder only. The database, source, tests and model file are outside it. Folder listings are switched off.

```
/                            200 25302B
/data/fitting_room.db        404 335B
/server.py                   404 335B
/storage.py                  404 335B
/model/sensor_learned.json   404 335B
/tests/                      404 335B
/../data/fitting_room.db     404 335B
/%2e%2e/server.py            404 335B
```

(The `..` requests were sent with `curl --path-as-is`, so curl did not tidy them before sending.)

```
$ curl -i http://127.0.0.1:8799/data/fitting_room.db
HTTP/1.0 404 File not found
Connection: close
Content-Type: text/html;charset=utf-8
Content-Length: 335
```

The database file was present on disk at the time (36,864 bytes in `app/data/`); it simply cannot be reached.

## Automated tests

`app/tests/test_server.py`, class `PublicFilesOnly`, checks the front end is served and that the database path, source files, tests, model file, folder listings and five `..` tricks all get 404. To check the tests detect the flaw, the web root was temporarily set back to the whole `app` folder: two tests failed (source files served, `/static/../server.py` served). The change was reverted and all 76 app tests passed.

The database test on its own would not have failed in that check, because the test server keeps its database in a temporary folder. The source file tests are what catch a wrong web root.

## What this does not stop

* Anyone who learns a shopper ID some other way can still act as that shopper. Real accounts are a pilot item (ADR 0002).
* The database file is not encrypted at rest.
