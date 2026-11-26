# ADR 0004: Delete my data, refuse body data and keep recommendations for 30 days

**Status:** Accepted, 26 November 2026

## Context

Since #3 and #4 the server stores a pseudonymous shopper ID, owned pairs, fit reports and recommendations. UK GDPR gives a shopper the right to erasure (Article 17) and requires data minimisation and storage limitation (Article 5(1)(c) and (e)). Three gaps were found before this change:

* There was no way for a shopper to delete their data. `storage.delete_shopper` existed but nothing called it, and `DELETE` requests got 501.
* `POST /api/wardrobe` and `POST /api/recommend` silently accepted extra fields. A body such as `{"height_cm": 170}` returned 200. Nothing was stored, but the product's central promise (no body data) was enforced only by the front end.
* Deleted rows stayed readable in the database file. SQLite marks deleted rows as free space without overwriting them, so after a delete the shopper ID could still be found in the raw bytes.
* Recommendations, including those for shoppers with no saved wardrobe, were kept for ever (noted in ADR 0003).

## Decision

* `DELETE /api/shopper` with the `X-Shopper-Id` header deletes the shopper. `ON DELETE CASCADE` removes their owned pairs, fit reports and recommendations. The reply lists how many rows went from each table. An unknown ID gets 404, so the ID cannot be revived by saving a new pair.
* `PRAGMA secure_delete = ON` for every connection, so deleted content is overwritten with zeros. A test reads the file bytes to prove the ID is gone.
* Every POST endpoint has an explicit set of allowed fields. Anything else is refused with 400, the same rule ADR 0003 applied to fit reports.
* Recommendations older than 30 days are deleted. A recommendation is only needed until the shopper can report how the pair fitted: delivery plus the 14 day cancellation period under the Consumer Contracts Regulations 2013 fits well inside 30 days. The purge runs whenever a new recommendation is made, using an index on `created_on`. A fit report outlives its recommendation; `ON DELETE SET NULL` clears only the link.
* A Delete my data button on the first step, shown only when the browser holds an ID, with a confirmation dialog.

## Consequences

* Erasure is complete and provable from tests and from the raw file, which is evidence for risk R3 in the report.
* The no body data promise is now enforced by the server, not only by the page.
* Fit reports remain after their recommendation is purged, so the data the sensor model is relearned from is kept, without the probabilities or the link.
* The shopper ID is still a bearer secret: anyone holding it can delete that shopper's data. Acceptable for a prototype without accounts; a pilot needs real authentication.
* Deleted content can still exist outside the live file: in backups, in a copy someone already took, or briefly in the rollback journal. The prototype has no backups; a pilot would need a backup retention period.
* Shoppers who never return are kept indefinitely, because there is no "last seen" date. A pilot should add one and expire inactive shoppers.

## Alternatives considered

* **Soft delete (a `deleted` flag).** Rejected: the data would still be held, which is not erasure.
* **`VACUUM` after each delete** instead of `secure_delete`. Rejected: it rewrites the whole file on every delete and needs no open transactions; `secure_delete` does the same job for just the pages touched.
* **Ignore unknown fields.** Rejected for the same reason as in ADR 0003: refusing makes a misbehaving client visible and gives clear evidence.
* **A scheduled job for the purge.** Rejected for the prototype: it would need a second process or thread; purging when a recommendation is made runs often enough and is easy to test.
* **A shorter retention, such as one day, for shoppers with no saved wardrobe.** Considered: those recommendations cannot be reported on after the page is closed. Rejected to keep one rule that is easy to explain; worth revisiting with pilot data.
