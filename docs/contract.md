# Bayan Bank UI Route Contract

The application routes below are declared in `accounts/urls.py` (without an
application namespace). Templates are presentation-only and use fixed demo data
unless a context variable is listed. Forms submit to demo handlers; nothing is
persisted.

The shared `base.html` expects Django's `request` and `messages` context values.
All rendered pages inherit those values.

| URL name | Path | Template | Who can open it | Additional context |
|---|---|---|---|---|
| `home` | `/` | — (redirects by role) | Authenticated client, staff, loan officer, or admin | None |
| `login` | `/login/` | `registration/login.html` | Public | `form`, `next` (Django `LoginView`) |
| `logout` | `/logout/` | — (redirects to login) | Authenticated user | None |
| `portal_home` | `/portal/` | `portal/home.html` | Client | None |
| `staff_home` | `/staff/` | `staff/home.html` | Staff, admin | None |
| `my_loans` | `/portal/loans/` | `portal/loans.html` | Client | None |
| `savings_history` | `/portal/savings/` | `portal/savings.html` | Client | None |
| `notifications` | `/portal/notifications/` | `portal/notifications.html` | Client | None |
| `apply_loan` | `/portal/apply/` | `portal/apply_loan.html` | Client | None |
| `loan_detail` | `/portal/loans/detail/` | `portal/loan_detail.html` | Client | None |
| `upload_id` | `/portal/upload-id/` | `portal/upload_id.html` | Client | None |
| `accept_agreement` | `/portal/accept-agreement/` | `portal/accept_agreement.html` | Client | None |
| `client_profile` | `/portal/profile/` | `portal/profile.html` | Client | None |
| `edit_client_profile` | `/portal/profile/edit/` | `portal/profile_edit.html` | Client | None |
| `change_password` | `/portal/change-password/` | `portal/change_password.html` | Client | None |
| `register` | `/register/` | `registration/register.html` | Public | None |
| `complete_profile` | `/register/complete-profile/` | `registration/complete_profile.html` | Public | None |
| `officer_home` | `/officer/` | `officer/home.html` | Loan officer, admin | None |
| `admin_home` | `/admin-panel/` | `adminpanel/home.html` | Admin | None |
| `staff_clients` | `/staff/clients/` | `staff/clients.html` | Staff, admin | None |
| `staff_client_detail` | `/staff/clients/detail/` | `staff/client_detail.html` | Staff, admin | None |
| `staff_add_client` | `/staff/clients/add/` | `staff/add_client.html` | Staff, admin | None |
| `verify_clients` | `/staff/clients/verify/` | `staff/verify_clients.html` | Staff, admin | `clients` |
| `verify_client_detail` | `/staff/clients/verify/detail/` | `staff/verify_client_detail.html` | Staff, admin | None |
| `staff_payments` | `/staff/payments/` | `staff/payments.html` | Staff, admin | None |
| `staff_payment_history` | `/staff/payments/history/` | `staff/payment_history.html` | Staff, admin | None |
| `staff_receipt` | `/staff/payments/receipt/` | `staff/receipt.html` | Staff, admin | None |
| `staff_savings` | `/staff/savings/` | `staff/savings.html` | Staff, admin | None |
| `release_loans` | `/staff/loans/release/` | `staff/release_loan.html` | Staff, admin | None |
| `confirm_loan_release` | `/staff/loans/release/confirm/` | `staff/release_confirmation.html` | Staff, admin | None |
| `loan_applications` | `/officer/applications/` | `officer/applications.html` | Loan officer, admin | `applications`, `status_filter` |
| `loan_application_detail` | `/officer/applications/detail/` | `officer/application_detail.html` | Loan officer, admin | None |
| `officer_loans` | `/officer/loans/` | `officer/loans.html` | Loan officer, admin | None |
| `officer_loan_detail` | `/officer/loans/detail/` | `officer/loan_detail.html` | Loan officer, admin | None |
| `admin_users` | `/admin-panel/users/` | `adminpanel/users.html` | Admin | None |
| `admin_clients` | `/admin-panel/clients/` | `adminpanel/clients.html` | Admin | None |
| `admin_create_user` | `/admin-panel/users/create/` | `adminpanel/user_form.html` | Admin | None (`editing` omitted/false) |
| `admin_edit_user` | `/admin-panel/users/edit/` | `adminpanel/user_form.html` | Admin | `editing` |
| `admin_loan_products` | `/admin-panel/loan-products/` | `adminpanel/loan_products.html` | Admin | None |
| `admin_product_form` | `/admin-panel/loan-products/form/` | `adminpanel/product_form.html` | Admin | None |
| `admin_reports` | `/admin-panel/reports/` | `adminpanel/reports.html` | Admin | None |
| `admin_audit_log` | `/admin-panel/audit-log/` | `adminpanel/audit_log.html` | Admin | None |

## Error handlers

| Handler | Template | Who can open it | Context |
|---|---|---|---|
| HTTP 403 (`handler403`) | `403.html` | Any user receiving `PermissionDenied` | `request`, `messages` |
| HTTP 404 (Django default handler) | `404.html` | Any visitor requesting a missing page | `request`, `messages` |

Role access for staff and loan officer screens includes admin as specified for
this UI. The built-in Django admin under `/admin/` is separate from these pages.