
from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from django.urls import reverse
from django.db import transaction

USERS = {
    "admin": "admin",
    "staff": "teststaff",
    "loan_officer": "testofficer",
    "client": "testclient",
}

# Routes confirmed by the previous navigation test.
ALLOWED_PAGES = {
    "admin": [
        "admin_home",
        "admin_audit_log",
        "admin_clients",
        "admin_loan_products",
        "admin_reports",
        "admin_users",
        "staff_savings_accounts",
    ],
    "staff": [
        "staff_home",
        "staff_clients",
        "verify_clients",
        "release_loans",
        "staff_payments",
        "staff_payment_history",
        "staff_savings_accounts",
    ],
    "loan_officer": [
        "officer_home",
        "loan_applications",
        "officer_loans",
    ],
    "client": [
        "portal_home",
        "client_bank_page",
        "change_password",
        "client_profile",
        "chatbot:chat_page",
    ],
}

# Explicitly forbidden dashboard destinations.
BLOCKED_PAGES = {
    "admin": [
        "staff_home",
        "officer_home",
        "portal_home",
    ],
    "staff": [
        "admin_home",
        "officer_home",
        "portal_home",
    ],
    "loan_officer": [
        "admin_home",
        "staff_home",
        "portal_home",
    ],
    "client": [
        "admin_home",
        "staff_home",
        "officer_home",
    ],
}

User = get_user_model()

passed = 0
failed = 0
review = 0

with override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"]
):
    for role, username in USERS.items():
        print(f"\n{'=' * 60}")
        print(f"TESTING {role.upper()}")
        print(f"{'=' * 60}")

        user = User.objects.get(username=username)
        client = Client(raise_request_exception=False)
        client.force_login(user)

        print("\nALLOWED PAGES")

        for name in ALLOWED_PAGES[role]:
            try:
                url = reverse(name)

                with transaction.atomic():
                    response = client.get(url, follow=False)
                    status = response.status_code
                    transaction.set_rollback(True)

                if status == 200:
                    print(f"[PASS] {name}: 200")
                    passed += 1
                else:
                    print(
                        f"[REVIEW] {name}: {status} "
                        f"{response.get('Location', '')}"
                    )
                    review += 1

            except Exception as exc:
                print(
                    f"[FAIL] {name}: "
                    f"{type(exc).__name__}: {exc}"
                )
                failed += 1

        print("\nBLOCKED DASHBOARDS")

        for name in BLOCKED_PAGES[role]:
            try:
                url = reverse(name)

                with transaction.atomic():
                    response = client.get(url, follow=False)
                    status = response.status_code
                    transaction.set_rollback(True)

                if status == 403:
                    print(f"[PASS] {name}: 403")
                    passed += 1
                elif status in (301, 302, 303, 307, 308):
                    print(
                        f"[REVIEW] {name}: {status} "
                        f"{response.get('Location', '')}"
                    )
                    review += 1
                else:
                    print(
                        f"[FAIL] {name}: {status}, "
                        "expected access denial"
                    )
                    failed += 1

            except Exception as exc:
                print(
                    f"[FAIL] {name}: "
                    f"{type(exc).__name__}: {exc}"
                )
                failed += 1

        client.logout()

print(f"\n{'=' * 60}")
print("FINAL RESULTS")
print(f"{'=' * 60}")
print(f"Passed: {passed}")
print(f"Failed: {failed}")
print(f"Review: {review}")
print("GET requests only; no financial actions submitted.")
