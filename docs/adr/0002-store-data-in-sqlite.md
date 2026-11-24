# ADR 0002: Store wardrobes and fit reports in SQLite with parameterised queries

**Status:** Accepted, 19 November 2026

## Context

Until now the prototype kept nothing: the owned pair lived in the browser and fit reports vanished after the belief update. The product depends on fit reports building up over time (they are what the sensor model is relearned from in the pilot), and the security evaluation needs real stored personal data to protect, attack and delete.

The prototype must still run with `python server.py` on a student laptop, with no database server to install.

## Decision

* Use SQLite through Python's built in `sqlite3` module. One file, `app/data/fitting_room.db` (ignored by git), or the path in `FITTING_ROOM_DB`.
* Three tables: `shoppers` (random ID and creation date only), `owned_pairs`, `fit_reports`. Foreign keys with `ON DELETE CASCADE`, so deleting a shopper removes everything about them in one statement.
* Every query uses `?` placeholders. No SQL is ever built by joining strings.
* `CHECK` constraints repeat the server's rules (size range, allowed feel and report values) as a second line of defence.
* Shoppers are identified by a 128 bit random ID from `secrets.token_urlsafe`, sent in an `X-Shopper-Id` header rather than the URL so it stays out of logs and browser history.
* Only the date is stored, not the time of day.

## Consequences

* No new dependency; the app still starts the same way.
* Injection into storage is blocked at two layers (see `evidence/security/20261119_sql_injection_wardrobe.md`).
* Deletion is simple and provable, which the delete my data work (#5) builds on.
* SQLite allows one writer at a time. Fine for a prototype and a small pilot; a larger service would move to a managed database.
* The random ID is a bearer secret with no password behind it. Acceptable while no names or body data are held, but a pilot needs real authentication.
* The file is not encrypted at rest.

## Alternatives considered

* **Keep everything in the browser (localStorage).** Rejected: fit reports could not be pooled to relearn the sensor, and there would be nothing server side to secure or delete.
* **JSON file on disk.** Rejected: no safe concurrent writes from a threaded server, no constraints, and deletion means rewriting the whole file.
* **PostgreSQL or another server database.** Rejected for the prototype: needs installing and running a separate service, which breaks the one command start. Worth revisiting for a pilot.
* **An ORM such as SQLAlchemy.** Rejected: a heavy dependency for three tables, and hand written parameterised SQL is easier to explain line by line.
