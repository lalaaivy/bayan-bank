
from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from django.urls import reverse, NoReverseMatch

USERS = {
    "admin": "admin",
    "staff": "teststaff",
    "loan_officer": "testofficer",
    "client": "testclient",
}

# These routes were confirmed in the earlier checks.
PAGES = [
    ("staff_clients", "staff", {}),
    ("loan_applications", "loan_officer", {}),
    ("release_loans", "staff", {}),
    ("verify_clients", "staff", {}),
]

passed = 0
failed = 0
errors = 0

User = get_user_model()

with override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"]
):
    for role, username in USERS.items():
        print(f"\n{'=' * 55}")
        print(f"TESTING ROLE: {role.upper()}")
        print(f"{'=' * 55}")

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            print(f"[ERROR] Missing user: {username}")
            errors += 1
            continue

        actual_role = getattr(
            getattr(user, "role", None), "name", None
        )

        if actual_role != role:
            print(f"[ERROR] Incorrect role for {username}")
            errors += 1
            continue

        client = Client(raise_request_exception=False)
        client.force_login(user)

        for name, allowed_role, kwargs in PAGES:
            if role != allowed_role:
                continue

            try:
                url = reverse(name, kwargs=kwargs or None)
                response = client.get(url, follow=False)
                status = response.status_code

                # 200 = page loaded
                # 302 = redirect; investigate destination
                if status == 200:
                    print(f"[PASS] {name}: HTTP 200")
                    passed += 1
                elif status in (301, 302, 303, 307, 308):
                    print(
                        f"[REVIEW] {name}: HTTP {status}, "
                        f"redirects to {response.get('Location')}"
                    )
                    failed += 1
                else:
                    print(f"[FAIL] {name}: HTTP {status}")
                    failed += 1

            except NoReverseMatch as exc:
                print(f"[ERROR] {name}: {exc}")
                errors += 1
            except Exception as exc:
                print(
                    f"[ERROR] {name}: "
                    f"{type(exc).__name__}: {exc}"
                )
                errors += 1

        client.logout()

print(f"\n{'=' * 55}")
print("FINAL RESULTS")
print(f"{'=' * 55}")
print(f"Passed: {passed}")
print(f"Failed/Review: {failed}")
print(f"Errors: {errors}")
print("GET requests only; no financial actions submitted.")
