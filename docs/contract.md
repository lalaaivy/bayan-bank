# Bayan Bank: Team Contract

Agreement between Backend, Database and Frontend. If something here needs to
change, change this file first, then the code.

Status: DRAFT, to be confirmed by all three teammates.

## 1. Ground rules

- Money is always `DecimalField(max_digits=14, decimal_places=2)`. Never float.
- Interest rates are `DecimalField(max_digits=5, decimal_places=2)` (12.50 means 12.5%).
- Ledger rows are never edited or deleted. Corrections are new reversing rows.
- Foreign keys use `on_delete=PROTECT`. Nothing is deleted if it has history.
- Only backend services (`services.py` in each app) change balances or loan status.
  Views, admin and templates never do.
- Database owns: models and migrations. Backend owns: services, views, permissions.
  Frontend owns: templates and static files.
- Sensitive client ID numbers are stored encrypted, with a separate hash for lookups.

## 2. Roles (already built, seeded by migration)

admin, loan_officer, staff, client

## 3. Models (Database team builds these)

| App | Model | Fields |
|---|---|---|
| accounts | Role, User | (done) |
| clients | Client | user (OneToOne to User, role=client), id_number_encrypted (BinaryField), id_number_hash (CharField 64, unique, indexed), phone, address, date_of_birth, created_at |
| loans | LoanProduct | name, annual_rate, min_amount, max_amount, min_months, max_months, is_active |
| loans | Loan | client (FK), product (FK), principal, annual_rate (copied from product at application), term_months, status, applied_at, decided_by (FK User, null), decided_at, disbursed_at, start_date |
| loans | Installment | loan (FK), number, due_date, principal_due, interest_due, amount_paid (default 0), paid_at (null), status. Unique on (loan, number) |
| savings | SavingsAccount | client (FK), account_number (unique), balance, status, opened_at |
| accounting | LedgerEntry | entry_type, amount (always positive), balance_after, savings_account (FK, null), loan (FK, null), reference, created_by (FK User), created_at. Append-only |
| audit | AuditLog | user (FK, null), action, object_type, object_id, details (JSONField), ip_address, created_at |
| notifications | Notification | user (FK), kind, message, is_read (default False), created_at |

Choices:
- Loan.status: pending, approved, rejected, active, paid, defaulted
- Installment.status: due, paid, overdue
- SavingsAccount.status: active, frozen, closed
- LedgerEntry.entry_type: deposit, withdrawal, transfer_in, transfer_out, loan_disbursement, loan_payment

Note: SavingsAccount.balance is a cached total. It must always equal the sum of
its ledger entries. Only services update it.

## 4. Pages (Backend builds views, Frontend builds templates)

Built already:

| URL | Method | Roles | Notes |
|---|---|---|---|
| / | GET | any logged in | redirects by role |
| /login/ | GET, POST | anyone | fields: username, password |
| /logout/ | POST | any logged in | must be a form button, not a link |
| /portal/ | GET | client | dashboard |
| /staff/ | GET | admin, loan_officer, staff | dashboard |

Client portal (to build):

| URL | Method | Roles | Template context / form fields |
|---|---|---|---|
| /portal/loans/ | GET | client | loans (own only) |
| /portal/loans/apply/ | GET, POST | client | products; fields: product, principal, term_months |
| /portal/loans/<id>/ | GET | client (owner) | loan, installments |
| /portal/savings/ | GET | client | accounts (own only), recent_entries |
| /portal/savings/transfer/ | POST | client | fields: from_account, to_account_number, amount |
| /portal/notifications/ | GET | client | notifications |

Staff (to build):

| URL | Method | Roles | Template context / form fields |
|---|---|---|---|
| /staff/clients/ | GET | admin, loan_officer, staff | clients (search by name or ID) |
| /staff/clients/new/ | GET, POST | admin, staff | fields: username, first_name, last_name, email, id_number, phone, address, date_of_birth |
| /staff/loans/ | GET | admin, loan_officer | loans filtered by status |
| /staff/loans/<id>/approve/ | POST | admin, loan_officer | none |
| /staff/loans/<id>/reject/ | POST | admin, loan_officer | field: reason |
| /staff/loans/<id>/disburse/ | POST | admin, loan_officer | none |
| /staff/loans/<id>/payment/ | POST | admin, staff | field: amount |
| /staff/savings/<id>/deposit/ | POST | admin, staff | field: amount |
| /staff/savings/<id>/withdraw/ | POST | admin, staff | field: amount |
| /staff/reports/ | GET | admin, loan_officer | download PDF or Excel |
| /staff/audit/ | GET | admin | audit_logs |

## 5. Open questions (decide together)

1. Can clients sign up themselves, or does staff always create them?
2. Can clients deposit or withdraw online, or only through staff?
3. Is there a transfer fee or minimum balance?
4. Late payment penalty: yes or no, and how much?
5. Does a loan need two approvals above a certain amount?
