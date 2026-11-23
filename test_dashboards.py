
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

DASHBOARDS = {
    "admin": "admin_home",
    "staff": "staff_home",
    "loan_officer": "officer_home",
    "client": "portal_home",
}

User = get_user_model()

passed = 0
failed = 0
errors = 0

with override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"]
):
    for role, username in USERS.items():
        print(f"\n{'=' * 60}")
        print(f"TESTING {role.upper()} DASHBOARD")
        print(f"{'=' * 60}")

        try:
            user = User.objects.get(username=username)

            actual_role = getattr(
                getattr(user, "role", None),
                "name",
                None,
            )

            if actual_role != role:
                print(
                    f"[ERROR] Incorrect role: {actual_role}"
                )
                errors += 1
                continue

            client = Client(raise_request_exception=False)
            client.force_login(user)

            url = reverse(DASHBOARDS[role])

            # Roll back database writes triggered by requests.
            with transaction.atomic():
                response = client.get(url, follow=False)
                status = response.status_code
                transaction.set_rollback(True)

            if status == 200:
                print(f"[PASS] {url}: HTTP 200")
                passed += 1

                content = response.content.decode(
                    "utf-8", errors="replace"
                )

                print(
                    f"Page size: {len(content):,} characters"
                )

            elif status in (301, 302, 303, 307, 308):
                print(
                    f"[REVIEW] {url}: HTTP {status}"
                )
                print(
                    f"Redirect: {response.get('Location')}"
                )
                failed += 1

            else:
                print(f"[FAIL] {url}: HTTP {status}")
                failed += 1

            client.logout()

        except Exception as exc:
            print(
                f"[ERROR] {type(exc).__name__}: {exc}"
            )
            errors += 1

print(f"\n{'=' * 60}")
print("FINAL DASHBOARD TEST RESULTS")
print(f"{'=' * 60}")
print(f"Passed: {passed}")
print(f"Failed/Review: {failed}")
print(f"Errors: {errors}")
print("GET requests only. No financial actions submitted.")
