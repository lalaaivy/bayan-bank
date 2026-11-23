
from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from django.urls import reverse, NoReverseMatch
from django.db import transaction


TEST_USERS = {
    "admin": "admin",
    "staff": "teststaff",
    "loan_officer": "testofficer",
    "client": "testclient",
}

# These are deliberately nonexistent IDs.
# We test unauthorized requests only.
INVALID_ID = 999999999

PROTECTED_ACTIONS = [
    ("staff_loan_approve", "loan_officer", {"loan_id": INVALID_ID}),
    ("staff_loan_reject", "loan_officer", {"loan_id": INVALID_ID}),
    ("staff_create_agreement", "loan_officer", {"loan_id": INVALID_ID}),
    ("staff_loan_disburse", "staff", {"loan_id": INVALID_ID}),
    ("staff_loan_pay", "staff", {"loan_id": INVALID_ID}),
    ("staff_deposit", "staff", {"account_id": INVALID_ID}),
    ("staff_withdraw", "staff", {"account_id": INVALID_ID}),
    ("staff_post_interest", "staff", {"account_id": INVALID_ID}),
    (
        "staff_approve_early_withdrawal",
        "staff",
        {"request_id": INVALID_ID},
    ),
    (
        "staff_reject_early_withdrawal",
        "staff",
        {"request_id": INVALID_ID},
    ),
    ("release_loans", "staff", {}),
    ("confirm_loan_release", "staff", {}),
    ("verify_clients", "staff", {}),
    (
        "verify_client_detail",
        "staff",
        {"client_id": INVALID_ID},
    ),
    (
        "loan_application_detail",
        "loan_officer",
        {"loan_id": INVALID_ID},
    ),
]

passed = 0
failed = 0
errors = 0


def test_access():
    global passed, failed, errors

    User = get_user_model()

    print("=" * 65)
    print("BAYAN BANK - SEPARATION OF DUTIES ACCESS TEST")
    print("=" * 65)

    users = {}

    for role, username in TEST_USERS.items():
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            print(f"[ERROR] Missing test user: {username}")
            errors += 1
            continue

        actual_role = getattr(
            getattr(user, "role", None),
            "name",
            None,
        )

        if actual_role != role:
            print(
                f"[ERROR] {username}: expected {role}, "
                f"found {actual_role}"
            )
            errors += 1
            continue

        users[role] = user

    print()

    for route_name, allowed_role, kwargs in PROTECTED_ACTIONS:
        print(f"Testing: {route_name}")
        print(f"Allowed role: {allowed_role}")

        try:
            url = reverse(
                route_name,
                kwargs=kwargs or None,
            )
        except NoReverseMatch as exc:
            print(f"  [ERROR] Cannot resolve route: {exc}")
            errors += 1
            print()
            continue

        for role, user in users.items():
            if role == allowed_role:
                # Do not execute authorized financial operations.
                continue

            client = Client(
                raise_request_exception=False,
                enforce_csrf_checks=False,
            )

            client.force_login(user)

            try:
                # Roll back any database writes if an
                # incorrectly permitted request reaches
                # application code.
                with transaction.atomic():
                    response = client.post(
                        url,
                        data={},
                    )

                    status = response.status_code

                    transaction.set_rollback(True)

                if status == 403:
                    print(
                        f"  [PASS] {role}: 403 Forbidden"
                    )
                    passed += 1

                else:
                    print(
                        f"  [FAIL] {role}: HTTP {status} "
                        "(expected 403)"
                    )
                    failed += 1

            except Exception as exc:
                print(
                    f"  [ERROR] {role}: "
                    f"{type(exc).__name__}: {exc}"
                )
                errors += 1

            finally:
                client.logout()

        print()

    print("=" * 65)
    print("FINAL RESULTS")
    print("=" * 65)
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Errors: {errors}")

    if failed == 0 and errors == 0:
        print(
            "All tested unauthorized requests "
            "returned 403."
        )
    else:
        print(
            "Some authorization checks require attention."
        )

    print()
    print(
        "Authorized financial actions were not executed."
    )
    print(
        "Database changes within test requests "
        "were rolled back."
    )
    print(
        "This test does not verify external side effects "
        "or all possible application entry points."
    )


with override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
):
    test_access()
