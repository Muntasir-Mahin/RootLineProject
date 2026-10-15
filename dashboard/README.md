# RootLine staff dashboard

Run from the directory containing `manage.py` (activate the project's virtual environment first):

```sh
python manage.py migrate
python manage.py create_dashboard_roles
python manage.py runserver
```

Sign in through the normal `/login/` page, then visit `/dashboard/` or use **Staff dashboard** on My account. The panel uses Django templates and `dashboard/static/dashboard/dashboard.css`; it needs no Tailwind compilation. Deploy its static files with the normal `collectstatic` process.

## Assigning staff

As the owner, sign in at `/admin/`. The management command creates **Finance**, **Support**, and **Catalogue**, and can safely run more than once. On each user's change screen, check **Active** and **Staff status**. Then open the appropriate group on the Groups screen, select users in **Members**, and save. The user's Groups field also works. Leave **Superuser status** unchecked and do not grant Django model permissions. A group alone does not grant access without staff status.

| Membership | Dashboard pages |
| --- | --- |
| Any active staff | Overview, read-only orders, activity log |
| Finance | Payments: verify or fail manual transactions |
| Support | Dispute details and decisions |
| Catalogue | Seller requests/approvals and product reviews |
| Superuser | Every page, plus owner-only Django admin |

Users may belong to several groups. Removing a group takes effect on the next request. Other staff cannot access `/admin/`, including its login page while signed in. The owner can continue managing users and groups there.

## Decisions and audit

Payment verification/failure runs through `payments/services.py`; dispute decisions run through `disputes/services.py`. Django admin uses the same services through its actions menu; enter a **Decision note** above the list before applying an action. Payment and dispute records are otherwise read-only in admin, as are seller approval flags and product verification status. Decisions produce an activity record with actor, target, summary, note and time. Admin's activity records cannot be added, changed or deleted through its interface.

All decision endpoints require POST and CSRF. Transactions lock **Order → Payment → Dispute** in that order, and include the audit writes. Repeated or invalid decisions show an error. Marking a case under review does not settle it; a final decision can be made once:

- **Refund buyer:** payment and escrow become refunded, and the order is cancelled.
- **Favour seller / Reject dispute:** escrow is released, the order is delivered, and the commission is deducted.
- **Buyer confirms delivery:** releases escrow only for a shipped order with no open dispute.

The commission rate is defined once as `COMMISSION_RATE` in `payments/services.py`. Commission is rounded to two decimals using `ROUND_HALF_UP`; the seller receives the exact remainder. These operations record manual payment/refund/release bookkeeping; existing bKash/Nagad funds must be checked and transferred by staff through their payment provider.

Seller requests are consumed by Approve/Reject; a rejected or revoked user can request again. Product decisions accept pending listings and reject repeated decisions. Seller cancellation before order confirmation preserves existing stock restoration and uses the payment refund service for held funds.

The overview counts payments waiting over 48 hours, and disputes, products and seller requests waiting over 72 hours. Override thresholds in settings if needed:

```python
DASHBOARD_STALE_HOURS = {'payments': 48, 'disputes': 72, 'products': 72, 'sellers': 72}
```

Existing seller requests had no submission timestamp, so the migration starts their age at deployment. New requests record the actual request time. Payment queue age uses its most recent update (including buyer resubmission). All displayed times use the existing `Asia/Dhaka` setting. Activity includes buyer/seller escrow events; the overview shows staff actions.

## Validation

```sh
python manage.py check
python manage.py makemigrations --check --dry-run
mkdir -p work
ROOTLINE_TEST_DB=work/dashboard-tests.sqlite3 python manage.py test --noinput
```

Use a disposable file-backed test database to exercise SQLite concurrency tests; SQLite's existing `IMMEDIATE` transaction mode serializes writers. Django skips concurrency tests on its default shared in-memory SQLite database. On PostgreSQL the services use row locks; this implementation's automated run used SQLite.
