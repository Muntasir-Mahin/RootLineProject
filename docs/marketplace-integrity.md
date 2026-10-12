# Marketplace integrity changes

The cart checks stock and creates orders, payment records and stock deductions in one transaction. Products are locked in ID order. SQL stock updates check the current quantity and use database arithmetic, so stale Python values cannot overwrite another purchase. Cancellation restores stock once using database arithmetic.

SQLite uses `IMMEDIATE` transactions because `select_for_update()` has no effect on SQLite. This serializes writers with a 20-second lock timeout. PostgreSQL uses row locks through the same application code, but the current validation was performed on SQLite.

## Auctions and fixed-price purchases

A product with an upcoming or running auction cannot be added to the cart or bought through an existing cart. After the auction ends, fixed-price purchases remain paused until its winner creates an order. Purchases resume when an auction is cancelled, ends without bids, or has a winning order. This deliberately protects the whole product stock rather than assuming that an auction sells only a fraction of it.

Auction creation and editing, bidding, finalization and winner checkout use the same product-before-auction lock order. Auctions require at least one available unit. Bids and public auction detail pages require a verified, available auction product with sufficient stock. Finalization also recovers legacy auctions marked ended without recording a winner, using their existing eligible bids. It preserves cancelled auctions and settled winners.

## Reviews and migration

A review requires a delivered order belonging to the buyer that contains the reviewed product. The database allows one review per buyer, product and order; repeated submissions keep the original review.

Apply the new review constraint with:

```sh
.venv/bin/python manage.py migrate --noinput
```

If existing duplicate reviews would prevent the constraint, the migration stops with an explanation and preserves the rows. Back up and reconcile those duplicates before retrying. It never silently deletes customer reviews.

## Validation

Run the suite from the repository root. Use a disposable file-backed test database so SQLite concurrency checks execute:

```sh
ROOTLINE_TEST_DB="$(mktemp /tmp/rootline-tests.XXXXXX.sqlite3)" .venv/bin/python manage.py test --noinput
```

Django creates and destroys this isolated test database; application data is not used. Without `ROOTLINE_TEST_DB`, Django uses an in-memory SQLite database and the concurrency tests explicitly skip because that database does not reproduce file-lock behavior.

The tests cover competing purchases of the last unit, duplicate cart and auction checkout submissions, auction creation competing with a cart purchase, equal simultaneous bids, duplicate reviews and cancellations, fractional stock, legacy auction finalization, product eligibility, wishlist POST/CSRF protection and malformed price filters.
