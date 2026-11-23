
import os
import sys
import inspect

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings"
)

import django
django.setup()

from django.urls import (
    get_resolver,
    reverse,
    resolve,
    NoReverseMatch,
)
from django.urls.resolvers import URLPattern, URLResolver


ROLE_RULES = {
    "DECIDERS": ("loan_officer",),
    "DISBURSERS": ("staff",),
    "PAYMENT_TAKERS": ("staff",),
    "CASHIERS": ("staff",),
}

PROTECTED_ROUTES = {
    "staff_loan_approve": "loan_officer",
    "staff_loan_reject": "loan_officer",
    "staff_create_agreement": "loan_officer",
    "staff_loan_disburse": "staff",
    "staff_loan_pay": "staff",
    "staff_deposit": "staff",
    "staff_withdraw": "staff",
    "staff_post_interest": "staff",
    "staff_approve_early_withdrawal": "staff",
    "staff_reject_early_withdrawal": "staff",
    "release_loans": "staff",
    "confirm_loan_release": "staff",
    "verify_clients": "staff",
    "verify_client_detail": "staff",
}

ARGUMENTS = {
    "loan_id": 1,
    "account_id": 1,
    "client_id": 1,
    "request_id": 1,
    "deposit_id": 1,
    "document_id": 1,
    "doc_id": 1,
    "user_id": 1,
    "side": "front",
}

failures = []
warnings = []


def heading(title):
    print()
    print("=" * 65)
    print(title)
    print("=" * 65)


def walk_urls(patterns, namespace=""):
    for entry in patterns:
        if isinstance(entry, URLResolver):
            new_namespace = namespace

            if entry.namespace:
                new_namespace = (
                    f"{namespace}:{entry.namespace}"
                    if namespace
                    else entry.namespace
                )

            yield from walk_urls(
                entry.url_patterns,
                new_namespace,
            )

        elif isinstance(entry, URLPattern):
            name = entry.name

            if name:
                full_name = (
                    f"{namespace}:{name}"
                    if namespace
                    else name
                )

                yield full_name, entry


def check_constants():
    heading("1. CHECK ROLE CONSTANTS")

    from loans import views as loan_views
    from loans import services as loan_services
    from savings import views as savings_views

    modules = {
        "loans.views": loan_views,
        "loans.services": loan_services,
        "savings.views": savings_views,
    }

    for module_name, module in modules.items():
        for constant, expected in ROLE_RULES.items():
            if not hasattr(module, constant):
                continue

            actual = getattr(module, constant)

            print(
                f"{module_name}.{constant}: {actual}"
            )

            if tuple(actual) != expected:
                failures.append(
                    f"{module_name}.{constant} "
                    f"should be {expected}, "
                    f"but is {actual}"
                )

    print("Role constant inspection complete.")


def check_routes():
    heading("2. CHECK PROTECTED URL ROUTES")

    all_routes = list(
        walk_urls(get_resolver().url_patterns)
    )

    found_names = {
        name for name, pattern in all_routes
    }

    for route_name, allowed_role in PROTECTED_ROUTES.items():

        if route_name not in found_names:
            failures.append(
                f"Missing URL name: {route_name}"
            )

            print(
                f"[MISSING] {route_name}"
            )
            continue

        matching = [
            pattern
            for name, pattern in all_routes
            if name == route_name
        ]

        if len(matching) > 1:
            warnings.append(
                f"Duplicate URL name: {route_name}"
            )

        pattern = matching[0]
        converters = getattr(
            pattern.pattern,
            "converters",
            {},
        )

        kwargs = {
            key: ARGUMENTS.get(key, 1)
            for key in converters
        }

        try:
            url = reverse(
                route_name,
                kwargs=kwargs or None,
            )

            match = resolve(url)

            callback = match.func

            callback_name = getattr(
                callback,
                "__name__",
                type(callback).__name__,
            )

            print(
                f"[FOUND] {route_name}"
            )
            print(
                f"        URL: {url}"
            )
            print(
                f"        View: {callback_name}"
            )
            print(
                f"        Expected role: {allowed_role}"
            )

            # Inspect wrapper chain, without executing
            # the view or modifying any records.
            chain = []
            current = callback
            seen = set()

            while current and id(current) not in seen:
                seen.add(id(current))

                chain.append(
                    getattr(
                        current,
                        "__name__",
                        type(current).__name__,
                    )
                )

                current = getattr(
                    current,
                    "__wrapped__",
                    None,
                )

            print(
                "        Wrapper chain: "
                + " -> ".join(chain)
            )

        except Exception as exc:
            failures.append(
                f"{route_name}: {exc}"
            )

            print(
                f"[ERROR] {route_name}: {exc}"
            )


def check_duplicates():
    heading("3. CHECK DUPLICATE URL NAMES")

    routes = list(
        walk_urls(get_resolver().url_patterns)
    )

    names = {}

    for name, pattern in routes:
        names.setdefault(name, []).append(
            str(pattern.pattern)
        )

    duplicates = {
        name: paths
        for name, paths in names.items()
        if len(paths) > 1
    }

    if not duplicates:
        print(
            "No duplicate named URL patterns found."
        )
        return

    for name, paths in duplicates.items():
        warnings.append(
            f"Duplicate URL name: {name}"
        )

        print(f"[WARNING] {name}")

        for path in paths:
            print(f"    {path}")


def check_project():
    heading("4. DJANGO SYSTEM CHECK")

    from django.core.management import call_command

    try:
        call_command("check")
    except Exception as exc:
        failures.append(
            f"Django system check failed: {exc}"
        )


def summary():
    heading("FINAL RESULTS")

    if failures:
        print(
            f"Found {len(failures)} issue(s):"
        )

        for item in failures:
            print(f"[ERROR] {item}")
    else:
        print(
            "No issues found in the checks performed."
        )

    if warnings:
        print()
        print(
            f"Found {len(warnings)} warning(s):"
        )

        for item in warnings:
            print(f"[WARNING] {item}")

    print()
    print(
        "IMPORTANT: This is a static configuration "
        "inspection, not a complete authorization test."
    )
    print(
        "A successful result does not prove that "
        "unauthorized POST requests return 403."
    )
    print(
        "No database records were changed."
    )

    return 1 if failures else 0


if __name__ == "__main__":
    check_constants()
    check_routes()
    check_duplicates()
    check_project()

    sys.exit(summary())
